from pathlib import Path
import gzip,hashlib,importlib.util,json,subprocess

repo=Path.cwd();base=Path(__file__).parent;target=repo/'docs/season-balance-20261102/evidence/A03-mail-build-progress-r1';assert not target.exists();target.mkdir()
spec=importlib.util.spec_from_file_location('public',repo/'tools/pr13_public_evidence.py');public=importlib.util.module_from_spec(spec);spec.loader.exec_module(public)
originals={}
for name in ['mail-permanent-local-r3','mail-permanent-local-r4','mail-permanent-local-r5']:
 for p in sorted((base/name).glob('*')):
  if not p.is_file() or p.suffix not in ('.json','.log'):continue
  raw=p.read_bytes();public.inspect_public_bytes(p,raw);dest=target/name/(p.name+'.gz' if len(raw)>150000 else p.name);dest.parent.mkdir(exist_ok=True)
  dest.write_bytes(gzip.compress(raw,mtime=0) if len(raw)>150000 else raw);originals[f'{name}/{p.name}']={'sha256':hashlib.sha256(raw).hexdigest(),'stored':dest.relative_to(target).as_posix(),'gzip':len(raw)>150000}
drivers=['run-mail-permanent-local-r3.py','run-mail-permanent-local-r4.py','prepare-mail-local-incremental-r5.py','run-mail-permanent-local-r5.py','inspect-runtime-staging-space-r109.py','package-mail-build-progress-r1.py']
for name in drivers:
 p=target/'drivers'/name;p.parent.mkdir(exist_ok=True);p.write_bytes((base/name).read_bytes())
source='server/tests/FantasyCard.Server.Tests/Persistence/PostgresMailPermanentCopyTests.cs'
pin=json.loads((base/'mail-permanent-local-r3/source-pin.json').read_text('utf-8'))
blob=subprocess.check_output(['git','show','HEAD:'+source]);choices=[blob,blob.replace(b'\r\n',b'\n'),blob.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')]
original=next(data for data in choices if hashlib.sha256(data).hexdigest()==pin[source])
(target/'failed-r3-test-source.original.cs').write_bytes(original)
(target/'corrected-test-source.cs').write_bytes((repo/source).read_bytes())
dependencies={}
for name in ['FantasyCard.Contracts','FantasyCard.Domain','FantasyCard.Server','FantasyCard.ConfigExporter']:
 p=base/'mail-permanent-local-r3/build/bin'/name/'debug'/(name+'.dll');dependencies[name]=hashlib.sha256(p.read_bytes()).hexdigest()
correction={'file':'mail-permanent-local-r5/unchanged-dependency-reuse.json','prebuild_field_named_all_test_source_compiled_was_a_plan_not_a_result':True,'actual_test_compilation_started':False,'actual_status':'resource admission rejected before dotnet start','future_field_name':'all_test_source_selected_for_compilation','original_prebuild_record_retained':True}
(target/'prebuild-wording-correction.json').write_text(json.dumps(correction,indent=2)+'\n',encoding='utf-8')
result={'status':'production_components_compiled_test_fixture_type_error_corrected_full_test_build_and_PG_pending','r3_compiled_dependency_DLLs':dependencies,'r3_test_assembly_compile_errors':10,'error_code':'CS8752','error_cause':'target-typed new() in single params argument inferred the array type','fix':'explicit MailAttachmentResponse constructors','r4_stopped_by_continuous_6GiB_memory_guard':True,'r5_admission_rejected_before_process_start':True,'test_cases_executed':0,'new_repository_PG_passed':0,'test_cases_written':10,'production_changed_since_r3':False,'only_test_source_changed_since_r3':source,'overall_completed_items':20,'C15_complete':False,'new_full_routes':0,'new_balance_encounters':0,'capacity100_retest':False,'production_restarted':False,'full_original_directory':str(base)}
(target/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
(target/'raw-manifest.json').write_text(json.dumps(originals,indent=2)+'\n',encoding='utf-8')
files={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}
(target/'manifest.json').write_text(json.dumps({'files':files},indent=2)+'\n',encoding='utf-8');print(json.dumps({'files':len(files),'production_components_compiled':4,'test_assembly_complete':False,'tests_executed':0}))
