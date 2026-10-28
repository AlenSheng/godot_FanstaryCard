import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

B = Path(__file__).parent
R = B.parents[1]
OUT = B / 'B12-candidate-defaults-PG-r1-independent-G-check'
assert not OUT.exists()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 ** 2), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_bytes())


receipt = read(B / 'B12-candidate-defaults-PG-r1-complete-original-G-backup/complete-original-G-receipt.original.json')
G = Path(receipt['local_directory'])
archive = Path(receipt['local_archive'])
assert receipt['ok'] and receipt['all_original_members_SHA_verified'] and receipt['archive_gzip_CRC_verified']
assert archive.stat().st_size == receipt['archive_bytes'] and sha(archive) == receipt['archive_sha256']
with gzip.open(archive, 'rb') as stream:
    while stream.read(1024 ** 2):
        pass
manifest_path = G / 'complete-original-manifest.json'
assert sha(manifest_path) == receipt['manifest_sha256']
manifest = read(manifest_path)
assert len(manifest['files']) == receipt['original_members'] and receipt['original_members'] >= 600
for row in manifest['files']:
    path = G / row['path']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
plan = read(G / 'work/control/plan.original.json')
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip()
for row in plan['source_files']:
    raw = subprocess.check_output(['git', 'show', head + ':' + row['path']], cwd=R)
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    path = G / 'work/source' / row['path']
    if row['path'] == plan['source_override_path']:
        addition = (G / 'work/control/addition.original.cs').read_bytes()
        index = raw.rfind(b'}')
        assert path.read_bytes() == raw[:index] + addition + raw[index:]
    else:
        assert sha(path) == row['sha256']
assert len(plan['source_files']) == 328
for row in plan['config_files']:
    raw = subprocess.check_output(['git', 'show', head + ':' + row['path']], cwd=R)
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
assert (G / 'work/control/pr13_stages.py').read_bytes() == subprocess.check_output(['git', 'show', head + ':tools/pr13_stages.py'], cwd=R)
result = read(G / 'evidence/result.original.json')
assert result['ok'] and result['exit_code'] == 0 and not result['oom_killed'] and result['owned_containers_removed']
assert result['remaining_owned_fixture_schemas'] == 0 and result['original_shared_and_controlled_inputs_unchanged']
assert result['private_environment_removed_after_owned_containers_ended']
tree = ET.parse(G / 'evidence/persistent-output/results/native-ten.original.trx')
counts = {key: int(value) for key, value in tree.find('.//{*}Counters').attrib.items()}
assert counts['total'] == counts['executed'] == counts['passed'] == 10 and counts['failed'] == counts['notExecuted'] == 0
methods = {row.find('{*}TestMethod').attrib['name'] for row in tree.findall('.//{*}UnitTest')}
assert methods == set(plan['required_native_methods'])
rows = tree.findall('.//{*}UnitTestResult')
assert len(rows) == 10 and all(row.attrib['outcome'] == 'Passed' for row in rows)
a = read(G / 'evidence/persistent-output/native-receipts/PR13-B12.3-T03.json')['actual']
observations = a['actualGuardObservations']
assert len(observations)==7 and [row['mode'] for row in observations]==plan['control_modes']
assert observations[0]['actualExitCode']==0 and observations[0]['actualGuard']['state']=='ValidDefault'
flags=['cards_spent_draw','fractional_guardian','optional_monster_pool','budgeted_bot_loot','mortal_bot_pve']
assert all(observations[0]['actualGuard']['actual_policy'][name] is False for name in flags)
assert observations[0]['actualGuard']['actual_policy']['monster_capacity']==5
for row in observations:
    assert row['snapshotBeforeHash']==row['snapshotAfterHash'] and row['databaseBeforeHash']==row['databaseAfterHash']
    assert row['FenxianDrawPolicy']==row['GuardianShieldPolicy']==1
for row in observations[1:]:
    assert row['actualExitCode']==3 and row['actualGuard']['state']=='Blocked'
    assert row['actualGuard']['reason']=='Formal numerical candidate defaults changed; isolate experiments and retain the frozen default policy'
assert a['actualMatches']==a['actualSnapshots']==1 and not a['candidateAdmitted'] and not a['productionSourceModified']
assert a['cards'] == [f'C{i:02d}' for i in range(1, 14)] + [f'GUA-{i:02d}' for i in range(1, 8)]
assert sha(G / 'work/artifacts/bin/FantasyCard.Server.Tests/release/FantasyCard.Domain.dll') == '844065af3158b40787699752915ed95befbd3c660c2b10dce501f9f4fc29e352'
proof = {'ok': True, 'native_clean': True, 'owned_container_removed': True, 'source_inputs_match_git': True,
         'implementation_source_sha': head, 'production_domain_assembly_unchanged': True,
         'declared_test_only_source_insertions': 1, 'all_original_G_members_rehashed': receipt['original_members'],
         'all_original_G_archive_SHA_and_CRC_rechecked': True, 'current_source_members': 328,
         'current_config_files': 8, 'actual_native_PG_rows': 10, 'native_skipped': 0,
         'new_control_rows': 1, 'original_nine_regression_rows': 9, 'actual': a,
         'local_operations': 'byte SHA CRC Git XML and original JSON identities only', 'MAIN_accepted': False}
OUT.mkdir()
(OUT / 'independent-G-check.original.json').write_bytes((json.dumps(proof, indent=2) + '\n').encode())
print(json.dumps({key: value for key, value in proof.items() if key != 'actual'}))
