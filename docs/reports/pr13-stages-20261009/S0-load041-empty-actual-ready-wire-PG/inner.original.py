import hashlib,json,os,subprocess
from pathlib import Path
W=Path('/work');O=Path('/output');P=json.loads((W/'plan.original.json').read_bytes())
runtime=Path('/runtime');dll=runtime/'FantasyCard.Server.dll'
assert hashlib.sha256(dll.read_bytes()).hexdigest()==P['actual_server_assembly_sha256']
env=dict(os.environ,FANTASYCARD_READY_STOP_SERVER_DLL=str(dll),FANTASYCARD_READY_STOP_SERVER_DLL_SHA256=P['actual_server_assembly_sha256'])
command=['python3','/source/client/tests/run_ready_stop_faults.py','--work-dir','/output/native','--godot','/usr/local/bin/godot','--database-container',P['PG_owner'],'--case','normal_ready']
with (O/'actual-native.stdout.original.log').open('xb') as out,(O/'actual-native.stderr.original.log').open('xb') as err:
 result=subprocess.run(command,cwd='/source',env=env,stdout=out,stderr=err,timeout=360)
report=json.loads((O/'native/report.json').read_bytes()) if (O/'native/report.json').exists() else {}
ok=result.returncode==0 and report.get('ok') and report.get('case_count')==report.get('passed_case_count')==1 and report.get('owned_fixture_databases_removed') and report.get('owned_server_stopped')
proof={'ok':bool(ok),'actual_native_job_exit_code':result.returncode,'actual_native_rows':report.get('case_count'), 'actual_passed_rows':report.get('passed_case_count'),'declared_control_only':'Original ready serialization/send, observation-only copy captures exact socket buffer and decodes it; no payload/field changes', 'actual_fixture_source_projection_sha':report.get('source_sha'),'current_release_source_sha':P['source_base_sha'],'compiled_source_sha':P['compiled_source_sha'],'production_source_not_edited':True,'MAIN_accepted':False}
(O/'empty-ready-wire-result.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode());print(json.dumps(proof));assert ok
