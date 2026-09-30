"""Install digest-locked Linux x64 tools without root or persistent permissions."""
import hashlib
import json
import os
import pathlib
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOCK = json.loads(pathlib.Path(__file__).with_name('toolchain.json').read_text())


def checksum(path, algorithm):
    value = hashlib.new(algorithm)
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def download(row, destination):
    """Local caches are untrusted until checked; partial downloads are never used."""
    if destination.is_file() and checksum(destination, row['algorithm']) == row['digest']:
        return
    temporary = destination.with_name(destination.name + '.download')
    cache = os.environ.get('FANTASYCARD_CLOUD_DOWNLOAD_CACHE')
    cached = pathlib.Path(cache) / destination.name if cache else None
    try:
        if cached and cached.is_file() and checksum(cached, row['algorithm']) == row['digest']:
            shutil.copyfile(cached, temporary)
        else:
            request = urllib.request.Request(row['url'], headers={'User-Agent': 'fantasycard-cloud-setup'})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as stream:
                shutil.copyfileobj(response, stream, 1024 * 1024)
        if checksum(temporary, row['algorithm']) != row['digest']:
            raise ValueError('Tool archive digest mismatch')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def extract_zip(archive, destination):
    expected = 'Godot_v4.7.2-stable_linux.x86_64'
    with zipfile.ZipFile(archive) as source:
        if source.namelist() != [expected]:
            raise ValueError('Unexpected Godot archive layout')
        source.extract(expected, destination)
    (destination / expected).chmod(0o755)
    (destination / 'godot').symlink_to(expected)


def version(binary):
    return subprocess.check_output([str(binary), '--version'], text=True, timeout=30).strip()


def install(base, name, rows, build, binary, expected):
    destination = base / name
    stamp_value = '\n'.join(row['digest'] for row in rows) + '\n'
    stamp = destination / '.verified-digest'
    if destination.is_symlink():
        raise ValueError('Tool destination cannot be a symlink')
    if stamp.is_file() and stamp.read_text() == stamp_value and (destination / binary).is_file():
        if expected in version(destination / binary):
            return
    archives = []
    for row in rows:
        archive = base / 'downloads' / row['url'].rsplit('/', 1)[-1]
        download(row, archive)
        archives.append(archive)
    with tempfile.TemporaryDirectory(prefix=name + '-install-', dir=base) as directory:
        stage = pathlib.Path(directory) / 'output'
        stage.mkdir()
        build(archives, stage, pathlib.Path(directory))
        if expected not in version(stage / binary):
            raise ValueError('Installed tool version differs from lock')
        (stage / '.verified-digest').write_text(stamp_value)
        # Only task-owned tool directories are replaced, after staging succeeds.
        if destination.exists():
            shutil.rmtree(destination)
        stage.replace(destination)


def main():
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64') or os.geteuid() == 0:
        raise SystemExit('Run cloud setup as an unprivileged Linux x64 user')
    sdk = json.loads((ROOT / 'server/global.json').read_text())['sdk']['version']
    if sdk != LOCK['dotnet']['version']:
        raise ValueError('Repository SDK changed; review the toolchain lock')
    base = pathlib.Path(os.environ.get('FANTASYCARD_CLOUD_TOOLS', '/workspace/fantasycard-cloud-tools'))
    if not base.is_absolute() or base == pathlib.Path('/') or base.is_symlink():
        raise ValueError('Expected a task-owned absolute tool directory')
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    (base / 'downloads').mkdir(exist_ok=True)
    # Debian 13 uses the same signed-distribution package hashes as the published
    # environment. Other distributions use the reviewed official SDK tar archive.
    debian = pathlib.Path('/etc/os-release').read_text()
    use_deb = 'ID=debian' in debian and 'VERSION_ID="13"' in debian
    rows = LOCK['dotnet_debian13'] if use_deb else [LOCK['dotnet']]
    def dotnet_build(archives, stage, work):
        for archive in archives:
            if use_deb:
                subprocess.run(['dpkg-deb', '-x', str(archive), str(stage)], check=True)
            else:
                with tarfile.open(archive) as source:
                    source.extractall(stage, filter='data')
    install(base, 'dotnet', rows, dotnet_build,
            'usr/share/dotnet/dotnet' if use_deb else 'dotnet', sdk)
    install(base, 'godot', [LOCK['godot']], lambda files, stage, work: extract_zip(files[0], stage),
            'godot', LOCK['godot']['version'] + '.')
    def pg_build(archives, stage, work):
        tools = work / 'build-tools'
        for archive in archives[1:]:
            subprocess.run(['dpkg-deb', '-x', str(archive), str(tools)], check=True)
        with tarfile.open(archives[0]) as source:
            source.extractall(work, filter='data')
        source_dir = work / ('postgresql-' + LOCK['postgres']['version'])
        env = dict(os.environ, PATH=str(tools / 'usr/bin') + ':' + os.environ['PATH'],
                   BISON_PKGDATADIR=str(tools / 'usr/share/bison'), M4=str(tools / 'usr/bin/m4'))
        log = base / 'postgres-build.log'
        with log.open('w') as output:
            for arguments in ([str(source_dir / 'configure'), '--prefix=' + str(stage), '--without-readline', '--without-icu'],
                              ['make', '-j2'], ['make', 'install']):
                subprocess.run(arguments, cwd=source_dir, env=env, stdout=output,
                               stderr=subprocess.STDOUT, check=True, timeout=1200)
    install(base, 'postgres', [LOCK['postgres'], *LOCK['build_tools']], pg_build,
            'bin/postgres', LOCK['postgres']['version'])
    print('Verified cloud toolchain installed in ' + str(base))


if __name__ == '__main__':
    main()
