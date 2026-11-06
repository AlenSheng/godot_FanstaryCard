from pathlib import Path
import importlib.util,os,json,hashlib
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');w=b/'red-interop-r1'
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
pins={p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for d in ['client/ui','client/data','client/network'] for p in (repo/d).rglob('*') if p.is_file() and p.suffix in ['.gd','.json']};(w/'client-source-pin.json').write_text(json.dumps(pins,indent=2)+'\n')
env=rt.isolated_environment(w,FANTASYCARD_SERVER_URL='http://127.0.0.1:9',FANTASYCARD_ART_EVIDENCE=str(w));engine=Path('G:/Program Files/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe')
cmd=[str(engine),'--headless','--path',str(repo/'client'),'--script',str(w/'run.gd')]
r=rt.guarded_run(cmd,env=env,timeout=90);text=r.stdout+r.stderr;(w/'godot.original.log').write_text(text,encoding='utf-8');print(text);assert r.returncode==0 and 'ERROR:' not in text
r=rt.guarded_run(['dotnet',str(w/'build/bin/Interop/debug/Interop.dll'),str(w),'decode'],env=dict(os.environ,DOTNET_NOLOGO='1'),timeout=90);(w/'server-decode.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
proof={'ok':True,'source_unchanged':all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items()),'actual_server_frames_decoded_by_Godot':3,'actual_Godot_command_decoded_by_server':1,'headless':True,'live_network':False};(w/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof));assert proof['source_unchanged']
