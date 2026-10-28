import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

B = Path(__file__).parent
R = B.parents[1]
OUT = B/'A08-dirty-source-PG-r1-independent-G-check'
assert not OUT.exists()

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1024**2),b''):
            h.update(data)
    return h.hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def git(*args):
    return subprocess.check_output(['git','-c','core.longpaths=true',*args],cwd=R)

receipt = read(B/'A08-dirty-source-PG-r1-complete-original-G-backup/complete-original-G-receipt.original.json')
G = Path(receipt['local_directory'])
archive = Path(receipt['local_archive'])
assert receipt['ok'] and receipt['all_original_members_SHA_verified'] and receipt['archive_gzip_CRC_verified']
assert archive.stat().st_size==receipt['archive_bytes'] and sha(archive)==receipt['archive_sha256']
with gzip.open(archive,'rb') as stream:
    while stream.read(1024**2):
        pass
assert sha(G/'complete-original-manifest.json')==receipt['manifest_sha256']
manifest = read(G/'complete-original-manifest.json')
assert len(manifest['files'])==receipt['original_members'] and receipt['original_members']>=600
for row in manifest['files']:
    p = G/row['path']
    assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
plan = read(G/'work/control/plan.original.json')
head = git('rev-parse','HEAD').decode().strip()
for row in plan['source_files']:
    raw = git('show',head+':'+row['path'])
    assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
    p = G/'work/source'/row['path']
    if row['path']==plan['source_override_path']:
        addition = (G/'work/control/addition.original.cs').read_bytes()
        index = raw.rfind(b'}')
        assert p.read_bytes()==raw[:index]+addition+raw[index:]
    else:
        assert sha(p)==row['sha256']
assert len(plan['source_files'])==328
assert (G/'work/control/gameplay_load_validation.py').read_bytes()==git('show',head+':tools/gameplay_load_validation.py')
for row in plan['work_files']:
    p = G/'work/control'/row['path']
    assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
for row in plan['config_files']:
    raw = git('show',head+':'+row['path'])
    assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
result = read(G/'evidence/result.original.json')
assert result['ok'] and result['exit_code']==0 and not result['oom_killed']
assert result['owned_containers_removed'] and result['private_environment_removed_after_owned_containers_ended']
assert result['remaining_owned_fixture_schemas']==0 and result['original_shared_and_controlled_inputs_unchanged']
terminal = read(G/'evidence/terminal-state.original.json')
assert terminal['MainPID']=='0' and terminal['ActiveState']=='inactive' and terminal['ExecMainStatus']=='0'
tree = ET.parse(G/'evidence/persistent-output/results/native-ten.original.trx')
counts = {k:int(v) for k,v in tree.find('.//{*}Counters').attrib.items()}
assert counts['total']==counts['executed']==counts['passed']==10 and counts['failed']==counts['notExecuted']==0
assert {n.find('{*}TestMethod').attrib['name'] for n in tree.findall('.//{*}UnitTest')}==set(plan['required_native_methods'])
assert all(n.attrib['outcome']=='Passed' for n in tree.findall('.//{*}UnitTestResult'))
native = read(G/'evidence/persistent-output/native-receipts/PR13-A08.1-T02.json')
assert native['status']=='Passed'
a = native['actual'];v = a['actualProvenance'];clean = v['clean'];dirty = v['dirty'];path = plan['source_override_path']
assert a['snapshotBeforeHash']==a['snapshotAfterHash'] and a['databaseBeforeHash']==a['databaseAfterHash']
assert a['actualMatches']==a['actualSnapshots']==1 and a['productionSourceModified'] is False
assert a['cards']==[f'C{i:02}' for i in range(1,14)]+[f'GUA-{i:02}' for i in range(1,8)]
assert clean['git_dirty'] is False and dirty['git_dirty'] is True
assert clean['git_commit']==dirty['git_commit']!=plan['source_base_sha']
assert clean==read(G/'work/control/clean-source-provenance.original.json')
assert clean['sha256'][path]==plan['original_test_source_sha256']
assert dirty['sha256'][path]==plan['modified_test_source_sha256']!=clean['sha256'][path]
assert v['actual_dirty_porcelain']==[' M '+path]
assert v['compiled_dirty_source_matches_frozen_insertion'] and v['owned_snapshot_commit_is_release_commit'] is False
assert v['tool_source_sha256']==sha(G/'work/control/gameplay_load_validation.py')
assert dirty['sha256']['server/config/generated/fantasycard.config.bytes']==clean['sha256']['server/config/generated/fantasycard.config.bytes']==plan['published_config_bytes_sha256']
assert git('-c','safe.directory='+str(G/'work/source'),'-C',str(G/'work/source'),'rev-parse','HEAD').decode().strip()==clean['git_commit']
original = git('-c','safe.directory='+str(G/'work/source'),'-C',str(G/'work/source'),'show','HEAD:'+path)
assert hashlib.sha256(original).hexdigest()==plan['original_test_source_sha256']
domain = G/'work/artifacts/bin/FantasyCard.Domain/release/FantasyCard.Domain.dll'
tests = G/'work/artifacts/bin/FantasyCard.Server.Tests/release/FantasyCard.Server.Tests.dll'
assert sha(domain)==plan['production_domain_assembly_sha256']=='844065af3158b40787699752915ed95befbd3c660c2b10dce501f9f4fc29e352'
assert sha(tests)==a['actualDirtyTestAssemblySha256']==result['inner']['actual_dirty_test_assembly_sha256']
proof = {'ok':True,'case_id':'PR13-A08.1-T02','profile':'POSTGRES','actual_native_PG_rows':10,
    'native_clean':True,'owned_container_removed':True,'source_inputs_match_git':True,
    'original_nine_regression_rows':9,'new_control_rows':1,'native_skipped':0,
    'all_original_G_members_rehashed':len(manifest['files']),'archive_SHA_and_CRC_rechecked':True,
    'current_source_members':328,'implementation_source_sha':head,
    'genuine_owned_Git_clean_and_dirty_states_verified':True,'owned_snapshot_commit_is_release_commit':False,
    'production_domain_assembly_unchanged':True,'actual_dirty_test_assembly_sha256':sha(tests),
    'actual':a,'all_canonical_profiles_other_than_exact_POSTGRES_cell_retained':True,'MAIN_accepted':False}
OUT.mkdir();(OUT/'independent-G-check.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in proof.items() if k!='actual'}))
