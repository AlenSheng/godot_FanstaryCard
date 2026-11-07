import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from xml.etree import ElementTree

stage = sys.argv[1]
assert re.fullmatch(r'storage-r[1-9][0-9]*', stage)
root = Path('/home/ubuntu/season-balance-20261102-a03-' + stage)
handle = json.loads((root / 'sdk-handle.json').read_text())
inspection = json.loads(subprocess.check_output(['docker', 'inspect', handle['container_id']]))[0]
assert inspection['Config']['Labels']['com.fantasycard.task'] == 'season-balance-20261102-a03-' + stage
assert inspection['State']['Status'] == 'exited', 'Follow the existing container until terminal; do not restart it.'
password = json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text())['password'].encode()
logs = subprocess.check_output(['docker', 'logs', handle['container_id']], stderr=subprocess.STDOUT)
assert password not in logs
files = {'sdk-handle.json': (root / 'sdk-handle.json').read_bytes(), 'sdk.log': logs}
assert (root/'guard-terminal.original.json').is_file(), 'Follow the same guard until terminal'
for name in ['resource-guard.py','resource-guard.original.jsonl','guard-terminal.original.json','guard-handle.json','guard.stdout.original.log','guard.stderr.original.log']:
    files[name]=(root/name).read_bytes()
for path in sorted((root / 'input/results').glob('*.trx')):
    files[path.name] = path.read_bytes()
for path in sorted((root / 'input/server/.artifacts/protocol-remediation/process-logs').glob('*.log')):
    files['process-logs/' + path.name] = path.read_bytes()
for directory in ['server','client']:
    for name in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:
        path=root/'input/config-proof'/directory/name
        if path.exists(): files['config-proof/'+directory+'/'+name]=path.read_bytes()
assert all(password not in content for content in files.values())
for wire in sorted((root/'input/journey-wire').glob('*.bin')):
    files['journey-wire/'+wire.name]=wire.read_bytes()
counts = {}
for name, content in files.items():
    if name.endswith('.trx'):
        tree = ElementTree.fromstring(content)
        counts[name] = next(node.attrib for node in tree.iter() if node.tag.endswith('Counters'))
audit = {'container_id': handle['container_id'], 'state': inspection['State']['Status'],
         'exit_code': inspection['State']['ExitCode'], 'oom_killed': inspection['State']['OOMKilled'],
         'production_database_used': False, 'counters': counts,
         'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
files['audit.json'] = (json.dumps(audit, indent=2) + '\n').encode()
target = root / 'public-evidence.tar.gz'
assert not target.exists(), 'Preserve existing evidence.'
with tarfile.open(target, 'w:gz') as bundle:
    for name, data in files.items():
        entry = tarfile.TarInfo(name)
        entry.size = len(data)
        bundle.addfile(entry, io.BytesIO(data))
target.chmod(0o644)
print(json.dumps({**audit, 'public_archive_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}, indent=2))
