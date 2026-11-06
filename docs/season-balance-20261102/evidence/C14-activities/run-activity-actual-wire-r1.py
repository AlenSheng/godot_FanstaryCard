from pathlib import Path
import importlib.util,json,hashlib,os,shutil
repo=Path.cwd();base=Path(__file__).parent;out=base/'activity-actual-wire-r1';assert not out.exists();out.mkdir();source=base/'storage-r86/public/activity-wire'
for p in source.glob('*.bin'):shutil.copyfile(p,out/p.name)
script=(base/'activity-wire.gd').read_text(encoding='utf-8')
(out/'run.gd').write_text(script,encoding='utf-8')
pins={p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for root in ['client/data','client/network','client/ui','client/tests'] for p in (repo/root).rglob('*') if p.is_file() and p.suffix in ['.gd','.json']};(out/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
env=rt.isolated_environment(out,FANTASYCARD_SERVER_URL='http://127.0.0.1:9',FANTASYCARD_ART_EVIDENCE=str(out))
engine=Path('G:/Program Files/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe')
r=rt.guarded_run([str(engine),'--headless','--path',str(repo/'client'),'--script',str(out/'run.gd')],env=env,timeout=90);text=r.stdout+r.stderr;(out/'native.original.log').write_text(text,encoding='utf-8');print(text)
proof={'exit':r.returncode,'engine_errors':'ERROR:' in text,'actual_network_wire_files':4,'source_unchanged':all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items()),'headless':True,'Godot_direct_live_connection':False};(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof));assert r.returncode==0 and 'ERROR:' not in text and proof['source_unchanged']
