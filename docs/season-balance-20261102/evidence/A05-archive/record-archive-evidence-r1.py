from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as E
repo=Path.cwd();b=Path(__file__).parent;e=repo/'docs/season-balance-20261102/evidence/A05-archive'
final=json.loads((b/'local-archive-pg-r3/result.json').read_text(encoding='utf-8'));tunnel=json.loads((b/'local-archive-pg-r3/owned-tunnel-terminal.json').read_text(encoding='utf-8'))
assert final['exit']==0 and final['source_unchanged'] and final['cloud_guard_ok'] and tunnel['exit_code']==0 and not tunnel['cloud_guard_failed']
assert not e.exists();e.mkdir(parents=True)
def copy(n):
 p=b/n;q=e/n;assert p.is_file(),p;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
for name in ['local-archive-build-r1','local-archive-pg-r2','local-archive-pg-r3']:
 for p in (b/name).iterdir():
  if p.is_file() and p.suffix in ['.json','.jsonl','.log','.cs']:copy(p.relative_to(b).as_posix())
 for p in (b/name/'results').glob('*.trx'):copy(p.relative_to(b).as_posix())
for p in (b/'storage-r91').iterdir():
 if p.is_file() and p.suffix in ['.json','.log','.py']:copy(p.relative_to(b).as_posix())
shutil.copytree(b/'storage-r91/public',e/'storage-r91/public')
for n in ['run-local-archive-build-r1.py','run-local-archive-pg-r2.py','run-local-archive-pg-r3.py','prepare-season-archive-r91.py','ship-season-archive-r91.py','observe-season-archive-r91.py','collect-season-archive-r91.py','retire-theme-expanded-v19.py','retire-archive-expanded-v20.py','archive-market-expanded-v19.py','archive-market-expanded-v20.py','ended-expanded-inputs-v19.json','ended-expanded-inputs-v20.json','v19-local-verification.json','v20-local-verification.json','archive-cloud-preflight-r1.original.json','record-archive-evidence-r1.py']:
 copy(n)
for version in [19,20]:
 for kind in ['prepare','download','retire','offload']:
  p=b/f'v{version}-{kind}.original.log'
  if p.exists():copy(p.name)
cases={};runs=[];failed=[]
for p in [b/'storage-r91/public/season-archive-server.trx',b/'local-archive-pg-r3/results/archive-followup.trx']:
 counts=dict(passed=0,failed=0,skipped=0)
 for n in E.parse(p).iter():
  if not n.tag.endswith('UnitTestResult'):continue
  outcome=n.get('outcome');name=n.get('testName')
  if outcome=='Passed':counts['passed']+=1;cases[name]=dict(source=str(p.relative_to(b)),test_id=n.get('testId'),outcome=outcome)
  elif outcome=='Failed':counts['failed']+=1;failed.append(dict(source=str(p.relative_to(b)),name=name))
  else:counts['skipped']+=1
 runs.append(counts)
assert runs==[dict(passed=73,failed=32,skipped=0),dict(passed=34,failed=0,skipped=0)] and len(cases)==106
(e/'server-case-union.json').write_text(json.dumps(dict(count=106,union_not_one_physical_run=True,runs=runs,cases=cases,original_failed_cases_preserved=failed),indent=2)+'\n',encoding='utf-8')
current=json.loads((b/'local-archive-pg-r3/source-pin.json').read_text(encoding='utf-8'))
for n,h in current.items():assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h,n
cloud=[json.loads(x) for x in (b/'local-archive-pg-r3/cloud-resource.original.jsonl').read_text(encoding='utf-8').splitlines()];assert all(x['guard_ok'] for x in cloud)
result=dict(status='A05_backend_complete_current_scope',A05_complete=True,whole_goal_complete=False,completed_items=20,configuration='season-v1-config-12',migration='V048__season_archive_pages.sql',new_archive_PG_tests=8,server_case_union=106,union_not_one_physical_run=True,r91_initial=dict(passed=73,failed=32,skipped=0),followup=dict(passed=34,failed=0,skipped=0),cloud_guard_samples=len(cloud),cloud_min_ram=min(x['available_ram'] for x in cloud),cloud_min_disk=min(x['free_disk'] for x in cloud),cloud_min_disk_fraction=min(x['disk_fraction'] for x in cloud),owned_tunnel_closed=True,cloud_SDK_started_for_followup=False,SDK_r91_removed=True,new_full_routes=0,B05_budget='291/300',C16_encounter_budget='121/300',capacity100_retest=False,production_deployed=False,production_restarted=False,season_activated=False,retained_failures=['r91 archive native positional SQL combined multiple commands: seven tests failed','r91 older current-version fixture hashes were placeholder values: twenty-five tests failed','r2 missing Configuration namespace: compiler failed, zero database cases'],scope=['Actual PostgreSQL atomic page, stable item identity, source-season isolation, original loadout references and permanent aggregate preservation','Concurrent account-first workers, injected mid-page rollback, same durable cursor through repository recreation','Existing full-warehouse market hold identity, old-room waiting without actor mutation, original late wallet credit','Hosted background worker completes without any online native client'],remaining=['Full OS-process crash/restart fault matrix is still F02; it is not proven by recreating a repository.','Archive collection UI is still E01/E02.','C15 exact tier rewards and C16 combat balance remain unaccepted.'],external_original_evidence_root=str(b))
(e/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
manifest={p.relative_to(e).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in e.rglob('*') if p.is_file()}
(e/'manifest.json').write_text(json.dumps(dict(files=manifest,external_original_evidence_root=str(b)),indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
