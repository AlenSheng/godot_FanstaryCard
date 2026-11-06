from pathlib import Path
import json,hashlib,shutil,xml.etree.ElementTree as E
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');target=repo/'docs/season-balance-20261102/evidence/A04-reward-refresh-funding-r1'
assert not target.exists()
a102=json.loads((b/'runtime-r102/collection-audit.json').read_text(encoding='utf-8'))
a103=json.loads((b/'runtime-r103/collection-audit.json').read_text(encoding='utf-8'))
assert a102['counts']['passed']=='15' and a102['counts']['failed']=='2' and a102['counts']['notExecuted']=='0'
assert a103['counts']['passed']=='16' and a103['counts']['failed']=='0' and a103['counts']['notExecuted']=='0' and a103['exit_code']==0
for stage,a in [('runtime-r102',a102),('runtime-r103',a103)]:
 assert hashlib.sha256((b/stage/'public-evidence.tar.gz').read_bytes()).hexdigest()==a['public_archive_sha256']
 for n,h in a['files'].items():assert hashlib.sha256((b/stage/'public'/n).read_bytes()).hexdigest()==h
 assert list((b/stage).glob('cleanup*.original.log'))
finalpins=json.loads((b/'local-refresh-funding-build-r4/source-pin.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in finalpins.items())
oldpins=json.loads((b/'local-refresh-funding-core-r2/source-pin.json').read_text(encoding='utf-8'))
assert all(oldpins[n]==h for n,h in finalpins.items() if n.startswith(('server/src/','server/tools/')))
selected=[]
for stage in ['runtime-r101','runtime-r102','runtime-r103']:
 for p in (b/stage).rglob('*'):
  if p.is_file() and p.name not in ['payload.tar.gz','public-evidence.tar.gz']:selected.append(p)
for name in ['local-refresh-funding-build-r1','local-refresh-funding-build-r2','local-refresh-funding-build-r3','local-refresh-funding-build-r4','local-refresh-funding-core-r1','local-refresh-funding-core-r2']:
 for p in (b/name).rglob('*'):
  if p.is_file() and (p.parent==b/name or p.parent.name=='results'):selected.append(p)
for pattern in ['*-refresh-funding-*.py','cleanup-failed-runtime-r102.py','prepare-precompiled-runtime-bundle.py','retire-verified-runtime-inputs-r3.py','runtime-r100-input-retirement-r3.original.log','runtime-r102-input-retirement-r3.original.log']:
 selected+=list(b.glob(pattern))
for p in set(selected):
 out=target/p.relative_to(b);out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out);assert out.read_bytes()==p.read_bytes()
passed={}
for stage in ['runtime-r102','runtime-r103']:
 for node in E.parse(b/stage/'public/results/season-archive-runtime.trx').getroot().iter():
  if node.tag.endswith('UnitTestResult') and node.get('outcome')=='Passed':passed.setdefault(node.get('testName'),[]).append(stage)
assert len(passed)==17
(target/'case-union.json').write_text(json.dumps(dict(distinct_PG_passed=17,not_one_17_pass_batch=True,batches={'runtime-r102':{'passed':15,'failed':2},'runtime-r103':{'passed':16,'failed':0}},cases=passed),indent=2)+'\n',encoding='utf-8')
result=dict(status='reward_refresh_original_quote_and_payer_verified_A03_A04_open',A03_complete=False,A04_complete=False,whole_goal_complete=False,completed_items=20,
 local_final_passed=7,local_final_failed=0,PG_final_batch_passed=16,PG_final_batch_failed=0,PG_final_batch_skipped=0,PG_distinct_passed=17,
 historical_failures_retained={'local_core_r1':{'passed':2,'failed':5,'reason':'Obsolete shared test fixture removed coupled preference tables.'},'local_build_r2':{'tests':0,'errors':2,'reason':'Nullable test row key cast rejected by compiler.'},'runtime_r102':{'passed':15,'failed':2,'reason':'New choice checkpoint fixtures lacked their original preparation link; strict policy validation retained.'}},
 prepared_runtime_r101_not_started=True,production_sources_unchanged_between_core_and_PG=True,source_unchanged=True,
 migration='V049 records actual wallet payer; pre-V049 reservations remain LegacyWallet with unknown historical config fields left NULL.',
 scopes=['Original actor catalog quotes refresh cost and temporary gold split','Admitted original seasonal wallet funds account remainder, never legacy fallback','Same transaction reserves payment, original context ledger and operation','After rollover original running match can pay and archived old wallet alone receives refund','Duplicate/concurrent requests and refunds happen once','Actual router, saved room restore and recovery worker reconcile recorded payer','V048 legacy and seasonal matches retain actual historical legacy payer; normal migration restart/checksum control passes'],
 UI_changed=False,UI_remaining='exploration_view.gd still hardcodes displayed refresh costs [60,180,450]; original preparation/catalog preview and comprehensive E01/E02 remain open.',
 formal_prices_or_workbook_changed=False,historical_rows_rewritten=False,production_deployed=False,production_restarted=False,new_full_routes=0,capacity100_retest=False,B05_total=291,C16_total=121,
 cloud_SDK_started=False,runtimes_removed=True,private_envs_removed=True,external_original_evidence_root=str(b),payloads_retained={stage:json.loads((b/stage/'manifest.json').read_text(encoding='utf-8'))['payload_sha256'] for stage in ['runtime-r101','runtime-r102','runtime-r103']},public_archives_retained={'runtime-r102':a102['public_archive_sha256'],'runtime-r103':a103['public_archive_sha256']})
(target/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
files={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file()}
(target/'manifest.json').write_text(json.dumps(dict(files=files,source_unchanged=True,large_original_binary_payloads_retained_on_G=True),indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(evidence_files=len(files)+1,PG_distinct=17,final_PG_passed=16,local_passed=7)))
