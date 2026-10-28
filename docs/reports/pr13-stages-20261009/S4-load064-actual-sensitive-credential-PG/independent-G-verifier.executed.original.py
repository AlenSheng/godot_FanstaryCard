import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

B = Path(__file__).parent
R = B.parents[1]
OUT = B/'LOAD064-sensitive-PG-r1-independent-G-check'
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

receipt = read(B/'LOAD064-sensitive-PG-r1-complete-original-G-backup/complete-original-G-receipt.original.json')
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
assert (G/'work/control/pr13_public_evidence.py').read_bytes()==git('show',head+':tools/pr13_public_evidence.py')
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
native=read(G/'evidence/persistent-output/native-receipts/LOAD-06.4-T03.json');assert native['status']=='Passed';a=native['actual']
assert a['snapshotBeforeHash']==a['snapshotAfterHash'] and a['databaseBeforeHash']==a['databaseAfterHash']
assert a['productionSourceModified'] is False and a['productionCredentialsUsed'] is False
assert a['actualDatabaseSessionLookupBeforeAndAfter'] and a['actualIssuedTicketConsumedOnce']
assert a['generatedEphemeralTestCredentialsOnly'] and a['sensitiveValuesNeverWrittenToPublicReceipt']
assert a['cards']==[f'C{i:02}' for i in range(1,14)]+[f'GUA-{i:02}' for i in range(1,8)]
candidates=G/'work/control/owned-sensitive-candidates'
session=read(candidates/'actual-session-token.json');ticket=read(candidates/'actual-realtime-ticket.json')
assert list(session)==['token'] and list(ticket)==['ticketBody']
assert hashlib.sha256(session['token'].encode()).hexdigest()==a['tokenSha256']
assert hashlib.sha256(ticket['ticketBody'].encode()).hexdigest()==a['ticketSha256']
assert sha(candidates/'actual-session-token.json')==a['privateCandidateSessionFileSha256']
assert sha(candidates/'actual-realtime-ticket.json')==a['privateCandidateTicketFileSha256']
v=a['actualPublicReview'];assert v['ok'] and v['sanitized_metadata_public_review_passed']
assert v['raw_values_written_to_public_report'] is False and v['raw_private_candidates_unchanged']
rows=v['actual_sensitive_candidates_rejected'];assert len(rows)==2
for row,field in zip(rows,['token','ticketbody']):
    assert row['actual_rejection_messages']==['Sensitive field in public evidence: '+field]*2
    assert row['original_sensitive_candidate_preserved']
    path=candidates/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
safe=G/'evidence/persistent-output/public-review-sanitized.original.json'
assert session['token'] not in safe.read_text() and ticket['ticketBody'] not in safe.read_text()
assert read(safe)['actual_sensitive_candidates_rejected']==rows
for path in (G/'evidence').rglob('*'):
    if path.is_file() and path.suffix in ['.json','.jsonl','.log','.trx']:
        raw=path.read_bytes();assert session['token'].encode() not in raw and ticket['ticketBody'].encode() not in raw
assert manifest['production_credentials_not_included'] and manifest['generated_ephemeral_test_credentials_included_in_private_G_archive']
domain = G/'work/artifacts/bin/FantasyCard.Domain/release/FantasyCard.Domain.dll'
tests = G/'work/artifacts/bin/FantasyCard.Server.Tests/release/FantasyCard.Server.Tests.dll'
assert sha(domain)==plan['production_domain_assembly_sha256']=='844065af3158b40787699752915ed95befbd3c660c2b10dce501f9f4fc29e352'
proof={'ok':True,'case_id':'LOAD-06.4-T03','profile':'POSTGRES','actual_native_PG_rows':10,
    'native_clean':True,'owned_container_removed':True,'source_inputs_match_git':True,
    'original_nine_regression_rows':9,'new_sensitive_boundary_methods':1,'native_skipped':0,
    'all_original_G_members_rehashed':len(manifest['files']),'archive_SHA_and_CRC_rechecked':True,
    'current_source_members':328,'implementation_source_sha':head,
    'actual_private_schema_session_and_actual_issued_ticket_verified':True,
    'both_current_public_inspect_and_manifest_entries_rejected':True,
    'raw_values_absent_from_all_public_evidence_and_receipts':True,
    'private_G_contains_generated_ephemeral_test_credentials':True,
    'production_credentials_used':False,'production_domain_assembly_unchanged':True,'actual':a,
    'all_other_canonical_profiles_retained':True,'MAIN_accepted':False}
OUT.mkdir();(OUT/'independent-G-check.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in proof.items() if k!='actual'}))
