from pathlib import Path
import gzip,hashlib,importlib.util,json,shlex,subprocess,xml.etree.ElementTree as ET

repo=Path.cwd();base=Path(__file__).parent;runtime=base/'runtime-r112';target=repo/'docs/season-balance-20261102/evidence/A03-admin-equipment-r1';assert not target.exists();target.mkdir()
spec=importlib.util.spec_from_file_location('public',repo/'tools/pr13_public_evidence.py');public=importlib.util.module_from_spec(spec);spec.loader.exec_module(public)
audit=json.loads((runtime/'collection-audit.json').read_bytes());assert audit['exit_code']==0 and not audit['oom_killed'] and audit['counts']['passed']=='36' and audit['counts']['failed']=='0' and audit['counts']['notExecuted']=='0'
assert hashlib.sha256((runtime/'public-evidence.tar.gz').read_bytes()).hexdigest()==audit['public_archive_sha256']
assert all(hashlib.sha256((runtime/'public'/n).read_bytes()).hexdigest()==h for n,h in audit['files'].items())
pin=json.loads((base/'admin-equipment-local-r1/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
code="from pathlib import Path;import json;p=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r112/input-tmpfs-cleanup.json');data=json.loads(p.read_text());assert data['owned_input_tmpfs_unmounted'];print(json.dumps(data))"
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182','sudo -n python3 -c '+shlex.quote(code)],capture_output=True,text=True,timeout=35)
(runtime/'tmpfs-cleanup-verification.original.json').write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');assert r.returncode==0 and json.loads(r.stdout)['owned_input_tmpfs_unmounted']
raws={}
def copy(p,name):
 raw=p.read_bytes();public.inspect_public_bytes(p,raw);dest=target/name;packed=len(raw)>150000 and p.suffix in ('.json','.jsonl','.log')
 if packed:dest=dest.with_name(dest.name+'.gz')
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(gzip.compress(raw,mtime=0) if packed else raw);raws[str(name)]={'sha256':hashlib.sha256(raw).hexdigest(),'stored':dest.relative_to(target).as_posix(),'gzip':packed}
for p in runtime.rglob('*'):
 if not p.is_file() or p.name.startswith(('payload','transport-stream')) or any(part in ('input','build') for part in p.relative_to(runtime).parts):continue
 if p.suffix in ('.json','.log','.py','.trx','.xml','.gz'):copy(p,Path('runtime-r112')/p.relative_to(runtime))
for name in ['source-pin.json','result.json','build-and-tests.original.log','results/mail-local.trx']:copy(base/'admin-equipment-local-r1'/name,Path('local')/name)
for name in ['run-admin-equipment-local-r1.py','prepare-runtime112-controls.py','setup-mail-runtime112-file-transfer.py','transfer-r112-stream-sftp.py','verify-r112-complete-stream.py','start-r112-from-verified-file.py','observe-admin-equipment-r112.py','collect-admin-equipment-r112.py','package-admin-equipment-provenance-r1.py']:copy(base/name,Path('drivers')/name)
groups={}
for test in ET.fromstring((runtime/'public/results/xunit.original.xml').read_bytes()).iter('test'):
 assert test.attrib['result']=='Pass';name=test.attrib['type'].split('.')[-1];groups[name]=groups.get(name,0)+1
assert groups['PostgresAdminEquipmentProvenanceTests']==3 and sum(groups.values())==36
result={'status':'admin_bulk_equipment_per_item_provenance_subchain_verified_composite_audit_pending','local_passed':34,'runtime_passed':36,'new_bulk_equipment_cases':3,'runtime_groups':groups,'failed':0,'skipped':0,'new_item_GUIDs_match_movements':True,'legacy_unknown_context_not_inferred':True,'existing_item_bytes_unchanged':True,'parallel_distinct_requests_and_same_key_conflict_verified':True,'movement_fault_rolls_back_all_mints_and_audit':True,'old_grant_specification_range_unchanged':True,'tmpfs_unmounted':True,'runtime_removed':True,'private_env_removed':True,'local_reserve_GiB':2,'cloud_guards_unchanged':True,'next_base_runtime109_preserved':True,'new_UI_or_protocol_structure_change':False,'new_full_routes':0,'new_balance_encounters':0,'capacity100_retest':False,'production_restarted':False,'overall_completed_items':21,'A03_A04_complete':False}
(target/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');(target/'raw-text-manifest.json').write_text(json.dumps(raws,indent=2)+'\n',encoding='utf-8')
files={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}
(target/'manifest.json').write_text(json.dumps({'files':files,'full_original_directory':str(base)},indent=2)+'\n',encoding='utf-8');print(json.dumps({'files':len(files),'local_passed':34,'runtime_passed':36,'new_cases':3}))
