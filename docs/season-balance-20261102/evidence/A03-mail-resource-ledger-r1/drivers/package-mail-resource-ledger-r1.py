from pathlib import Path
import base64,gzip,hashlib,importlib.util,json,shlex,subprocess,xml.etree.ElementTree as ET

repo=Path.cwd();base=Path(__file__).parent;runtime=base/'runtime-r110';target=repo/'docs/season-balance-20261102/evidence/A03-mail-resource-ledger-r1';assert not target.exists();target.mkdir()
spec=importlib.util.spec_from_file_location('public',repo/'tools/pr13_public_evidence.py');public=importlib.util.module_from_spec(spec);spec.loader.exec_module(public)
audit=json.loads((runtime/'collection-audit.json').read_bytes());assert audit['exit_code']==0 and not audit['oom_killed'] and audit['counts']['passed']=='25' and audit['counts']['failed']=='0' and audit['counts']['notExecuted']=='0'
assert hashlib.sha256((runtime/'public-evidence.tar.gz').read_bytes()).hexdigest()==audit['public_archive_sha256']
assert all(hashlib.sha256((runtime/'public'/n).read_bytes()).hexdigest()==h for n,h in audit['files'].items())
pin=json.loads((base/'mail-resource-local-r1/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
code="from pathlib import Path;import json;root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r110');p=root/'input-tmpfs-cleanup.json';data=json.loads(p.read_text());assert data['owned_input_tmpfs_unmounted'];print(json.dumps(data))"
command='sudo -n python3 -c '+shlex.quote(code)
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=35)
(runtime/'tmpfs-cleanup-verification.original.json').write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');assert r.returncode==0 and json.loads(r.stdout)['owned_input_tmpfs_unmounted']
raws={}
def copy(p,name):
 raw=p.read_bytes();public.inspect_public_bytes(p,raw);dest=target/name;compressed=len(raw)>150000 and p.suffix in ('.json','.jsonl','.log')
 if compressed:dest=dest.with_name(dest.name+'.gz')
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(gzip.compress(raw,mtime=0) if compressed else raw)
 raws[str(name)]={'sha256':hashlib.sha256(raw).hexdigest(),'stored':dest.relative_to(target).as_posix(),'gzip':compressed}
for p in runtime.rglob('*'):
 if not p.is_file() or p.name.startswith(('payload','transport-stream')) or any(part in ('input','build') for part in p.relative_to(runtime).parts):continue
 if p.suffix in ('.json','.log','.py','.trx','.xml','.gz'):copy(p,Path('runtime-r110')/p.relative_to(runtime))
for name in ['source-pin.json','result.json','build-and-tests.original.log','results/mail-local.trx']:copy(base/'mail-resource-local-r1'/name,Path('local')/name)
for name in ['run-mail-resource-local-r1.py','prepare-runtime110-tmpfs-control.py','setup-mail-runtime110-file-transfer.py','transfer-r110-stream-sftp.py','verify-r110-complete-stream.py','start-r110-from-verified-file.py','observe-mail-resource-r110.py','collect-mail-resource-r110.py','checkpoint-isolated-postgres-r110.py','retire-runtime108-expanded-input-r1.py','package-mail-resource-ledger-r1.py']:copy(base/name,Path('drivers')/name)
copy(base/'runtime-r108/input-retirement-verified-local-r1.original.json',Path('retirement/runtime108-input.original.json'))
groups={}
for test in ET.fromstring((runtime/'public/results/xunit.original.xml').read_bytes()).iter('test'):
 assert test.attrib['result']=='Pass';name=test.attrib['type'].split('.')[-1];groups[name]=groups.get(name,0)+1
assert groups['PostgresMailPermanentCopyTests']==14 and sum(groups.values())==25
result={'status':'mail_currency_and_equipment_source_subchain_verified_A03_A04_still_open','local_passed':25,'isolated_runtime_passed':25,'runtime_groups':groups,'new_mail_resource_cases':6,'failed':0,'skipped':0,'binary_payload_unchanged':True,'currency_count':7,'unknown_legacy_context_not_inferred':True,'old_receipts_and_ledgers_not_rewritten':True,'source_kind':'LegacyMail','mail_ID_source_preserved':True,'owned_tmpfs_bytes':67108864,'tmpfs_actual_payload_bytes':27618768,'tmpfs_unmounted':True,'private_env_removed':True,'runtime_removed':True,'local_reserve_GiB':2,'cloud_min_admission_MiB':1864,'cloud_floor_RAM_MiB':500,'cloud_floor_disk_GiB':3,'cloud_floor_disk_ratio':0.05,'cloud_disk_margin_MiB':64,'next_base_runtime109_preserved':True,'cloud_SDK_started':False,'new_UI_or_protocol_change':False,'new_full_routes':0,'new_balance_encounters':0,'capacity100_retest':False,'production_restarted':False,'overall_completed_items':21,'remaining_known_gaps':['AdminRevoke writes exact class souls as aggregate ClassSoul, so later exact-class spending can break its chain; no existing rows should be guessed or rewritten.','Admin equipment revoke of seasonal item still needs full original movement context audit.','Other asset classes and complete process recovery remain A03/A04/F02 scope.']}
(target/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
(target/'raw-text-manifest.json').write_text(json.dumps(raws,indent=2)+'\n',encoding='utf-8')
files={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}
(target/'manifest.json').write_text(json.dumps({'files':files,'full_original_directory':str(base)},indent=2)+'\n',encoding='utf-8');print(json.dumps({'files':len(files),'runtime_passed':25,'local_passed':25,'A03_complete':False}))
