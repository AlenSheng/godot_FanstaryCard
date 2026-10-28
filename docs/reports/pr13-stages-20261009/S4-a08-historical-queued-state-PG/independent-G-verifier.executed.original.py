import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

B = Path(__file__).parent
R = B.parents[1]
OUT = B/'A08-history-state-PG-r1-independent-G-check'
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

receipt = read(B/'A08-history-state-PG-r1-complete-original-G-backup/complete-original-G-receipt.original.json')
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
for name,source in [('pr13_review_policy.py','tools/pr13_review_policy.py'),('pr13_public_evidence.py','tools/pr13_public_evidence.py'),('legacy-B-queue.original.json','docs/plans/PR13_COMBAT_EXPERIENCE_QUEUE_20260930.json')]:
    assert (G/'work/control'/name).read_bytes()==git('show',head+':'+source)
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
actuals = {}
expected_modes = {'PR13-A08.2-T01':'historical-counts','PR13-A08.2-T02':'queued-fortyeight','PR13-A08.2-T03':'unresolved-thirty'}
queue=read(G/'work/control/legacy-B-queue.original.json')
legacy_tasks={t['id']:t for pkg in queue['tasks'] for t in pkg['subtasks']}
assert len(legacy_tasks)==48
for cid,mode in expected_modes.items():
    native=read(G/'evidence/persistent-output/native-receipts'/(cid+'.json'))
    assert native['status']=='Passed';a=native['actual']
    assert a['snapshotBeforeHash']==a['snapshotAfterHash'] and a['databaseBeforeHash']==a['databaseAfterHash']
    assert a['actualMatches']==a['actualSnapshots']==1 and a['productionSourceModified'] is False
    assert a['actualHistoricalRawReconciliation'] is False and a['actualLoadOrCapacitySamples']==0
    assert a['actualExitCode']==0 and a['cards']==[f'C{i:02}' for i in range(1,14)]+[f'GUA-{i:02}' for i in range(1,8)]
    v=a['actualStateGuard'];assert v['ok'] and v['mode']==mode
    output=v['actual_policy_output']
    if mode=='queued-fortyeight':
        assert output['historical_queue_tasks']==48 and output['controlled_current_passed']==0
        assert output['current_real_B_register_was_not_reclassified'] is True
        observations=output['actual_classifier_observations'];assert len(observations)==48
        assert {o['task_id'] for o in observations}==set(legacy_tasks)
        for o in observations:
            assert o['legacy_specification_state']==legacy_tasks[o['task_id']]['specification_state']=='ReviewReady'
            assert o['legacy_queue_state']==legacy_tasks[o['task_id']]['state']=='Queued'
            assert o['actual_classification']=='Queued' and len(o['controlled_execution_records'])==3
            assert all(r['executed'] is False and r['status']=='NotExecuted' for r in o['controlled_execution_records'])
    else:
        assert output['current_passed']==0 and output['runtime_revalidated'] is False and output['comparison_state']=='Blocked'
        if mode=='historical-counts':assert output['historical_passed']==191 and output['historical_skipped']==62
        else:assert output['historical_passed']==130 and output['reported_other_cutoff_count']==139 and output['raw_reconciliation_performed'] is False
    actuals[cid]=a
domain = G/'work/artifacts/bin/FantasyCard.Domain/release/FantasyCard.Domain.dll'
tests = G/'work/artifacts/bin/FantasyCard.Server.Tests/release/FantasyCard.Server.Tests.dll'
assert sha(domain)==plan['production_domain_assembly_sha256']=='844065af3158b40787699752915ed95befbd3c660c2b10dce501f9f4fc29e352'
proof={'ok':True,'case_ids':plan['case_ids'],'profile':'POSTGRES','actual_native_PG_rows':10,
    'native_clean':True,'owned_container_removed':True,'source_inputs_match_git':True,
    'original_nine_regression_rows':9,'new_state_matrix_methods':1,'native_skipped':0,
    'all_original_G_members_rehashed':len(manifest['files']),'archive_SHA_and_CRC_rechecked':True,
    'current_source_members':328,'current_classification_input_files':3,'implementation_source_sha':head,
    'actual_state_subprocess_modes':3,'controlled_legacy_queue_tasks':48,'controlled_absent_case_records':144,
    'historical_raw_reconciliation_performed':False,'current_real_B48_register_reclassified':False,
    'actual_load_or_capacity_samples':0,'production_domain_assembly_unchanged':True,'actuals':actuals,
    'all_other_canonical_profiles_retained':True,'MAIN_accepted':False}
OUT.mkdir();(OUT/'independent-G-check.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in proof.items() if k!='actuals'}))
