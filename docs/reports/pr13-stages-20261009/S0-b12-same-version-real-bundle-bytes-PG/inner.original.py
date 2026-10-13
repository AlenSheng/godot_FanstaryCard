import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, '/control')
import export_client_catalog
import pr13_stages

C = Path('/control')
O = Path('/output')
plan = json.loads((C / 'plan.original.json').read_bytes())
phases = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def phase(name, args, timeout):
    with (O / (name + '.stdout.original.log')).open('xb') as stdout, (O / (name + '.stderr.original.log')).open('xb') as stderr:
        result = subprocess.run(args, cwd='/work/server', stdout=stdout, stderr=stderr, timeout=timeout)
    phases.append({'name': name, 'exit_code': result.returncode})
    assert result.returncode == 0, name + ' failed'


# Writable copies only; every published byte remains mounted read-only.
for name in ['base-root', 'changed-root']:
    root = C / name
    root.mkdir()
    for row in plan['config_files']:
        target = root / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (C / 'published' / row['path']).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
        target.write_bytes(data)
base = C / 'base-root'
original = (base / 'server/config/generated/fantasycard.config.bytes').read_bytes()
original_identity = pr13_stages.config_identity(base)
assert sha(original) == plan['published_config_bytes_sha256']
fields = export_client_catalog.fields(original)
table = next(value for value in fields[3] if export_client_catalog.fields(value).get(1) == [b'Cards'])
assert table.startswith(b'\x0a\x05Cards')
position = original.find(table)
assert position >= 0 and original.find(table, position + 1) < 0
changed = bytearray(original)
changed[position + 6] = ord('x')
changed = bytes(changed)
changed_fields = export_client_catalog.fields(changed)
assert changed_fields[1] == fields[1] and changed_fields[2] == fields[2]
assert sum(a != b for a, b in zip(original, changed)) == 1
for row in changed_fields[3]:
    export_client_catalog.fields(row)
for folder in ['server/config/generated', 'client/data/generated']:
    (C / 'changed-root' / folder / 'fantasycard.config.bytes').write_bytes(changed)
witness = {'original_config_version': original_identity['version'],
           'version_bytes_unchanged': changed_fields[1] == fields[1],
           'declared_content_hash_unchanged': changed_fields[2] == fields[2],
           'original_embedded_content_hash': fields[2][0].hex(),
           'wire_layout_valid': True, 'changed_bytes': 1, 'changed_offset': position + 6,
           'original_bytes_sha256': sha(original), 'changed_bytes_sha256': sha(changed),
           'both_server_and_client_changed_copies_identical': True,
           'published_source_untouched': True}
(C / 'prepared-byte-witness.original.json').write_bytes((json.dumps(witness, indent=2) + '\n').encode())
project = '/work/server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'
phase('restore', ['dotnet', 'restore', project, '--source', '/packages', '--artifacts-path', '/artifacts',
      '-p:RestorePackagesPath=/packages', '-p:UseSharedCompilation=false', '-maxcpucount:1'], 480)
phase('build', ['dotnet', 'build', project, '-c', 'Release', '--no-restore', '--artifacts-path', '/artifacts',
      '-p:UseSharedCompilation=false', '-maxcpucount:1'], 600)
phase('native', ['dotnet', 'test', project, '-c', 'Release', '--no-build', '--no-restore',
      '--artifacts-path', '/artifacts', '--filter', 'FullyQualifiedName~PostgresNumericalContractTests',
      '--results-directory', '/output/results', '--logger', 'trx;LogFileName=native-ten.original.trx'], 300)
tree = ET.parse(O / 'results/native-ten.original.trx')
counts = {key: int(value) for key, value in tree.find('.//{*}Counters').attrib.items()}
assert counts['total'] == counts['executed'] == counts['passed'] == 10 and counts['failed'] == counts['notExecuted'] == 0
methods = {row.find('{*}TestMethod').attrib['name'] for row in tree.findall('.//{*}UnitTest')}
assert methods == set(plan['required_native_methods'])
receipt = json.loads((O / 'native-receipts/PR13-B12.1-T02.json').read_bytes())
assert receipt['status'] == 'Passed' and receipt['actual']['actualInvalidExitCode'] == 3
(O / 'inner-result.original.json').write_bytes((json.dumps({'ok': True, 'actual_native_rows': 10,
    'new_control_rows': 1, 'original_nine_regression_rows': 9, 'native_skipped': 0,
    'case_id': 'PR13-B12.1-T02', 'actual_config_version': original_identity['version'],
    'prepared_byte_witness': witness, 'phases': phases, 'MAIN_accepted': False}, indent=2) + '\n').encode())
print(json.dumps({'ok': True, 'actual_PG_rows': 10, 'new_control_rows': 1, 'native_skipped': 0}))
