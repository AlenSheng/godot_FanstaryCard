import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

B = Path('/home/ubuntu/pr13-acceptance-20261009')
revision = sys.argv[1]
assert revision == 'r2'
name = 'A042-ordered-required-PG-' + revision + '-20261014'
E = B / 'evidence' / name
W = B / 'work' / name
owner = 'pr13-cap-a042-ordered-required-pg-' + revision


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
    # Retain exact unmodified parent client inputs alongside the two declared overrides.
    plan=json.loads((W/'plan.original.json').read_bytes())
    parent=E/'parent-client-originals';assert not parent.exists();parent.mkdir()
    for row in plan['client_files']:
        data=subprocess.check_output(['git','-c','safe.directory=/opt/fantasycard-github','-C','/opt/fantasycard-github','show',plan['source_base_sha']+':'+row['path']])
        assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
        target=parent/row['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    rows = []
    plan=json.loads((W/'plan.original.json').read_bytes())
    for prefix, root in [('evidence',E),('work',W),('input-source',Path(plan['source_root'])),('input-runtime',Path(plan['runtime_root']))]:
        for path in sorted(root.rglob('*')):
            assert not path.is_symlink()
            if not path.is_file():
                continue
            assert path.name not in ['delivery-originals.tar.gz', 'complete-original-manifest.json']
            rows.append({'path': prefix + '/' + path.relative_to(root).as_posix(),
                         'bytes': path.stat().st_size, 'sha256': sha(path)})
    assert sum(row['bytes'] for row in rows) <= 320 * 1024 ** 2
    manifest = {'ok': True, 'attempt': name, 'owner': owner, 'state': state, 'files': rows,
                'private_credentials_not_included': False, 'production_credentials_not_used': True, 'generated_ephemeral_credentials_may_occur_in_private_originals': True, 'native_reexecuted_by_delivery': False, 'MAIN_accepted': False}
    manifest_path.write_bytes((json.dumps(manifest, indent=2) + '\n').encode())
manifest = json.loads(manifest_path.read_bytes())
plan=json.loads((W/'plan.original.json').read_bytes())
roots={'evidence':E,'work':W,'input-source':Path(plan['source_root']),'input-runtime':Path(plan['runtime_root'])}
if sys.argv[2]=='manifest':
    print(json.dumps({'ok':True,'manifest':manifest,'manifest_sha256':sha(manifest_path),'streaming_without_cloud_archive':True}))
elif sys.argv[2]=='stream':
    for row in manifest['files']:
        prefix,relative=row['path'].split('/',1);p=roots[prefix]/relative
        assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
    class HashedStream:
        def __init__(self):self.bytes=0;self.hash=hashlib.sha256()
        def write(self,data):
            self.hash.update(data);self.bytes+=len(data);sys.stdout.buffer.write(data);return len(data)
        def flush(self):sys.stdout.buffer.flush()
    stream=HashedStream()
    with tarfile.open(fileobj=stream,mode='w|gz',dereference=True) as bundle:
        for row in manifest['files']:
            prefix,relative=row['path'].split('/',1);bundle.add(roots[prefix]/relative,arcname=row['path'],recursive=False)
        bundle.add(manifest_path,arcname='complete-original-manifest.json',recursive=False)
    stream.flush()
    sys.stderr.write('ACK '+json.dumps({'bytes':stream.bytes,'sha256':stream.hash.hexdigest(),'manifest_sha256':sha(manifest_path),'streaming_without_cloud_archive':True})+'\n')
else:raise ValueError('Unknown delivery action')
