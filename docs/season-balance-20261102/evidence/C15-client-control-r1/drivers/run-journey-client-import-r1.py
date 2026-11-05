from pathlib import Path
import hashlib,importlib.util,json,sys

repo=Path.cwd();base=Path(__file__).parent;stage=base/sys.argv[1];assert stage.name.startswith('journey-client-import-') and not stage.exists();stage.mkdir()
sources=list((repo/'client').rglob('*.gd'))+list((repo/'client').rglob('*.tscn'))+list((repo/'client/data').rglob('*.json'))+list((repo/'client/assets/imported/UI/SeasonJourney').glob('*.png'))+[repo/'client/project.godot',repo/'client/assets/imported/manifest.json']
pins={p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
(stage/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n',encoding='utf-8')
spec=importlib.util.spec_from_file_location('runtime',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
env=guard.isolated_environment(stage);command=[r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe','--headless','--audio-driver','Dummy','--path',str(repo/'client'),'--editor','--import','--quit']
try:result=guard.guarded_run(command,env=env,timeout=180,wait_seconds=0)
except Exception as error:
 (stage/'interrupted.original.json').write_text(json.dumps({'type':type(error).__name__,'message':str(error),'output':str(getattr(error,'output',''))},indent=2)+'\n',encoding='utf-8');raise
(stage/'stdout.original.log').write_text(result.stdout,encoding='utf-8');(stage/'stderr.original.log').write_text(result.stderr,encoding='utf-8')
unchanged=all(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest for name,digest in pins.items())
report={'returncode':result.returncode,'engine_errors':'ERROR:' in result.stdout+result.stderr,'input_sources_unchanged':unchanged,'rendered_frames':False}
(stage/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report));assert result.returncode==0 and not report['engine_errors'] and unchanged
