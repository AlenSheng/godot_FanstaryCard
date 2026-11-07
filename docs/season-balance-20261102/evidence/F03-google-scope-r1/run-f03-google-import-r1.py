from pathlib import Path
import json,importlib.util,os,hashlib
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');info=json.loads((b/'f03-google-integration-r1/source.original.json').read_bytes());work=Path(info['worktree']);out=b/'f03-google-import-r1';assert not out.exists();out.mkdir()
spec=importlib.util.spec_from_file_location('guard',Path.cwd()/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
env=guard.isolated_environment(out,FANTASYCARD_SERVER_URL='http://127.0.0.1:9')
engine=Path(r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe')
cmd=[str(engine),'--headless','--editor','--path',str(work/'client'),'--import','--rendering-method','gl_compatibility','--audio-driver','Dummy','--quit']
r=guard.guarded_run(cmd,env=env,timeout=300,wait_seconds=30);(out/'import.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');errors=[l for l in (r.stdout+r.stderr).splitlines() if 'ERROR:' in l]
proof={'exit':r.returncode,'errors':errors,'headless':True,'new_gameplay_cases':0,'source_candidate':info['detached_validation_commit']};(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print((r.stdout+r.stderr)[-4000:]);print(json.dumps({'exit':r.returncode,'errors':len(errors)}));assert r.returncode==0 and not errors
