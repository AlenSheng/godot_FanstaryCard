from pathlib import Path
import hashlib,importlib.util,json,shutil

repo=Path.cwd();base=Path(__file__).parent;target=repo/'docs/season-balance-20261102/evidence/C15-native17-admin-sql-r1';assert not target.exists();target.mkdir()
spec=importlib.util.spec_from_file_location('public',repo/'tools/pr13_public_evidence.py');public=importlib.util.module_from_spec(spec);spec.loader.exec_module(public)
sources=['journey-native-cloud-r4','admin-card-ledger-sql-r1','mail-permanent-local-r2']
for name in sources:
 for p in sorted((base/name).rglob('*')):
  if not p.is_file() or any(part in ('server','client','config','protocol','build') for part in p.relative_to(base/name).parts):continue
  if p.suffix not in ('.json','.log','.py','.sql','.gz'):continue
  relative=Path(name)/p.relative_to(base/name);raw=p.read_bytes();public.inspect_public_bytes(p,raw)
  destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
for name in ['reproduce-admin-card-ledger-sql-r1.py','prepare-journey-native-cloud-r4.py','upload-journey-native-cloud-r4.py','resume-journey-native-cloud-r4-upload-r1.py','start-journey-native-cloud-r4-preupload-gate.original.py','start-journey-native-cloud-r4.py','run-mail-permanent-local-r2.py','package-native17-and-admin-sql-r1.py']:
 destination=target/'drivers'/name;destination.parent.mkdir(exist_ok=True);destination.write_bytes((base/name).read_bytes())
native=base/'journey-native-cloud-r4/public';case=json.loads((native/'case-results.json').read_text('utf-8'));state=json.loads((native/'terminal.original.json').read_text('utf-8'));cleanup=json.loads((native/'cleanup.original.json').read_text('utf-8'))
assert case['ok'] and case['checks']==17 and not case['failures'] and state['state']['ExitCode']==0 and not state['state']['OOMKilled'] and state['guard_failure'] is None and cleanup['container_removed'] and cleanup['all_original_input_bytes_unchanged']
sql=json.loads((base/'admin-card-ledger-sql-r1/validation.json').read_text('utf-8'));assert sql['discrepancies']==[0,1,0,0]
result={'status':'current_native17_and_UI_compilation_verified_admin_SQL_counterexample_proved_full_UI_and_CSharp_PG_pending','native_controller_passed':17,'native_controller_failed':0,'engine':'Linux Godot4.7.2.stable.official.ed1daf0bf','UI_compile_targets':5,'native_actual_network':False,'rendered_frames':0,'source_files_verified':143,'old_input_extras_verified':10,'old_input_unchanged':True,'container_removed':True,'temporary_SQL_discrepancies':[0,1,0,0],'SQL_scope':'actual mutation/ledger/reconciliation SQL on isolated temporary fixture tables; not repository/HTTP integration','SQL_rolled_back':True,'mail_PG_cases_written':8,'admin_PG_cases_written':2,'new_CSharp_build_started':False,'new_CSharp_PG_passed':0,'local_build_r2_admission_rejected':True,'original_upload_template_failure_retained':True,'C15_complete':False,'overall_completed_items':20,'new_full_routes':0,'new_balance_encounters':0,'capacity100_retest':False,'production_restarted':False}
(target/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
files={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}
(target/'manifest.json').write_text(json.dumps({'files':files,'full_original_directory':str(base)},indent=2)+'\n',encoding='utf-8');print(json.dumps({'files':len(files),'native17':True,'SQL_counterexample':True,'repository_PG_passed':0}))
