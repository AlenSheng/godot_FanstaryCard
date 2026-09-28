"""Validate a protected Docker image using its matching private build stage."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import secrets
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET

from release_protection import PRIVATE, ROOT, sha256


ASSEMBLIES = ("FantasyCard.Contracts", "FantasyCard.Domain", "FantasyCard.Server")
SUITES = ("FantasyCard.Domain.Tests", "FantasyCard.Server.Tests")


def command(*args, log=None, check=True, timeout=600):
    if log:
        with log.open("w", encoding="utf-8") as output:
            result = subprocess.run(args, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
    else:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed; " + (str(log) if log else result.stderr[-3000:]))
    return result


def docker(*args, **kwargs):
    return command("docker", *args, **kwargs)


def status(url, body=None, request_timeout=3, media_type="application/json"):
    request = urllib.request.Request(url, data=body, headers={"Content-Type": media_type, "Accept": media_type})
    try:
        with urllib.request.urlopen(request, timeout=request_timeout) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return 0


def wait_for(predicate, label, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.5)
    raise RuntimeError("Timed out waiting for " + label)


def prepare_tests(evidence):
    config = ET.parse(ROOT / "server/protection/obfuscar.xml")
    root = config.getroot()
    for variable in root.findall("Var"):
        value = {"InPath": "/unprotected", "OutPath": "/test-protected",
                 "LogFile": "/evidence/test-mapping.xml"}.get(variable.get("name"))
        if value:
            variable.set("value", value)
    for suite in SUITES:
        directory = f"/src/artifacts/acceptance/bin/{suite}/release"
        ET.SubElement(root, "AssemblySearchPath", path=directory)
        module = ET.SubElement(root, "Module", file=f"{directory}/{suite}.dll")
        ET.SubElement(module, "SkipType", name="*", skipMethods="true", skipFields="true",
                      skipProperties="true", skipEvents="true", skipStringHiding="true")
    config.write(evidence / "test-obfuscar.xml", encoding="utf-8", xml_declaration=True)
    # Explicit LF also supports checkouts configured with core.autocrlf=true.
    with (evidence / "tests.sh").open("w", encoding="utf-8", newline="\n") as output:
        output.write((ROOT / "tools/docker_protection_tests.sh").read_text(encoding="utf-8"))
    smoke = evidence / "smoke"
    smoke.mkdir()
    shutil.copy2(ROOT / "tools/docker_protection_smoke.cs", smoke / "Program.cs")
    (smoke / "Smoke.csproj").write_text('''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework><OutputType>Exe</OutputType>
    <ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <FrameworkReference Include="Microsoft.AspNetCore.App" />
    <Reference Include="FantasyCard.Contracts"><HintPath>/evidence/image-app/FantasyCard.Contracts.dll</HintPath></Reference>
    <Reference Include="Google.Protobuf"><HintPath>/evidence/image-app/Google.Protobuf.dll</HintPath></Reference>
    <Reference Include="Npgsql"><HintPath>/evidence/image-app/Npgsql.dll</HintPath></Reference>
  </ItemGroup>
</Project>
''', encoding="utf-8")


def validate(image_tag, builder_tag):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix="docker-acceptance-", dir=PRIVATE))
    print("Evidence: " + str(evidence), flush=True)
    token = "fc-accept-" + uuid.uuid4().hex[:12]
    network = token + "-net"
    database, server, runner, production = [token + suffix for suffix in ("-db", "-server", "-tests", "-production")]
    containers = []
    network_created = False
    report = {"ok": False, "started_at": datetime.now(timezone.utc).isoformat(), "evidence": str(evidence)}
    try:
        image = json.loads(docker("image", "inspect", image_tag).stdout)[0]
        builder = json.loads(docker("image", "inspect", builder_tag).stdout)[0]
        if image["Os"] != "linux" or image["Config"].get("User") in (None, "", "0", "root", "0:0"):
            raise ValueError("Expected a Linux image with a non-root runtime user.")
        report.update(image=image["Id"], image_tag=image_tag, image_digests=image["RepoDigests"],
                      builder=builder["Id"], platform=image["Os"] + "/" + image["Architecture"])
        docker("network", "create", network)
        network_created = True
        connection = "Host=postgres;Port=5432;Database=acceptance;Username=acceptance;Pooling=false"
        runtime_connection = connection + ";Timeout=2;Command Timeout=2"
        docker("run", "-d", "--name", database, "--network", network, "--network-alias", "postgres",
               "--tmpfs", "/var/lib/postgresql", "-e", "POSTGRES_USER=acceptance",
               "-e", "POSTGRES_DB=acceptance", "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:18-alpine")
        containers.append(database)
        wait_for(lambda: docker("exec", database, "pg_isready", "-U", "acceptance", "-d", "acceptance", check=False).returncode == 0,
                 "isolated PostgreSQL")
        postgres_image = json.loads(docker("inspect", database).stdout)[0]["Image"]
        report["postgres_image"] = postgres_image
        report["postgres_version"] = docker("exec", database, "postgres", "--version").stdout.strip()

        docker("create", "--name", server, "--network", network, "--network-alias", "server",
               "-p", "127.0.0.1::8080", "-e", "ASPNETCORE_ENVIRONMENT=Development",
               "-e", "Identity__EnableLocalAuth=true", "-e", "AllowedHosts=server;localhost;127.0.0.1",
               "-e", "ConnectionStrings__Postgres=" + runtime_connection, image["Id"])
        containers.append(server)
        docker("cp", server + ":/app", str(evidence / "image-app"))
        app = evidence / "image-app"
        forbidden = [str(path.relative_to(app)) for path in app.rglob("*") if path.is_file() and
                     (path.suffix.lower() in {".cs", ".pdb", ".key", ".dpapi", ".csproj", ".sln", ".slnx"}
                      or "mapping" in path.name.lower() or "test" in path.name.lower()
                      or "obfuscar" in path.name.lower() or path.name == "appsettings.Development.json")]
        if forbidden:
            raise ValueError("Unexpected deployment files: " + ", ".join(forbidden))
        report["assemblies"] = {name + ".dll": sha256(app / (name + ".dll")) for name in ASSEMBLIES}
        archive = evidence / "runtime-filesystem.tar"
        docker("export", "-o", str(archive), server)
        with tarfile.open(archive) as contents:
            leaked = [entry.name for entry in contents if entry.name.split("/", 1)[0] in
                      {"src", "input", "output", "private", "framework", "obfuscar"}]
        if leaked:
            raise ValueError("Builder-only files leaked into runtime image.")
        key_path = ROOT / "release-encryption.key"
        if key_path.exists():
            key = key_path.read_bytes().strip()
            if key:
                tail = b""
                with archive.open("rb") as content:
                    while chunk := content.read(1024 * 1024):
                        block = tail + chunk
                        if key in block:
                            raise ValueError("Root encryption key leaked into runtime filesystem.")
                        tail = block[-len(key):]
        report["package_checks"] = {"forbidden_files": [], "builder_files_absent": True,
                                    "root_key_scan": "passed" if key_path.exists() else "key not present locally"}
        archive.unlink()
        prepare_tests(evidence)
        docker("run", "-d", "--name", runner, "--network", network,
               "--mount", f"type=bind,source={evidence},target=/evidence",
               "-e", "FANTASYCARD_TEST_POSTGRES=" + connection,
               "-e", "FANTASYCARD_E2E_SERVER_DLL=/evidence/image-app/FantasyCard.Server.dll",
               builder["Id"], "sleep", "infinity")
        containers.append(runner)
        originals = {}
        for name in ASSEMBLIES:
            built = docker("exec", runner, "sha256sum", "/input/" + name + ".dll").stdout.split()[0]
            if built != report["assemblies"][name + ".dll"]:
                raise ValueError("The runtime and private builder are not from the same build: " + name)
            originals[name + ".dll"] = docker("exec", runner, "sha256sum",
                f"/src/src/{name}/bin/Release/net10.0/{name}.dll").stdout.split()[0]
            if originals[name + ".dll"] == built:
                raise ValueError("Obfuscation did not change " + name)
        report["original_assemblies"] = originals
        print("Running the full Linux test suites against final-image assemblies...", flush=True)
        test_run = docker("exec", runner, "sh", "/evidence/tests.sh", log=evidence / "tests.log", check=False)
        counters = {key: 0 for key in ("total", "passed", "failed", "notExecuted")}
        for trx in (evidence / "results").glob("*.trx"):
            element = ET.parse(trx).find(".//{*}Counters")
            if element is not None:
                for key in counters:
                    counters[key] += int(element.get(key, "0"))
        report["tests"] = counters
        if test_run.returncode or counters["total"] == 0 or counters["total"] != counters["passed"]:
            raise RuntimeError("Linux tests failed or skipped; inspect tests.log and results/*.trx")
        print("Linux tests passed: " + str(counters["passed"]), flush=True)
        docker("exec", runner, "dotnet", "build", "/evidence/smoke/Smoke.csproj", "-c", "Release",
               "-o", "/smoke", log=evidence / "smoke-build.log")
        docker("start", server)
        port = docker("port", server, "8080/tcp").stdout.strip().rsplit(":", 1)[1]
        base = "http://127.0.0.1:" + port
        wait_for(lambda: status(base + "/health/ready") == 200, "runtime image readiness")
        uid = docker("exec", server, "id", "-u").stdout.strip()
        if uid == "0":
            raise ValueError("Runtime process is root.")
        report["runtime_uid"] = uid
        for phase in ("before", "after"):
            if phase == "after":
                docker("kill", server)
                docker("start", server)
                # Docker can allocate a different ephemeral host port on start.
                port = docker("port", server, "8080/tcp").stdout.strip().rsplit(":", 1)[1]
                base = "http://127.0.0.1:" + port
                wait_for(lambda: status(base + "/health/ready") == 200, "restarted runtime image")
            docker("exec", runner, "dotnet", "/smoke/Smoke.dll", phase, log=evidence / ("smoke-" + phase + ".log"))
            report["smoke_" + phase] = json.loads((evidence / ("smoke-" + phase + ".json")).read_text())
        print("Runtime HTTP/WebSocket and forced-restart checks passed.", flush=True)
        # SIGSTOP simulates a DB outage without destroying the tmpfs test database.
        docker("pause", database)
        try:
            wait_for(lambda: status(base + "/health/ready", request_timeout=10) == 503, "unhealthy database readiness", seconds=45)
            if status(base + "/health/live") != 200:
                raise ValueError("Liveness should remain healthy during DB outage.")
        finally:
            docker("unpause", database)
        wait_for(lambda: status(base + "/health/ready") == 200, "database recovery")
        report["database_outage"] = {"ready": 503, "live": 200, "recovered": 200}
        docker("stop", server)
        docker("run", "-d", "--name", production, "--network", network, "-p", "127.0.0.1::8080",
               "-e", "ASPNETCORE_ENVIRONMENT=Production", "-e", "Identity__EnableLocalAuth=false",
               "-e", "Admin__ApiKey=" + secrets.token_hex(32),
               "-e", "ConnectionStrings__Postgres=" + runtime_connection, image["Id"])
        containers.append(production)
        production_port = docker("port", production, "8080/tcp").stdout.strip().rsplit(":", 1)[1]
        production_base = "http://127.0.0.1:" + production_port
        wait_for(lambda: status(production_base + "/health/ready") == 200, "production-mode readiness")
        denied = status(production_base + "/api/v1/auth/local", b"", media_type="application/protobuf")
        if denied != 404:
            raise ValueError("Local authentication was not disabled in production mode.")
        report["production_local_auth_status"] = denied
        for name, digest in report["assemblies"].items():
            if sha256(app / name) != digest:
                raise ValueError("Final-image assembly changed during validation: " + name)
        report["ok"] = True
    except Exception as error:
        report["error"] = str(error)
    finally:
        cleanup = []
        for container in reversed(containers):
            docker("logs", container, log=evidence / (container + ".log"), check=False)
            outcome = docker("rm", "-f", "-v", container, check=False)
            if outcome.returncode:
                cleanup.append(container)
        if network_created and docker("network", "rm", network, check=False).returncode:
            cleanup.append(network)
        report["cleanup"] = {"ok": not cleanup, "remaining": cleanup,
                             "database": "isolated tmpfs removed; existing Docker workloads untouched"}
        if cleanup:
            report["ok"] = False
        (evidence / "smoke-state.json").unlink(missing_ok=True)
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        (evidence / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return report["ok"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Protected runtime image tag or ID")
    parser.add_argument("--builder-image", required=True, help="Matching Dockerfile --target build image")
    args = parser.parse_args()
    return 0 if validate(args.image, args.builder_image) else 1


if __name__ == "__main__":
    raise SystemExit(main())
