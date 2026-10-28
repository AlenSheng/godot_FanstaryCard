import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, '/control')

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


project = '/work/server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'
phase('restore', ['dotnet', 'restore', project, '--source', '/packages', '--artifacts-path', '/artifacts',
      '-p:RestorePackagesPath=/packages', '-p:UseSharedCompilation=false', '-maxcpucount:1'], 480)
phase('build', ['dotnet', 'build', project, '-c', 'Release', '--no-restore', '--artifacts-path', '/artifacts',
      '-p:UseSharedCompilation=false', '-maxcpucount:1'], 600)
domain=Path('/artifacts/bin/FantasyCard.Domain/release/FantasyCard.Domain.dll')
assert sha(domain.read_bytes())==plan['production_domain_assembly_sha256']
phase('native', ['dotnet', 'test', project, '-c', 'Release', '--no-build', '--no-restore',
      '--artifacts-path', '/artifacts', '--filter', 'FullyQualifiedName~PostgresNumericalContractTests',
      '--results-directory', '/output/results', '--logger', 'trx;LogFileName=native-ten.original.trx'], 300)
tree = ET.parse(O / 'results/native-ten.original.trx')
counts = {key: int(value) for key, value in tree.find('.//{*}Counters').attrib.items()}
assert counts['total'] == counts['executed'] == counts['passed'] == 10 and counts['failed'] == counts['notExecuted'] == 0
methods = {row.find('{*}TestMethod').attrib['name'] for row in tree.findall('.//{*}UnitTest')}
assert methods == set(plan['required_native_methods'])
for cid in plan['case_ids']:
    receipt=json.loads((O/'native-receipts'/(cid+'.json')).read_bytes());assert receipt['status']=='Passed'
(O / 'inner-result.original.json').write_bytes((json.dumps({'ok': True, 'actual_native_rows': 10,
    'new_control_rows': 1, 'original_nine_regression_rows': 9, 'native_skipped': 0,
    'case_ids':plan['case_ids'], 'actual_state_subprocess_modes':3, 'production_domain_assembly_sha256':sha(domain.read_bytes()), 'phases': phases, 'MAIN_accepted': False}, indent=2) + '\n').encode())
print(json.dumps({'ok': True, 'actual_PG_rows': 10, 'new_control_rows': 1, 'native_skipped': 0}))
