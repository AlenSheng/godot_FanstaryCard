import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

B = Path(__file__).parent
R = B.parents[1]
OUT = B/'B12-unexplained-ledger-PG-r1-independent-G-check'
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

receipt = read(B/'B12-unexplained-ledger-PG-r1-complete-original-G-backup/complete-original-G-receipt.original.json')
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
for name in ['pr13_review_policy.py','pr13_public_evidence.py']:
    assert (G/'work/control'/name).read_bytes()==git('show',head+':tools/'+name)
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
native=read(G/'evidence/persistent-output/native-receipts/PR13-B12.4-T03.json')
assert native['status']=='Passed';a=native['actual']
assert a['snapshotBeforeHash']==a['snapshotAfterHash'] and a['databaseBeforeHash']==a['databaseAfterHash']
assert a['productionSourceModified'] is False and a['liveAssetsTouched'] is False
assert a['corruptEvidenceNotRepairedOrDeleted'] is True and a['actualLedgerRows']==2
assert a['cards']==[f'C{i:02}' for i in range(1,14)]+[f'GUA-{i:02}' for i in range(1,8)]
healthy=a['healthyReconciliation'];broken=a['brokenReconciliation'];still=a['stillBrokenReconciliation']
assert healthy['IsHealthy'] and healthy['TotalViolationCount']==0
assert not broken['IsHealthy'] and broken['LedgerChainMismatchCount']==broken['TotalViolationCount']==1
assert still==broken
assert a['actualSecondDelta']==5 and a['actualSecondBalance']-a['actualFirstBalance']-a['actualSecondDelta']==7
hr=json.loads(a['healthyLedgerRaw']);br=json.loads(a['brokenLedgerRaw'])
assert len(hr)==len(br)==2 and hr[0]==br[0]
assert hr[1]['ledger_id']==br[1]['ledger_id'] and hr[1]['delta']==br[1]['delta']==5
assert br[1]['balance_after']-hr[1]['balance_after']==7
assert hr[1]['balance_after']==hr[0]['balance_after']+5
v=a['actualAssetGuard'];assert v['ok'] and v['faulted_ledger_was_not_repaired_or_deleted_to_pass']
gate=v['actual_asset_gate'];assert gate['state']=='Blocked' and gate['asset_acceptance'] is False
assert len(gate['unexplained_alerts'])==len(v['actual_alerts'])==1 and gate['unexplained_alerts'][0]==v['actual_alerts'][0]['id']
assert v['actual_alerts'][0]['explained'] is False
observed=v['actual_alerts'][0]['actual_database_observation']
assert observed['ledger_chain_mismatch_count']==observed['total_violation_count']==1 and observed['unexplained_balance_gap']==7
assert v['healthy_no_alert_positive_gate']['state']=='ReadyForMainReview' and v['healthy_no_alert_positive_gate']['asset_acceptance'] is False
domain = G/'work/artifacts/bin/FantasyCard.Domain/release/FantasyCard.Domain.dll'
tests = G/'work/artifacts/bin/FantasyCard.Server.Tests/release/FantasyCard.Server.Tests.dll'
assert sha(domain)==plan['production_domain_assembly_sha256']=='844065af3158b40787699752915ed95befbd3c660c2b10dce501f9f4fc29e352'
proof={'ok':True,'case_id':'PR13-B12.4-T03','profile':'POSTGRES','actual_native_PG_rows':10,
    'native_clean':True,'owned_container_removed':True,'source_inputs_match_git':True,
    'original_nine_regression_rows':9,'new_real_ledger_gate_methods':1,'native_skipped':0,
    'all_original_G_members_rehashed':len(manifest['files']),'archive_SHA_and_CRC_rechecked':True,
    'current_source_members':328,'implementation_source_sha':head,
    'current_EconomyReconciliation_SQL_observed_one_actual_ledger_gap':True,'actual_corrupt_balance_gap':7,
    'corrupt_ledger_evidence_not_repaired_or_deleted_to_pass':True,
    'production_domain_assembly_unchanged':True,'actual':a,
    'all_other_canonical_profiles_retained':True,'MAIN_accepted':False}
OUT.mkdir();(OUT/'independent-G-check.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in proof.items() if k!='actual'}))
