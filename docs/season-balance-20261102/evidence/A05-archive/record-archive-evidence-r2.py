from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as E
repo=Path.cwd();b=Path(__file__).parent;e=repo/'docs/season-balance-20261102/evidence/A05-archive'
audit=json.loads((b/'runtime-r92/collection-audit.json').read_text(encoding='utf-8'))
assert audit['exit_code']==0 and not audit['oom_killed'] and audit['binary_payload_unchanged'] and audit['counts']['passed']=='34' and audit['counts']['failed']=='0' and audit['counts']['notExecuted']=='0'
cleanup=json.loads((b/'runtime-r92/cleanup.original.log').read_text(encoding='utf-8'));assert cleanup['private_environment_removed'] and cleanup['all_original_evidence_retained']
assert not e.exists();e.mkdir(parents=True)
def copy(n):
 p=b/n;q=e/n;assert p.is_file(),p;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
for name in ['local-archive-build-r1','local-archive-build-r2','local-archive-pg-r2','local-archive-pg-r3','runtime-r92']:
 for p in (b/name).iterdir():
  if p.is_file() and p.suffix in ['.json','.jsonl','.log','.cs','.py']:copy(p.relative_to(b).as_posix())
 for p in (b/name/'results').glob('*.trx'):copy(p.relative_to(b).as_posix())
 if (b/name/'frozen-source').exists():shutil.copytree(b/name/'frozen-source',e/name/'frozen-source')
 if (b/name/'public').exists():shutil.copytree(b/name/'public',e/name/'public')
for p in (b/'storage-r91').iterdir():
 if p.is_file() and p.suffix in ['.json','.log','.py']:copy(p.relative_to(b).as_posix())
shutil.copytree(b/'storage-r91/public',e/'storage-r91/public')
for n in ['run-local-archive-build-r1.py','run-local-archive-build-r2.py','run-local-archive-pg-r2.py','run-local-archive-pg-r3.py','prepare-season-archive-r91.py','ship-season-archive-r91.py','observe-season-archive-r91.py','collect-season-archive-r91.py','start-archive-runtime-r92.py','observe-archive-runtime-r92.py','collect-archive-runtime-r92.py','retire-theme-expanded-v19.py','retire-archive-expanded-v20.py','archive-market-expanded-v19.py','archive-market-expanded-v20.py','ended-expanded-inputs-v19.json','ended-expanded-inputs-v20.json','v19-local-verification.json','v20-local-verification.json','archive-cloud-preflight-r1.original.json','runtime-r92-preflight.original.json','archive-toolchain.original.json','record-archive-evidence-r1.py','record-archive-evidence-r2.py']:
 copy(n)
for version in [19,20]:
 for kind in ['prepare','download','retire','offload']:
  p=b/f'v{version}-{kind}.original.log'
  if p.exists():copy(p.name)
cases={};runs=[];failed=[]
for p in [b/'storage-r91/public/season-archive-server.trx',b/'runtime-r92/public/results/season-archive-runtime.trx']:
 counts=dict(passed=0,failed=0,skipped=0)
 for n in E.parse(p).iter():
  if not n.tag.endswith('UnitTestResult'):continue
  outcome=n.get('outcome');name=n.get('testName')
  if outcome=='Passed':counts['passed']+=1;cases[name]=dict(source=str(p.relative_to(b)),test_id=n.get('testId'),outcome=outcome)
  elif outcome=='Failed':counts['failed']+=1;failed.append(dict(source=str(p.relative_to(b)),name=name))
  else:counts['skipped']+=1
 runs.append(counts)
assert runs==[dict(passed=73,failed=32,skipped=0),dict(passed=34,failed=0,skipped=0)] and len(cases)==106,(runs,len(cases))
(e/'server-case-union.json').write_text(json.dumps(dict(count=106,union_not_one_physical_run=True,runs=runs,cases=cases,original_failed_cases_preserved=failed),indent=2)+'\n',encoding='utf-8')
current=json.loads((b/'local-archive-build-r2/source-pin.json').read_text(encoding='utf-8'))
for n,h in current.items():assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h,n
cloud=[json.loads(x) for x in (b/'runtime-r92/public/resource-guard.original.jsonl').read_text(encoding='utf-8').splitlines()]
assert all(x['available_ram']>=500*1024**2 and x['free_disk']>=3*1024**3 and x['disk_fraction']>=.05 for x in cloud)
guard=json.loads((b/'runtime-r92/public/guard-terminal.original.json').read_text(encoding='utf-8'));assert guard['state']=='exited' and guard['exit_code']==0
result=dict(status='A05_backend_complete_current_scope',A05_complete=True,whole_goal_complete=False,completed_items=20,configuration='season-v1-config-12',migration='V048__season_archive_pages.sql',new_archive_PG_tests=8,server_case_union=106,union_not_one_physical_run=True,r91_initial=dict(passed=73,failed=32,skipped=0),runtime_r92=dict(passed=34,failed=0,skipped=0,seconds=67.951,precompiled_on_local=True,SDK='10.0.400',cloud_SDK_started=False,payload_sha256='a6407b48c78e50dbcf5dc326951925621f5bd21feb7122daec989c71fb64d6a5'),cloud_guard_samples=len(cloud),cloud_min_ram=min(x['available_ram'] for x in cloud),cloud_min_disk=min(x['free_disk'] for x in cloud),cloud_min_disk_fraction=min(x['disk_fraction'] for x in cloud),owned_runtime_removed=True,SDK_r91_removed=True,new_full_routes=0,B05_budget='291/300',C16_encounter_budget='121/300',capacity100_retest=False,production_deployed=False,production_restarted=False,season_activated=False,retained_failures=['r91 native positional SQL combined multiple commands: seven archive tests failed','r91 current-version fixture hashes were placeholders: twenty-five tests failed','r2 missing Configuration namespace: compiler failed, zero PG cases','r3 observer timed out after900s; eventual TRX7passed27connection failures, whole batch rejected; incomplete stdout explicitly retained as a gap','r92 runtime helper preparation syntax failed before any cloud action; preserved separate from actual test outcomes'],scope=['Real PostgreSQL page atomicity, stable item identity, source-season isolation, preserved original armor references and permanent aggregate','Concurrent account-first workers, injected mid-page rollback and original durable cursor through repository recreation','Full-warehouse market hold identity, old-room waiting, original late wallet credit','Hosted background execution without an online client; actual pre-start cancellation releases assets and no longer prevents archive'],remaining=['Full OS-process crash/restart fault matrix remains F02; repository recreation is not claimed as that proof.','Archive collection UI remains E01/E02.','C15 exact tier rewards and C16 combat balance remain unaccepted.'],runtime_log_note='Runtime image emitted a missing optional libgssapi_krb5.so.2 notice. The configured password PostgreSQL path passed; Kerberos authentication is not asserted.',external_original_evidence_root=str(b))
(e/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
manifest={p.relative_to(e).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in e.rglob('*') if p.is_file()}
(e/'manifest.json').write_text(json.dumps(dict(files=manifest,external_original_evidence_root=str(b)),indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
