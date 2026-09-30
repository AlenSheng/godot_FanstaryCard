"""Verify immutable packet metadata and exact-source provenance; only judge .1."""
import argparse,hashlib,json,pathlib,subprocess
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--packet',required=True);p.add_argument('--output',required=True);a=p.parse_args()
src=pathlib.Path(a.source).resolve();packet=pathlib.Path(a.packet).resolve();out=pathlib.Path(a.output)
sha='e06037f58738d0fbff86090e86d8bd06f8608e04';receipt='c68bd4aadf59676096b93ce8e5a972b12575cc08'
def read(p):return json.loads(p.read_text())
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=src,text=True).strip()
assert git('rev-parse','HEAD')==sha and not git('status','--porcelain=v1')
m=read(packet/'MANIFEST.json');manifest_checks=[]
for r in m['files']:
    f=packet/r['path'];manifest_checks.append(dict(path=r['path'],matches=f.stat().st_size==r['bytes'] and h(f)==r['sha256']))
assert all(r['matches'] for r in manifest_checks)
source_checks=[]
for r in read(packet/'SOURCE_PROOF.json')['files']:
    b=(src/r['path']).read_bytes();blob=subprocess.check_output(['git','show',sha+':'+r['path']],cwd=src)
    source_checks.append(dict(path=r['path'],bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),matches=len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'] and b==blob))
assert all(r['matches'] for r in source_checks)
tests=[]
for name in git('ls-files','tools/tests').splitlines():
    b=(src/name).read_bytes();assert b==subprocess.check_output(['git','show',sha+':'+name],cwd=src)
    tests.append(dict(path=name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),matches_exact_sha=True))
plan=read(src/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json');fields=plan['evidence_contract']['report_fields'];contract=next(p for p in plan['packages'] if p['id']=='LOAD-01')['subtasks'][0]
task=next(t for t in read(packet/'REPORT.json')['tasks'] if t['task_id']=='LOAD-01.1');meta=[]
for r in [task]+task['stage_receipts']:
    check=dict(stage=r['stage'],missing_fields=[f for f in fields if f not in r],unexplained_nulls=[f for f in fields if r.get(f,'MISSING') is None and not r['missing_reasons'].get(f)],profile_matches=r['profile_hash']==h(packet/'PROFILE.json'),algorithm_matches=r['algorithm_version']=='sha256:'+h(packet/'ALGORITHM_SOURCE.json'),integration_sha_matches=r['integration_sha']==sha)
    assert not check['missing_fields'] and not check['unexplained_nulls'] and check['profile_matches'] and check['algorithm_matches'] and check['integration_sha_matches'];meta.append(check)
algorithm=read(packet/'ALGORITHM_SOURCE.json');assert all(h(src/name)==value for name,value in algorithm.items())
old_harness=pathlib.Path('/workspace/pr13-main-review/receipts/new/docs/reports/pr13-takeover-20260930/schema-safety-ee8adcf4/run_load01_acceptance.py').read_text();new_harness=(packet/'run_load01.py').read_text();assert old_harness.replace('ee8adcf40be9aebb1330156a3524910c08225ebc',sha)==new_harness
deps=read(pathlib.Path('/workspace/pr13-main-review/receipts/old/docs/reports/pr13-takeover-20260930/offline-acceptance-f812/load01/MINIMAL_DEPENDENCY_INPUTS.json'))
runtime_delta=git('diff','--name-only','ee8adcf40be9aebb1330156a3524910c08225ebc',sha,'--','tools','client','server','protocol','config').splitlines()
assert set(runtime_delta)==set(['tools/gameplay_load_validation.py','tools/pr13_runtime_evidence.py','tools/tests/test_gameplay_load_validation.py','tools/tests/test_pr13_runtime_evidence.py'])
receipt_runtime_delta=git('diff','--name-only',sha,receipt,'--','tools','client','server','protocol','config').splitlines();assert not receipt_runtime_delta
result=dict(only_adjudicated_task='LOAD-01.1',integration_sha=sha,receipt_commit=receipt,packet_manifest_entries=len(manifest_checks),packet_manifest_mismatches=[r['path'] for r in manifest_checks if not r['matches']],source_files=source_checks,test_files=tests,metadata_checks=meta,packet_profile_hash=h(packet/'PROFILE.json'),packet_algorithm_version='sha256:'+h(packet/'ALGORITHM_SOURCE.json'),canonical_plan_hash=h(src/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'),canonical_contract=contract,canonical_harness_only_expected_SHA_changed=True,runtime_delta_from_ee8=runtime_delta,runtime_delta_fixed_to_receipt=receipt_runtime_delta,minimum_dependencies=deps,dependency_assessment='LOAD-11.1 minimal source/hash provenance and LOAD-06.4 local identity/time/null/redaction contract present; no whole upstream Accepted prerequisite.',rules='server/AGENTS.md read; no root/tools AGENTS or .agents/skills in the pinned tree. Existing canonical missing-server_create exception retained; no server work or extra gate.',documentation_notes=['Implementation S1 prose still mentions f812 although referenced before-ee8 evidence reproduces the three ee8 defects. Actual before/after SHA and traces are separately pinned in the prior independent review.','Implementation rollback text names only gameplay_load_validation.py; independent rollback is git revert e06037f5, restoring both changed runtime files and their tests.','Implementation MAIN source URL was null with a reason; independent S6 now cites dac6fdbd43d9c925a696a18f9774d9392c06c302. These historical documentation leftovers do not create new runtime gates.'])
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(packet_manifest_entries=len(manifest_checks),source_files=len(source_checks),test_files=len(tests),metadata_rows=len(meta),all_verified=True,canonical_harness_assertions_unchanged=True),ensure_ascii=False))
