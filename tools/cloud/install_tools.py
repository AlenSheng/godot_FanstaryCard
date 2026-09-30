"""Install the reviewed Linux x64 toolchain; verify bytes before extraction."""
import hashlib
import json
import os
import pathlib
import platform
import subprocess
import tarfile
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOCK = json.loads(pathlib.Path(__file__).with_name("toolchain.json").read_text())


def download(row, destination):
    temporary = destination.with_suffix(".download")
    request = urllib.request.Request(row["url"], headers={"User-Agent": "fantasycard-cloud-setup"})
    digest = hashlib.new(row["algorithm"])
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != row["digest"]:
        temporary.unlink()
        raise RuntimeError("Official download did not match the reviewed digest")
    temporary.replace(destination)


def main():
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "AMD64"):
        raise SystemExit("Cloud setup requires Linux x64; it does not configure this computer")
    sdk = json.loads((ROOT / "server/global.json").read_text())["sdk"]["version"]
    if sdk != LOCK["dotnet"]["version"]:
        raise SystemExit("Repository SDK changed: review and update the toolchain lock first")
    base = pathlib.Path(os.environ.get("FANTASYCARD_CLOUD_TOOLS", "/opt/fantasycard-cloud-tools"))
    base.mkdir(parents=True, exist_ok=True)
    for name in ("dotnet", "godot"):
        row = LOCK[name]
        destination = base / name
        stamp = destination / ".verified-digest"
        if stamp.exists() and stamp.read_text().strip() == row["digest"]:
            continue
        archive = base / (name + (".tar.gz" if name == "dotnet" else ".zip"))
        download(row, archive)
        destination.mkdir(parents=True, exist_ok=True)
        if name == "dotnet":
            with tarfile.open(archive) as source:
                source.extractall(destination, filter="data")
        else:
            with zipfile.ZipFile(archive) as source:
                expected = "Godot_v4.7.2-stable_linux.x86_64"
                if source.namelist() != [expected]:
                    raise RuntimeError("Unexpected Godot release archive layout")
                source.extract(expected, destination)
            binary = destination / expected
            binary.chmod(0o755)
            (destination / "godot").symlink_to(binary.name)
        stamp.write_text(row["digest"] + "\n")
        archive.unlink()
    subprocess.run([str(base / "dotnet/dotnet"), "--version"], check=True)
    subprocess.run([str(base / "godot/godot"), "--version"], check=True)


if __name__ == "__main__":
    main()
