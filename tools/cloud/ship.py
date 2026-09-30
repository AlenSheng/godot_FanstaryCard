"""Transfer only the tested image and trusted controller; fetch only sanitized evidence."""
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import tempfile

from deployment import extract_health, file_hash, positive_integer, sha
from remote_deploy import validate_manifest


def main():
    number = positive_integer(os.environ["GITHUB_RUN_ID"])
    attempt = positive_integer(os.environ["GITHUB_RUN_ATTEMPT"])
    source = sha(os.environ["COMMIT_SHA"])
    controller = sha(os.environ["GITHUB_SHA"])
    artifact = pathlib.Path("image-artifact")
    evidence = pathlib.Path("deploy-evidence")
    evidence.mkdir(exist_ok=True)
    manifest = json.loads((artifact / "manifest.json").read_text())
    validate_manifest(manifest, source, number, controller)
    if manifest.get("run_attempt") != attempt or file_hash(artifact / "image.tar.gz") != manifest["archive_sha256"]:
        raise ValueError("Downloaded artifact does not match this build run")
    # Ignore all executable content from the build artifact. Generate health checks
    # again from the trusted controller checkout on this fresh runner.
    extract_health("trusted/server/deploy/fantasycard-update.sh", artifact / "health.sh")
    if file_hash(artifact / "health.sh") != manifest["health_sha256"]:
        raise ValueError("Build artifact attempted to change the trusted health checks")
    remote = f"/opt/fantasycard-app/test-deploy/incoming/{number}-{attempt}"
    host = "ubuntu@43.172.70.182"
    key = os.environ.pop("TEST_SERVER_SSH_KEY", "")
    known = os.environ.pop("TEST_SERVER_KNOWN_HOSTS", "")
    if not key or not known or not re.search(r"(?:^|\n)43\.172\.70\.182(?:\s|,)", known):
        raise ValueError("Test-server credentials or verified known-hosts entry are missing")
    with tempfile.TemporaryDirectory(prefix="fantasycard-ssh-") as directory:
        private = pathlib.Path(directory) / "key"
        hosts = pathlib.Path(directory) / "known_hosts"
        private.write_text(key.rstrip() + "\n")
        hosts.write_text(known.rstrip() + "\n")
        private.chmod(0o600)
        hosts.chmod(0o600)
        options = ["-i", str(private), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                   "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + str(hosts),
                   "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4"]
        ssh = ["ssh", *options, "-p", "22", host]
        scp = ["scp", *options, "-P", "22"]
        # Every shell argument is either fixed or validated before it reaches SSH.
        subprocess.run([*ssh, "umask 077 && mkdir -p " + shlex.quote(remote)], check=True, timeout=45)
        subprocess.run([*scp, str(artifact / "image.tar.gz"), str(artifact / "manifest.json"),
                        str(artifact / "health.sh"), "trusted/tools/cloud/remote_deploy.py", host + ":" + remote + "/"],
                       check=True, timeout=600)
        command = shlex.join(["python3", remote + "/remote_deploy.py", "--bundle", remote,
                              "--source-sha", source, "--run-id", str(number), "--controller-sha", controller])
        try:
            subprocess.run([*ssh, command], check=True, timeout=2400)
        finally:
            subprocess.run([*scp, host + ":" + remote + "/result.json", str(evidence / "result.json")],
                           check=False, timeout=45)
        # A successful SSH command is insufficient; validate the returned outcome.
        result = json.loads((evidence / "result.json").read_text())
        if result.get("status") != "accepted" or result.get("source_sha") != source or result.get("image_id") != manifest["image_id"]:
            raise ValueError("Remote acceptance evidence does not match the tested image")
        # Public read-only readiness through real TLS after remote acceptance.
        subprocess.run(["curl", "--fail", "--silent", "--show-error", "--max-time", "20",
                        "https://www.relicbound.cn/health/ready"], check=True, timeout=25,
                       stdout=(evidence / "external-readiness.txt").open("wb"))
        if (evidence / "external-readiness.txt").read_text().strip() != "Healthy":
            raise ValueError("External readiness returned an unexpected body")


if __name__ == "__main__":
    main()
