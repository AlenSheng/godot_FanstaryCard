"""Controlled test-server rollout. Uses the existing compose, env file and update lock.

Run only as ubuntu on 43.172.70.182 through the approved Actions environment.
No credentials, database dumps or application logs are emitted to Actions artifacts.
"""
import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import re
import signal
import subprocess
import time

REPO = pathlib.Path("/opt/fantasycard-github")
APP = pathlib.Path("/opt/fantasycard-app")
COMPOSE = REPO / "server/compose.cloud.yaml"
ENV_FILE = REPO / "server/.env"
LOCK = pathlib.Path("/tmp/fantasycard-update.lock")
BLOCKED_PATHS = (
    "server/src/FantasyCard.Server/Persistence", "server/compose.cloud.yaml",
    "server/Caddyfile", "server/site", "server/monitoring", "server/deploy",
    "server/src/FantasyCard.Server/appsettings.json", "server/Directory.Build.props",
    "server/Directory.Packages.props", "server/global.json", "server/NuGet.Config",
)


def digest(path):
    value = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def run(*arguments, **kwargs):
    # Argument arrays throughout; never interpolate PR input into shell commands.
    return subprocess.run(list(map(str, arguments)), check=True, timeout=kwargs.pop("timeout", 120), **kwargs)


def capture(*arguments):
    return run(*arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()


def validate_manifest(data, source_sha, run_id, controller_sha):
    if data.get("format") != 1 or data.get("repository") != "AlenSheng/godot_FanstaryCard":
        raise ValueError("Unexpected artifact repository or format")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or data.get("source_sha") != source_sha:
        raise ValueError("Artifact source differs from the approved source")
    if data.get("run_id") != run_id or data.get("controller_sha") != controller_sha:
        raise ValueError("Artifact belongs to another run or controller")
    for key in ("archive_sha256", "health_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", data.get(key, "")):
            raise ValueError("Malformed artifact checksum")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", data.get("image_id", "")):
        raise ValueError("Malformed immutable image ID")


def rollout(new_image, old_image, apply, healthy, record, finalize=lambda image: None):
    """After mutation begins, every error attempts the same immutable-image rollback."""
    try:
        record("activating")
        apply(new_image)
        if not healthy():
            raise RuntimeError("New application did not pass existing deployment health checks")
        finalize(new_image)
        record("accepted")
    except BaseException:
        record("rolling_back")
        try:
            apply(old_image)
            restored = healthy()
            if restored:
                finalize(old_image)
        except BaseException:
            restored = False
        record("rolled_back" if restored else "rollback_failed")
        raise


@contextlib.contextmanager
def deployment_lock():
    import fcntl  # Linux only, kept inside the server-only path for portable unit tests.
    with LOCK.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def deploy(bundle, source_sha, run_id, controller_sha):
    import pwd
    if pwd.getpwuid(os.geteuid()).pw_name != "ubuntu":
        raise ValueError("Run as ubuntu; do not elevate the controller process")
    bundle = bundle.resolve(strict=True)
    allowed = (APP / "test-deploy/incoming").resolve(strict=True)
    if not bundle.is_relative_to(allowed):
        raise ValueError("Deployment bundle must stay inside the fixed incoming directory")
    manifest = json.loads((bundle / "manifest.json").read_text())
    validate_manifest(manifest, source_sha, run_id, controller_sha)
    if digest(bundle / "image.tar.gz") != manifest["archive_sha256"] or digest(bundle / "health.sh") != manifest["health_sha256"]:
        raise ValueError("Artifact bytes differ from the tested build")
    if not COMPOSE.is_file() or not ENV_FILE.is_file():
        raise ValueError("Existing test server is not provisioned")
    remote = capture("git", "-C", REPO, "remote", "get-url", "origin")
    if remote not in ("https://github.com/AlenSheng/godot_FanstaryCard.git", "git@github.com:AlenSheng/godot_FanstaryCard.git"):
        raise ValueError("Server checkout is not the canonical repository")
    run("git", "-C", REPO, "diff", "--quiet")
    run("git", "-C", REPO, "diff", "--cached", "--quiet")
    run("git", "-C", REPO, "fetch", "--no-tags", "--filter=blob:none", "origin", source_sha, timeout=300)
    if capture("git", "-C", REPO, "rev-parse", "FETCH_HEAD") != source_sha:
        raise ValueError("Fetched source does not match the approved full SHA")
    state = APP / "test-deploy"
    state.mkdir(exist_ok=True, mode=0o700)
    override = state / "active-image.yaml"
    base = ["sudo", "-n", "docker", "compose", "-f", str(COMPOSE), "--env-file", str(ENV_FILE)]
    if override.exists():
        base += ["-f", str(override)]
    def compose(*arguments, **kwargs):
        return run(*base, *arguments, **kwargs)

    container = compose("ps", "-q", "server", stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{12,64}", container):
        raise ValueError("Expected one running application container")
    old_image = capture("sudo", "-n", "docker", "inspect", "--format", "{{.Image}}", container)
    old_revision = capture("sudo", "-n", "docker", "inspect", "--format", '{{index .Config.Labels "org.opencontainers.image.revision"}}', container)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", old_image) or not re.fullmatch(r"[0-9a-f]{40}", old_revision):
        raise ValueError("Running baseline has no verifiable source/image identity")
    if (APP / "deployed-runtime-commit").read_text().strip() != old_revision:
        raise ValueError("Runtime source marker does not match the running baseline")
    # Same schema, persistence code and deployment configuration are required for automatic rollback.
    run("git", "-C", REPO, "diff", "--quiet", old_revision, source_sha, "--", *BLOCKED_PATHS)
    run("git", "-C", REPO, "diff", "--quiet", "HEAD", old_revision, "--", *BLOCKED_PATHS)
    evidence = {**manifest, "baseline_revision": old_revision, "baseline_image_id": old_image,
                "checkout_sha": capture("git", "-C", REPO, "rev-parse", "HEAD"),
                "controller_sha256": digest(pathlib.Path(__file__)), "events": [], "status": "preflight"}
    result = bundle / "result.json"
    def record(status):
        evidence["status"] = status
        evidence["events"].append({"status": status, "utc_epoch": time.time()})
        temporary = result.with_suffix(".tmp")
        temporary.write_text(json.dumps(evidence, indent=2) + "\n")
        temporary.replace(result)
        # Only known non-secret status strings enter the workflow log.
        print("deployment_status=" + status, flush=True)

    def health():
        for _ in range(24):
            if subprocess.run(["bash", str(bundle / "health.sh")], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=45).returncode == 0:
                return True
            time.sleep(5)
        return False

    def apply(image):
        temporary = override.with_suffix(".tmp")
        temporary.write_text("services:\n  server:\n    image: " + image + "\n")
        temporary.chmod(0o600)
        temporary.replace(override)
        command = ["sudo", "-n", "docker", "compose", "-f", str(COMPOSE), "--env-file", str(ENV_FILE), "-f", str(override)]
        run(*command, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "server", timeout=180)
        current = capture(*command, "ps", "-q", "server")
        if capture("sudo", "-n", "docker", "inspect", "--format", "{{.Image}}", current) != image:
            raise ValueError("Running container does not use the selected immutable image")

    record("preflight")
    if not health():
        raise ValueError("Existing test-server baseline is unhealthy; stop before mutation")
    backup_dir = APP / "backups"
    backup_dir.mkdir(exist_ok=True, mode=0o700)
    backup = backup_dir / f"actions-{run_id}-before-{source_sha}.dump"
    with backup.open("xb") as output:
        compose("exec", "-T", "postgres", "pg_dump", "-U", "fantasycard", "-d", "fantasycard",
                "--format=custom", "--no-owner", "--no-privileges", stdout=output, stderr=subprocess.DEVNULL, timeout=300)
    if not backup.stat().st_size:
        raise ValueError("Empty database backup; stop before mutation")
    with backup.open("rb") as source:
        compose("exec", "-T", "postgres", "pg_restore", "--list", stdin=source,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    evidence["backup"] = {"name": backup.name, "sha256": digest(backup), "bytes": backup.stat().st_size}
    run("sudo", "-n", "docker", "image", "load", "-i", bundle / "image.tar.gz", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    new_image = manifest["image_id"]
    if capture("sudo", "-n", "docker", "image", "inspect", "--format", "{{.Id}}", new_image) != new_image:
        raise ValueError("Loaded image ID does not match tested build")
    if capture("sudo", "-n", "docker", "image", "inspect", "--format", '{{index .Config.Labels "org.opencontainers.image.revision"}}', new_image) != source_sha:
        raise ValueError("Loaded image source label does not match approved source")
    def finalize(image):
        # The repository checkout and deployed-git-commit remain unchanged.
        revision = source_sha if image == new_image else old_revision
        marker = APP / "deployed-runtime-commit"
        temporary = marker.with_suffix(".actions-tmp")
        temporary.write_text(revision + "\n")
        temporary.replace(marker)
    rollout(new_image, old_image, apply, health, record, finalize)
    (state / "last-accepted.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=pathlib.Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--controller-sha", required=True)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise RuntimeError("Controller interrupted")
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        with deployment_lock():
            deploy(args.bundle, args.source_sha, args.run_id, args.controller_sha)
    except Exception as error:
        # Do not print exception command output: it may contain runtime configuration.
        print("Deployment stopped: " + type(error).__name__, flush=True)
        raise SystemExit(1) from None
