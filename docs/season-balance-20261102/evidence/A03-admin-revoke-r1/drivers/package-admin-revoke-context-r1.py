from pathlib import Path
import gzip,hashlib,importlib.util,json,shlex,subprocess,xml.etree.ElementTree as ET

repo=Path.cwd();base=Path(__file__).parent;runtime=base/'runtime-r111';target=repo/'docs/season-balance-20261102/evidence/A03-admin-revoke-r1';assert not target.exists();target.mkdir()
spec=importlib.util.spec_from_file_location('public',repo/'tools/pr13_public_evidence.py');public=importlib.util.module_from_spec(spec);spec.loader.exec_module(public)
audit=json.loads((runtime/'collection-audit.json').read_bytes());assert audit['exit_code']==0 and not audit['oom_killed'] and audit['counts']['passed']=='33' and audit['counts']['failed']=='0' and audit['counts']['notExecuted']=='0'
assert hashlib.sha256((runtime/'public-evidence.tar.gz').read_bytes()).hexdigest()==audit['public_archive_sha256']
assert all(hashlib.sha256((runtime/'public'/n).read_bytes()).hexdigest()==h for n,h in audit['files'].items())
pin=json.loads((base/'admin-revoke-local-r2/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
code="from pathlib import Path;import json;root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r111');p=root/'input-tmpfs-cleanup.json';data=json.loads(p.read_text());assert data['owned_input_tmpfs_unmounted'];print(json.dumps(data))"
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182','sudo -n python3 -c '+shlex.quote(code)],capture_output=True,text=True,timeout=35)
(runtime/'tmpfs-cleanup-verification.original.json').write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');assert r.returncode==0 and json.loads(r.stdout)['owned_input_tmpfs_unmounted']
raws={}
def copy(p,name):
 raw=p.read_bytes();public.inspect_public_bytes(p,raw);dest=target/name;packed=len(raw)>150000 and p.suffix in ('.json','.jsonl','.log')
 if packed:dest=dest.with_name(dest.name+'.gz')
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(gzip.compress(raw,mtime=0) if packed else raw);raws[str(name)]={'sha256':hashlib.sha256(raw).hexdigest(),'stored':dest.relative_to(target).as_posix(),'gzip':packed}
for p in runtime.rglob('*'):
 if not p.is_file() or p.name.startswith(('payload','transport-stream')) or any(part in ('input','build') for part in p.relative_to(runtime).parts):continue
 if p.suffix in ('.json','.log','.py','.trx','.xml','.gz'):copy(p,Path('runtime-r111')/p.relative_to(runtime))
for stage in ['admin-revoke-local-r1','admin-revoke-local-r2']:
 for name in ['source-pin.json','result.json','build-and-tests.original.log','results/mail-local.trx','interrupted.original.json']:
  if (base/stage/name).is_file():copy(base/stage/name,Path(stage)/name)
for name in ['run-admin-revoke-local-r1.py','run-admin-revoke-local-r2.py','prepare-admin-runtime111-control.py','prepare-runtime111-tmpfs-control.py','finish-runtime111-control-files.py','setup-mail-runtime111-file-transfer.py','transfer-r111-stream-sftp.py','verify-r111-complete-stream.py','start-r111-from-verified-file.py','observe-admin-revoke-r111.py','collect-admin-revoke-r111.py','package-admin-revoke-context-r1.py']:copy(base/name,Path('drivers')/name)
groups={}
for test in ET.fromstring((runtime/'public/results/xunit.original.xml').read_bytes()).iter('test'):
 assert test.attrib['result']=='Pass';name=test.attrib['type'].split('.')[-1];groups[name]=groups.get(name,0)+1
assert groups['PostgresAdminRevokeContextTests']==8 and sum(groups.values())==33
result={'status':'admin_revoke_exact_currency_and_original_equipment_context_subchain_verified','local_passed':34,'runtime_passed':33,'runtime_groups':groups,'new_revoke_cases':8,'failed':0,'skipped':0,'local_initial_admission_rejection_preserved':True,'input_preparation_collision_before_Native_preserved':True,'historical_ClassSoul_rows_unchanged':True,'new_class_soul_currencies_exact':True,'original_season_context_after_new_unavailable_definition_verified':True,'legacy_unknown_versions_not_inferred':True,'equipment_generated_difficulty_unchanged':True,'D0_movement_is_account_context_not_a_generated_drop':True,'rollback_and_same_key_retry_verified':True,'tmpfs_unmounted':True,'private_env_removed':True,'runtime_removed':True,'source_and_binary_SHA_verified':True,'local_reserve_GiB':2,'cloud_guards_unchanged':True,'new_UI_or_protocol_structure_change':False,'new_full_routes':0,'new_balance_encounters':0,'capacity100_retest':False,'production_restarted':False,'overall_completed_items':21,'A03_A04_complete':False,'remaining_source_audit':['Admin bulk equipment grant has an operation count audit but no per-item movement provenance.','Other asset classes and complete process failure recovery still need composite audit.']}
(target/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');(target/'raw-text-manifest.json').write_text(json.dumps(raws,indent=2)+'\n',encoding='utf-8')
files={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}
(target/'manifest.json').write_text(json.dumps({'files':files,'full_original_directory':str(base)},indent=2)+'\n',encoding='utf-8');print(json.dumps({'files':len(files),'local_passed':34,'runtime_passed':33,'new_cases':8,'overall':'21/35'}))
