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
}


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

    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo).decode().strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo).decode().splitlines()
    plan = repo / "docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json"
    source_paths = [repo / "client/tests/gameplay_load_client.gd", repo / "client/state/game_store.gd",
                    repo / "client/network/gateway.gd", Path(__file__), Path(__file__).with_suffix(".gd")]
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
                "'ready_deadline_seconds',(SELECT coalesce(json_agg(extract(epoch from ready_deadline-created_at)), '[]'::json) FROM matches))", database))
            (directory / "postgres-postconditions.json").write_text(json.dumps(snapshot, indent=2) + "\n")
            db_ok = fixture_seeded and snapshot["equipment_locks"] == 1 and snapshot["pending_settlement_holds"] == 0 and all(item["status"] in ("Cancelled", "Expired", "Settled") for item in snapshot["preparations"]) and snapshot["locked_equipment"] == 0 and all(item["state"] in ("Settled", "Removed") for item in snapshot["human_match_states"])
            passed = code == 0 and client.get("passed", False) and db_ok and "SCRIPT ERROR" not in output and "ERROR:" not in output
            cases.append({"case": case, "canonical_case_id": CASES[case][0], "expected": CASES[case][1], "actual": client,
                          "postgres": snapshot, "postgres_passed": db_ok, "passed": passed, "Accepted": False,
                          "source_sha": source_sha, "source_dirty": dirty, "input_hashes": inputs,
                          "remaining_profiles": profile["remaining_profiles"], "exit_code": code,
                          "evidence": [case + "/client.json", case + "/postgres-postconditions.json", case + "-godot.log", case + "/server.log"]})
            print(case + ": " + ("PASS" if passed else "FAIL"), flush=True)
            (work / "cases.jsonl").write_text("".join(json.dumps(case_record, ensure_ascii=False) + "\n" for case_record in cases))
            stop_server()
        ok = len(cases) == len(selected) and all(case["passed"] for case in cases)
    except Exception as exc:
        error = str(exc)
        print(type(exc).__name__ + ": " + error, flush=True)
    finally:
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
