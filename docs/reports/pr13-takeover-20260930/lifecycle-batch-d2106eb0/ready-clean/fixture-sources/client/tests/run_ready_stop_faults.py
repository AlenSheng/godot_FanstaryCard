"""Bounded actual Godot -> full Program -> owned Unix PostgreSQL fault proofs.

No remote server, accounts, uploads, gameplay shortcuts or revised deadlines.
Run directories are immutable: an existing output path is always rejected.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.request import urlopen

from fixture_runtime import isolated_environment

CASES = {
    "normal_ready": ("LOAD-04.4-T01", "Real normal READY followed by coordinator drain; one room, clear route/assets."),
    "required_lost_reconnect": ("LOAD-04.4-T01", "Drop first real required frame, disconnect, restore authoritative same room on reconnect."),
    "stop_prepare_await": ("LOAD-04.4-T03", "STOP while real preparation response awaits delivery; cancel preparation."),
    "stop_enqueue_await": ("LOAD-04.4-T03", "STOP while real enqueue response awaits delivery; cancel queued ticket."),
    "stop_ticket_await": ("LOAD-04.4-T03", "STOP while real queued ticket response awaits delivery; cancel ticket and no READY after STOP."),
    "stop_queue_wait": ("LOAD-04.4-T03", "STOP in queued wait; cancel ticket and release assets/route."),
    "stop_ready_enqueue_await": ("PR13-A04.4-T01", "Real READY arrives during enqueue await; STOP prevents send, actual 15s deadline removes player and releases holds."),
    "stop_ready_before_send": ("PR13-A04.4-T01", "STOP at actual READY event before send; cancellation or actual deadline removes player and releases holds."),
    "late_required_duplicate": ("LOAD-04.4-T01", "Deliver the real delayed required packet twice after READY dispatch; decoder sequence filtering and room context remain correct."),
    "late_accepted_before_ticket": ("LOAD-04.4-T01", "SupportOnly synthetic stale accepted packet through real decoder must not suppress authoritative current ticket reads."),
    "ready_accepted_lost_resume": ("LOAD-04.4-T01", "Discard the actual committed ready_accepted frame; sequence-gap session.resume restores the same authority and room."),
    "ready_started_lost_reconnect": ("PR13-A04.4-T02", "Discard the actual started frame after accepted READY, disconnect, then recover the same room by real reconnect snapshot/replay."),
    "ready_replies_lost_reconnect": ("PR13-A04.4-T02", "Discard real committed ready_accepted and started frames, disconnect, then recover the same room from authority."),
    "ready_send_lost_reconnect": ("PR13-A04.4-T02", "Discard the first actual serialized room.ready before forwarding; PostgreSQL remains Assigned, reconnect retries and enters exactly the same room."),
    "ready_send_all_lost_stop": ("PR13-A04.4-T01", "Discard all three actual serialized room.ready frames, STOP, and let the unchanged actual 15s deadline remove the Assigned player and release assets."),
}
TRANSPORT_CASES = {case for case in CASES if case.startswith("ready_")}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, help="New immutable evidence directory")
    parser.add_argument("--case", action="append", choices=CASES, help="Default: every frozen case")
    parser.add_argument("--godot", default=os.environ.get("A3GAME_GODOT_EXECUTABLE"))
    parser.add_argument("--dotnet", default=shutil.which("dotnet"))
    args = parser.parse_args()
    if not args.godot or not args.dotnet:
        parser.error("Source relicround-env/activate.sh or provide --godot/--dotnet")
    repo = Path(__file__).resolve().parents[2]
    work = Path(args.work_dir).resolve()
    if work.exists():
        parser.error("Output already exists; preserve original raw and choose a new directory")
    work.mkdir(parents=True)
    selected = args.case or list(CASES)
    commands = []
    cases = []
    pg_started = False
    pgdata = work / "private-pg"
    pg_socket = Path(tempfile.mkdtemp(prefix="pr13-ready-stop-", dir="/tmp"))
    server = None
    server_log = None
    proxy = None
    proxy_log = None
    pg_env = dict(os.environ, PGHOST=str(pg_socket), PGUSER="ready_stop_owner", PGPORT="5432")
    for key in ("PGOPTIONS", "PGPASSWORD", "PGSERVICE", "PGSERVICEFILE"):
        pg_env.pop(key, None)

    def run(command, label, cwd=repo, env=None, timeout=120, during_run=None):
        started = time.monotonic()
        try:
            if during_run is None:
                result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=timeout)
                raw = result.stdout + result.stderr
                code = result.returncode
            else:
                with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
                    try:
                        while process.poll() is None:
                            during_run()
                            if time.monotonic() - started >= timeout:
                                process.kill()
                                break
                            time.sleep(.05)
                        raw, _ = process.communicate(timeout=5)
                        code = process.returncode if time.monotonic() - started < timeout else 124
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=5)
        except subprocess.TimeoutExpired as exc:
            raw = (exc.stdout or b"") + (exc.stderr or b"") + b"\nFrozen command deadline exceeded\n"
            code = 124
        (work / (label + ".log")).write_bytes(raw)
        commands.append({"label": label, "command": list(map(str, command)), "cwd": str(cwd), "exit_code": code,
                         "duration_seconds": round(time.monotonic() - started, 3), "deadline_seconds": timeout,
                         "log": label + ".log"})
        return code, raw.decode(errors="replace")

    def sql(query, database="postgres"):
        result = subprocess.run(["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-d", database, "-c", query],
                                env=pg_env, capture_output=True, timeout=15)
        if result.returncode:
            raise RuntimeError("Private test database query failed")
        return result.stdout.decode().strip()

    def stop_server():
        nonlocal server, server_log
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            server = None
        if server_log is not None:
            server_log.close()
            server_log = None

    def stop_proxy():
        nonlocal proxy, proxy_log
        if proxy is not None:
            started = time.monotonic()
            proxy.terminate()
            try:
                proxy.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proxy.kill()
                proxy.wait(timeout=5)
            commands.append({"label": "owned-frame-proxy-cleanup", "command": ["SIGTERM", str(proxy.pid)],
                             "exit_code": proxy.returncode, "duration_seconds": round(time.monotonic() - started, 3),
                             "deadline_seconds": 10})
            for command in commands:
                if command.get("pid") == proxy.pid:
                    command["exit_code"] = proxy.returncode
                    command["status"] = "stopped"
            proxy = None
        if proxy_log is not None:
            proxy_log.close()
            proxy_log = None

    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo).decode().strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo).decode().splitlines()
    plan = repo / "docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json"
    source_paths = [repo / "client/tests/gameplay_load_client.gd", repo / "client/state/game_store.gd",
                    repo / "client/network/gateway.gd", Path(__file__), Path(__file__).with_suffix(".gd"),
                    repo / "client/tests/ready_frame_proxy.py", repo / "client/tests/fixture_runtime.py",
                    repo / "protocol/realtime/v1/realtime.proto"]
    inputs = {str(path.relative_to(repo)): sha(path) for path in source_paths}
    profile = {"profiles": ["OFFLINE", "POSTGRES"], "case_deadline_seconds": 95,
               "server_ready_deadline_seconds": 30, "server_shutdown_grace_seconds": 10,
               "botfill_seconds": 30, "ready_deadline_seconds": 15, "load_matchmaking_deadline_seconds": 60,
               "load_cleanup_verification_deadline_seconds": 22, "original_rate_limits": True, "local_terminal_required": True,
               "case_ids": {case: CASES[case][0] for case in selected}, "Accepted": False,
               "remaining_profiles": ["LIVE", "MAIN_INDEPENDENT_ADJUDICATION"],
               "server_create_skill": "Missing; prior user exception applies; actual server/AGENTS.md and canonical docs read",
               "synthetic_fixture": "late_accepted_before_ticket only; SupportOnly, actual decoder/event entry; no internal state prefills"}
    profile["owned_asset_fixture"] = "After actual login, seed one new White Fire Feet armor and initial Mage loadout; real bootstrap loads it before preparation. No history, balances or ledger repairs."
    (work / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    (work / "inputs.json").write_text(json.dumps({"source_sha": source_sha, "source_dirty": dirty,
        "input_hashes": inputs, "plan_sha256": sha(plan), "profile_sha256": sha(work / "profile.json")}, indent=2) + "\n")
    fixture_sources = work / "fixture-sources"
    for path in source_paths + [plan]:
        target = fixture_sources / path.relative_to(repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    canonical = json.loads(plan.read_text())
    canonical_rows = []
    def collect_rows(value):
        if isinstance(value, dict):
            if value.get("id") in ("LOAD-04.4", "PR13-A04.4", "PR13-A03.4"):
                canonical_rows.append(value)
            for nested in value.values():
                collect_rows(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_rows(nested)
    collect_rows(canonical)
    (work / "canonical-cases.raw.json").write_text(json.dumps(canonical_rows, ensure_ascii=False, indent=2) + "\n")
    profile["real_frame_proxy"] = "Selected ready_* cases only; transparent loopback relay, actual binary envelope capture/drop, no synthetic command/event encoding. Boundary PostgreSQL reads only."
    profile["canonical_limitations"] = ["LIVE not run", "same-account three cycles not run", "old-cycle events not covered", "manual independent adjudication pending"]
    profile["canonical_mapping_scope"] = "New loss/send matrix subcases; original canonical rows copied verbatim, their complete execution state is unchanged."
    (work / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    input_record = json.loads((work / "inputs.json").read_text())
    input_record["profile_sha256"] = sha(work / "profile.json")
    (work / "inputs.json").write_text(json.dumps(input_record, indent=2) + "\n")
    ok = False
    error = None
    try:
        # All stale compiler outputs are removed in the actual source tree.
        removed = []
        for path in sorted((path for path in (repo / "server").rglob("*") if path.is_dir() and path.name in ("bin", "obj")),
                           key=lambda path: len(path.parts), reverse=True):
            if path.exists():
                removed.append(str(path.relative_to(repo)))
                shutil.rmtree(path)
        (work / "removed-build-outputs.json").write_text(json.dumps(removed, indent=2) + "\n")
        code, _ = run([args.dotnet, "build", "FantasyCard.Server.slnx", "-c", "Release", "-v", "minimal"],
                      "fresh-source-build", cwd=repo / "server", timeout=180)
        if code:
            raise RuntimeError("Fresh actual source build failed")
        dll = repo / "server/src/FantasyCard.Server/bin/Release/net10.0/FantasyCard.Server.dll"
        # A compact project copies production dependencies verbatim; no UI/art
        # assets or theme changes. Fonts are dependencies of production Game.
        project = work / "godot"
        for folder in ("network", "state", "platform", "data", "ui"):
            for source in (repo / "client" / folder).rglob("*"):
                if source.is_file() and source.suffix in (".gd", ".json"):
                    target = project / source.relative_to(repo / "client")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
        for filename in ("SourceHanSansSC-Regular.otf", "SourceHanSerifSC-SemiBold.otf"):
            target = project / "assets/fonts" / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / "client/assets/fonts" / filename, target)
        (project / "tests").mkdir()
        for filename in ("gameplay_load_client.gd", "run_ready_stop_faults.gd"):
            shutil.copyfile(repo / "client/tests" / filename, project / "tests" / filename)
        # Avoid importing unrelated copied UI scripts with their asset preloads.
        for source in (project / "ui").glob("*.gd"):
            if source.name not in ("palette.gd", "card_details.gd"):
                source.unlink()
        project_config = 'config_version=5\n[application]\nconfig/name="PR13 READY STOP offline"\n[platform]\ndevelopment/local_auth=true\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
        # Import font dependencies before registering the real autoload. A fresh
        # editor otherwise parses Game before it has created fontdata resources.
        (project / "project.godot").write_text(project_config)
        import_env = isolated_environment(work, FANTASYCARD_SERVER_URL="http://127.0.0.1:1", FANTASYCARD_LOAD_RUN_ID="ready-stop-import")
        code, output = run([args.godot, "--headless", "--path", str(project), "--editor", "--import", "--quit"], "godot-import", env=import_env)
        if code or "SCRIPT ERROR" in output:
            raise RuntimeError("Godot fixture import failed")
        (project / "project.godot").write_text(project_config + '[autoload]\nGame="*res://state/game_store.gd"\n')
        copied_inputs = []
        for path in sorted(project.rglob("*")):
            if path.is_file() and ".godot" not in path.relative_to(project).parts:
                source = repo / "client" / path.relative_to(project)
                copied_inputs.append({"fixture_path": str(path.relative_to(work)), "sha256": sha(path),
                                      "source_path": str(source.relative_to(repo)) if source.exists() else None,
                                      "source_sha256": sha(source) if source.exists() else None,
                                      "copied_unchanged": source.exists() and sha(source) == sha(path),
                                      "kind": "generated_import_metadata" if path.suffix == ".uid" else "generated_project_config" if path.name == "project.godot" else "copied_source_input"})
        (work / "fixture-inputs.json").write_text(json.dumps(copied_inputs, indent=2) + "\n")
        code, _ = run(["initdb", "-D", str(pgdata), "-U", "ready_stop_owner", "--auth=trust", "--no-locale", "--encoding=UTF8"], "private-pg-init", timeout=30)
        if code:
            raise RuntimeError("Owned PostgreSQL initialization failed")
        code, _ = run(["pg_ctl", "-D", str(pgdata), "-l", str(work / "private-pg.log"), "-o",
                       "-c listen_addresses='' -k " + str(pg_socket), "-w", "start"], "private-pg-start", timeout=30)
        if code:
            raise RuntimeError("Owned Unix PostgreSQL start failed")
        pg_started = True
        (work / "toolchain.json").write_text(json.dumps({"dotnet": subprocess.check_output([args.dotnet, "--version"]).decode().strip(),
            "godot": subprocess.check_output([args.godot, "--version"]).decode().strip(),
            "postgres": subprocess.check_output(["postgres", "--version"]).decode().strip(),
            "server_dll_sha256": sha(dll), "transport": "PostgreSQL owned Unix socket; Program/Godot loopback HTTP binary Protobuf"}, indent=2) + "\n")
        for index, case in enumerate(selected):
            directory = work / case
            directory.mkdir()
            database = "ready_stop_" + uuid.uuid4().hex
            sql("CREATE DATABASE " + database)
            with socket.socket() as socket_probe:
                socket_probe.bind(("127.0.0.1", 0))
                port = socket_probe.getsockname()[1]
            address = "http://127.0.0.1:" + str(port)
            env = isolated_environment(directory, ASPNETCORE_ENVIRONMENT="Development", ASPNETCORE_URLS=address,
                ConnectionStrings__Postgres="Host=" + str(pg_socket) + ";Database=" + database + ";Username=ready_stop_owner",
                Identity__EnableLocalAuth="true", ProtobufHttp__AllowLegacyJson="false", Realtime__AllowLegacyAccessTokenQuery="false",
                FANTASYCARD_SERVER_URL=address, FANTASYCARD_LOAD_RUN_ID="ready-stop-offline",
                FANTASYCARD_LOAD_CLIENT_ID=case, FANTASYCARD_LOAD_PROCESS_EPOCH=str(index),
                FANTASYCARD_LOAD_REPORT=str(directory / "client.json"), FANTASYCARD_LOAD_STOP_FILE=str(directory / "STOP"),
                FANTASYCARD_READY_STOP_CASE=case, FANTASYCARD_LOAD_MAX_CYCLES="1",
                Logging__LogLevel__Default="Warning", Logging__LogLevel__FantasyCard="Warning")
            for key in list(env):
                if key.startswith("OTEL_EXPORTER_") or key.startswith("Matchmaking__") or key.startswith("RequestLimits__"):
                    env.pop(key)
            # Restore the actual production 30s default; Development config's
            # zero-second botfill would shortcut the queued/READY fault window.
            env["Matchmaking__BotFillDelaySeconds"] = "30"
            server_log = (directory / "server.log").open("wb")
            server = subprocess.Popen([args.dotnet, str(dll)], cwd=repo / "server/src/FantasyCard.Server", env=env,
                                      stdout=server_log, stderr=subprocess.STDOUT)
            ready = False
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and server.poll() is None:
                try:
                    with urlopen(address + "/health/ready", timeout=.5) as response:
                        ready = response.status == 200
                except Exception:
                    pass
                if ready:
                    break
                time.sleep(.2)
            if not ready:
                raise RuntimeError("Owned full Program failed startup")
            if case in TRANSPORT_CASES:
                proxy_command = [sys.executable, str(repo / "client/tests/ready_frame_proxy.py"), "--upstream-port", str(port),
                                 "--case", case, "--evidence", str(directory / "transport"), "--database", database]
                proxy_log = (directory / "proxy.log").open("wb")
                proxy_env = dict(env, **{key: pg_env[key] for key in ("PGHOST", "PGUSER", "PGPORT")})
                for key in ("PGOPTIONS", "PGPASSWORD", "PGSERVICE", "PGSERVICEFILE"):
                    proxy_env.pop(key, None)
                proxy = subprocess.Popen(proxy_command, cwd=repo, env=proxy_env,
                                         stdout=proxy_log, stderr=subprocess.STDOUT)
                proxy_deadline = time.monotonic() + 10
                while proxy.poll() is None and not (directory / "transport/ready.json").exists() and time.monotonic() < proxy_deadline:
                    time.sleep(.05)
                if proxy.poll() is not None or not (directory / "transport/ready.json").exists():
                    raise RuntimeError("Owned actual frame proxy startup failed")
                proxy_port = json.loads((directory / "transport/ready.json").read_text())["port"]
                env["FANTASYCARD_SERVER_URL"] = "http://127.0.0.1:" + str(proxy_port)
                commands.append({"label": case + "-frame-proxy-start", "command": proxy_command, "cwd": str(repo),
                                 "exit_code": None, "status": "started", "pid": proxy.pid, "deadline_seconds": 10})
            fixture_seeded = False
            def seed_owned_fixture():
                nonlocal fixture_seeded
                login_path = directory / "fixture-login.json"
                if fixture_seeded or not login_path.exists():
                    return
                player = str(uuid.UUID(json.loads(login_path.read_text())["player_id"]))
                equipment = str(uuid.uuid4())
                sql("BEGIN; INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,created_at,element,secondary_trait) VALUES ('" + equipment + "','" + player + "','Feet','White',0,true,'Equipped',CURRENT_TIMESTAMP,'Fire','DrawInterval'); UPDATE player_loadouts SET feet_id='" + equipment + "',version=version+1 WHERE player_id='" + player + "' AND hero_class=2; COMMIT", database)
                (directory / "fixture-seeded.json").write_text(json.dumps({"player_id": player, "equipment_id": equipment, "synthetic_initial_asset": True, "history_repair": False}) + "\n")
                fixture_seeded = True
            code, output = run([args.godot, "--headless", "--max-fps", "60", "--path", str(project), "--script", "res://tests/run_ready_stop_faults.gd"],
                               case + "-godot", env=env, timeout=95, during_run=seed_owned_fixture)
            client = json.loads((directory / "client.json").read_text()) if (directory / "client.json").exists() else {}
            stop_proxy()
            transport = [json.loads(line) for line in (directory / "transport/trace.jsonl").read_text().splitlines()] if case in TRANSPORT_CASES else []
            dropped = [item for item in transport if item["event"] == "frame_dropped"]
            forwarded = [item for item in transport if item["event"] == "frame_forwarded"]
            transport_ok = not any(item["event"] == "proxy_error" for item in transport)
            if case in TRANSPORT_CASES:
                transport_ok = transport_ok and bool(dropped) and any(item["event"] == "proxy_stopped" and item["remaining_connections"] == 0 for item in transport)
                if case.startswith("ready_send_"):
                    transport_ok = transport_ok and all(item["kind"] == "room.ready" and len(item["postgres_at_drop"]) == 1 and item["postgres_at_drop"][0]["player_state"] == "Assigned" and item["postgres_at_drop"][0]["status"] == "Starting" for item in dropped)
                    if case == "ready_send_all_lost_stop":
                        transport_ok = transport_ok and len(dropped) == 3 and not any(item["kind"] == "room.ready" for item in forwarded)
                    else:
                        transport_ok = transport_ok and len(dropped) == 1 and any(item["kind"] == "room.ready" for item in forwarded)
                else:
                    expected_drops = {"room.ready_accepted"} if case == "ready_accepted_lost_resume" else {"room.started"} if case == "ready_started_lost_reconnect" else {"room.ready_accepted", "room.started"}
                    transport_ok = transport_ok and {item["kind"] for item in dropped} == expected_drops and all(len(item["postgres_at_drop"]) == 1 and item["postgres_at_drop"][0]["player_state"] in ("Ready", "Active") for item in dropped)
                    transport_ok = transport_ok and any(item["kind"] == "session.resume" for item in forwarded)
                    # The exact stored event must be replayed, not a replacement
                    # event invented by the fixture or merely a matching kind.
                    transport_ok = transport_ok and all(any(item["kind"] == lost["kind"] and item["sequence"] == lost["sequence"] and item["sha256"] == lost["sha256"] and item["ordinal"] > lost["ordinal"] for item in forwarded) for lost in dropped)
                if case.endswith("reconnect"):
                    transport_ok = transport_ok and any(item["event"] == "fault_disconnect" for item in transport) and len([item for item in forwarded if item["kind"] == "session.connected"]) >= 2
                if case != "ready_send_all_lost_stop":
                    transport_ok = transport_ok and all(item["postgres_at_drop"][0]["match_id"] == client.get("observed_match_id") and item["postgres_at_drop"][0]["room_id"] == client.get("observed_room_id") for item in dropped)
            # Read-only postconditions. Do not repair fixture balances/ledger/history.
            snapshot = json.loads(sql("SELECT json_build_object('preparations',(SELECT coalesce(json_agg(json_build_object('status',status)), '[]'::json) FROM preparations),"
                "'tickets',(SELECT coalesce(json_agg(json_build_object('status',status)), '[]'::json) FROM match_tickets),"
                "'human_match_states',(SELECT coalesce(json_agg(json_build_object('state',state)), '[]'::json) FROM match_players WHERE NOT is_bot),"
                "'locked_equipment',(SELECT count(*) FROM equipments WHERE location IN ('PreparationLocked','InMatchEquipped','InMatchBackpack')),"
                "'preparation_asset_rows',(SELECT count(*) FROM preparation_assets),"
                "'equipment_locks',(SELECT count(*) FROM inventory_movements WHERE reason='preparation.lock'),"
                "'equipment_releases',(SELECT count(*) FROM inventory_movements WHERE reason='preparation.release'),"
                "'pending_settlement_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),"
                "'settlements',(SELECT count(*) FROM match_settlements),"
                "'rooms',(SELECT count(*) FROM room_snapshots),"
                "'matches',(SELECT count(*) FROM matches),"
                "'match_rows',(SELECT coalesce(json_agg(json_build_object('match_id',match_id,'room_id',room_id,'status',status,'created_at_unix_ms',extract(epoch from created_at)*1000,'ready_deadline_unix_ms',extract(epoch from ready_deadline)*1000,'observed_at_unix_ms',extract(epoch from CURRENT_TIMESTAMP)*1000)), '[]'::json) FROM matches),"
                "'ready_deadline_seconds',(SELECT coalesce(json_agg(extract(epoch from ready_deadline-created_at)), '[]'::json) FROM matches))", database))
            (directory / "postgres-postconditions.json").write_text(json.dumps(snapshot, indent=2) + "\n")
            db_ok = fixture_seeded and snapshot["equipment_locks"] == 1 and snapshot["pending_settlement_holds"] == 0 and all(item["status"] in ("Cancelled", "Expired", "Settled") for item in snapshot["preparations"]) and snapshot["locked_equipment"] == 0 and all(item["state"] in ("Settled", "Removed") for item in snapshot["human_match_states"])
            if case in TRANSPORT_CASES:
                # Even an all-removed human lobby launches an owned bot room.
                # Human membership, route and asset release are the terminal
                # conditions; deleting that bot room would change production.
                db_ok = db_ok and snapshot["matches"] == 1 and snapshot["rooms"] == 1 and snapshot["ready_deadline_seconds"] == [15]
                if case == "ready_send_all_lost_stop":
                    db_ok = db_ok and snapshot["human_match_states"] == [{"state": "Removed"}] and snapshot["equipment_releases"] == 1 and snapshot["settlements"] == 0 and snapshot["match_rows"][0]["observed_at_unix_ms"] >= snapshot["match_rows"][0]["ready_deadline_unix_ms"]
            passed = code == 0 and client.get("passed", False) and db_ok and transport_ok and "SCRIPT ERROR" not in output and "ERROR:" not in output
            (directory / "case.raw.json").write_text(json.dumps({"client": client, "postgres": snapshot, "transport": transport, "command_exit_code": code}, indent=2) + "\n")
            cases.append({"case": case, "canonical_case_id": CASES[case][0], "expected": CASES[case][1], "actual": client,
                          "postgres": snapshot, "postgres_passed": db_ok, "passed": passed, "Accepted": False,
                          "source_sha": source_sha, "source_dirty": dirty, "input_hashes": inputs,
                          "remaining_profiles": profile["remaining_profiles"], "exit_code": code,
                          "transport_passed": transport_ok, "coverage": client.get("coverage", "Unknown"),
                          "evidence": [case + "/client.json", case + "/postgres-postconditions.json", case + "-godot.log", case + "/server.log"]})
            print(case + ": " + ("PASS" if passed else "FAIL"), flush=True)
            (work / "cases.jsonl").write_text("".join(json.dumps(case_record, ensure_ascii=False) + "\n" for case_record in cases))
            stop_server()
        ok = len(cases) == len(selected) and all(case["passed"] for case in cases)
    except Exception as exc:
        error = str(exc)
        print(type(exc).__name__ + ": " + error, flush=True)
    finally:
        stop_proxy()
        stop_server()
        if pg_started:
            run(["pg_ctl", "-D", str(pgdata), "-m", "fast", "-w", "stop"], "owned-pg-cleanup", timeout=30)
        shutil.rmtree(pg_socket)
        (work / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        (work / "report.json").write_text(json.dumps({"ok": ok, "Accepted": False, "error": error,
            "source_sha": source_sha, "source_dirty": dirty, "case_count": len(cases), "planned_case_count": len(selected),
            "passed_case_count": sum(case["passed"] for case in cases), "cases": cases,
            "remaining_profiles": profile["remaining_profiles"], "original_raw_preserved": True,
            "uploads": [], "owned_server_stopped": server is None, "owned_postgres_stopped": not (pgdata / "postmaster.pid").exists()}, indent=2) + "\n")
        # Compiler/project caches and PG cluster bytes are support workspace, not
        # the exported evidence. Logs/results/source manifests remain immutable.
        evidence = [path for path in work.rglob("*") if path.is_file() and not any(part in ("godot", "runtime", "private-pg") for part in path.relative_to(work).parts)]
        (work / "manifest.json").write_text(json.dumps([{ "path": str(path.relative_to(work)), "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(evidence)], indent=2) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
