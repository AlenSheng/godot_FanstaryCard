"""Run the existing suites against protected DLLs and an isolated local PostgreSQL."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from release_protection import PRIVATE, ROOT, sha256


def validate(report_path, postgres_bin):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    package = Path(report["output"]).resolve()
    if not package.is_relative_to(ROOT / "builds/server-protected"):
        raise ValueError("Validation target must be a protected server build in this project.")
    suites = [Path(value) for value in report["test_assemblies"]]
    for name, hashes in report["assemblies"].items():
        if sha256(package / name) != hashes["protected_sha256"]:
            raise ValueError("Packaged server hash mismatch: " + name)
        for suite in suites:
            dependency = suite.parent / name
            if dependency.is_file() and sha256(dependency) != hashes["protected_sha256"]:
                raise ValueError("Test suite is not using the protected package: " + str(dependency))
    for binary in ("initdb.exe", "pg_ctl.exe"):
        if not (postgres_bin / binary).is_file():
            raise ValueError("PostgreSQL executable missing: " + str(postgres_bin / binary))
    working = Path(tempfile.mkdtemp(prefix="server-validation-", dir=PRIVATE))
    data = working / "pgdata"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with (working / "initdb.log").open("w", encoding="utf-8") as log:
        subprocess.run([str(postgres_bin / "initdb.exe"), "-D", str(data), "-U", "protection_test",
                        "-A", "trust", "--no-locale", "-E", "UTF8"], stdout=log, stderr=subprocess.STDOUT, check=True)
    pg_ctl = str(postgres_bin / "pg_ctl.exe")
    started = False
    try:
        subprocess.run([pg_ctl, "-D", str(data), "-w", "-l", str(working / "postgres.log"),
                        "-o", f"-h 127.0.0.1 -p {port} -F", "start"], check=True, timeout=60)
        started = True
        env = os.environ.copy()
        env["FANTASYCARD_TEST_POSTGRES"] = f"Host=127.0.0.1;Port={port};Database=postgres;Username=protection_test;Pooling=false"
        env["FANTASYCARD_E2E_SERVER_DLL"] = str(package / "FantasyCard.Server.dll")
        results = working / "results"
        with (working / "tests.log").open("w", encoding="utf-8") as log:
            run = subprocess.run(["dotnet", "vstest", *map(str, suites), "--Logger:trx",
                                  "--ResultsDirectory:" + str(results)], cwd=ROOT / "server", env=env,
                                 stdout=log, stderr=subprocess.STDOUT, timeout=600)
        totals = {key: 0 for key in ("total", "passed", "failed", "notExecuted")}
        for trx in results.glob("*.trx"):
            counters = ET.parse(trx).find(".//{*}Counters")
            if counters is not None:
                for key in totals:
                    totals[key] += int(counters.get(key, "0"))
        success = run.returncode == 0 and totals["total"] > 0 and totals["passed"] == totals["total"]
        verification = {"ok": success, "tests": totals, "package": str(package),
                        "assemblies": report["assemblies"], "evidence": str(working),
                        "database": "fresh localhost-only test cluster; stopped after validation"}
        (working / "verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
        if not success:
            raise ValueError("Protected server validation failed or skipped tests; inspect " + str(working / "tests.log"))
        (package / "protection-verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
        (package / "CANDIDATE-NOT-YET-VALIDATED.txt").unlink(missing_ok=True)
        report["tested"] = True
        report["verification"] = verification
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return verification
    finally:
        if started:
            subprocess.run([pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop"], check=True, timeout=60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Private report.json from export_protected_server.py")
    parser.add_argument("--postgres-bin", type=Path, default=PRIVATE / "postgres/pgsql/bin")
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.report, args.postgres_bin.resolve()), indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
