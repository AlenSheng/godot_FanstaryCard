import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

B = Path('/home/ubuntu/pr13-acceptance-20261009')
revision = sys.argv[1]
assert revision == 'r1'
name = 'LOAD064-sensitive-PG-' + revision + '-20261014'
E = B / 'evidence' / name
W = B / 'work' / name
owner = 'pr13-cap-load064-sensitive-pg-' + revision


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


state = dict(x.split('=', 1) for x in subprocess.check_output(['systemctl', 'show', owner,
    '--property=MainPID,ActiveState,ExecMainStatus,InvocationID'], text=True).splitlines())
assert state['MainPID'] == '0' and state['ActiveState'] in ['failed', 'inactive']
assert not subprocess.check_output(['docker', 'ps', '-a', '--filter', 'label=codex.owner=' + owner,
                                  '--format', '{{.Names}}'], text=True).strip()
if not (E / 'terminal-state.original.json').exists():
    (E / 'terminal-state.original.json').write_bytes((json.dumps(state, indent=2) + '\n').encode())
    (E / 'unit.journal.terminal.original.log').write_bytes(subprocess.check_output(['journalctl', '-u', owner, '--no-pager']))
manifest_path = E / 'complete-original-manifest.json'
archive = W / 'delivery-originals.tar.gz'
if not manifest_path.exists():
    assert not archive.exists()
    rows = []
    for prefix, root in [('evidence', E), ('work', W)]:
        for path in sorted(root.rglob('*')):
            assert not path.is_symlink()
            if not path.is_file():
                continue
            assert path.name not in ['delivery-originals.tar.gz', 'complete-original-manifest.json']
            rows.append({'path': prefix + '/' + path.relative_to(root).as_posix(),
                         'bytes': path.stat().st_size, 'sha256': sha(path)})
    assert sum(row['bytes'] for row in rows) <= 320 * 1024 ** 2
    manifest = {'ok': True, 'attempt': name, 'owner': owner, 'state': state, 'files': rows,
                'production_credentials_not_included': True, 'generated_ephemeral_test_credentials_included_in_private_G_archive': True, 'native_reexecuted_by_delivery': False, 'MAIN_accepted': False}
    manifest_path.write_bytes((json.dumps(manifest, indent=2) + '\n').encode())
    with tarfile.open(archive, 'x:gz') as bundle:
        for row in rows:
            prefix, relative = row['path'].split('/', 1)
            bundle.add((E if prefix == 'evidence' else W) / relative, arcname=row['path'], recursive=False)
        bundle.add(manifest_path, arcname='complete-original-manifest.json', recursive=False)
manifest = json.loads(manifest_path.read_bytes())
ack = {'bytes': archive.stat().st_size, 'sha256': sha(archive), 'manifest_sha256': sha(manifest_path)}
if sys.argv[2] == 'manifest':
    print(json.dumps({'ok': True, 'manifest': manifest, **ack}))
elif sys.argv[2] == 'stream':
    with archive.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
    sys.stderr.write('ACK ' + json.dumps(ack) + '\n')
else:
    raise ValueError('Unknown delivery action')
