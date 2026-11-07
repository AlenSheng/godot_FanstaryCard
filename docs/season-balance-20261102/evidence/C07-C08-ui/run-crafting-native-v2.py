from pathlib import Path
import importlib.util,json,hashlib,sys
repo=Path.cwd();base=Path(__file__).parent;work=base/sys.argv[1]
assert work.name.startswith('crafting-native-r') and not work.exists();work.mkdir()
runner='''extends SceneTree
func _initialize() -> void:
    create_timer(30).timeout.connect(func(): print("Owned native watchdog reached; assertions incomplete"); quit(1))
    call_deferred("run")
func run() -> void:
    var game=get_root().get_node("Game")
    game.set_process(false)
    game.gateway.set_process(false)
    game.gateway.persist_session=false
    game.gateway.reconnect_enabled=false
    game.gateway.socket.close()
    var sound=get_root().get_node("Sound")
    sound.stop_all()
    sound.set_process(false)
    var results := {}
    var ok := true
    var total := 0
    for name in ["test_season_equipment.gd","test_season_enhancement.gd","test_season_crafting_protocol.gd","test_season_crafting_model.gd","test_season_crafting_controller.gd"]:
        print("START "+name)
        var row: Dictionary=await load("res://tests/"+name).new().run_test()
        results[name]=row
        ok=ok and row.ok
        total+=row.checks.size()
    FileAccess.open(OS.get_environment("FANTASYCARD_ART_EVIDENCE").path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"ok":ok,"checks":total,"suites":results},"  "))
    print(JSON.stringify({"ok":ok,"checks":total}))
    quit(0 if ok else 1)
'''
(work/'run.gd').write_text(runner,encoding='utf-8')
inputs={}
for folder in ['ui','data','network','tests']:
 for p in (repo/'client'/folder).rglob('*'):
  if p.is_file() and p.suffix in ['.gd','.json']:inputs[p.relative_to(repo).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
(work/'source-pin.json').write_text(json.dumps(inputs,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
env=runtime.isolated_environment(work,FANTASYCARD_SERVER_URL='http://127.0.0.1:9',FANTASYCARD_ART_EVIDENCE=str(work))
engine=Path('G:/Program Files/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe')
try:
 r=runtime.guarded_run([str(engine),'--headless','--path',str(repo/'client'),'--script',str(work/'run.gd')],env=env,timeout=90)
except Exception as error:
 def plain(value): return value.decode('utf-8',errors='replace') if isinstance(value,bytes) else value or ''
 output=plain(getattr(error,'stdout',''))+plain(getattr(error,'stderr',''))+plain(getattr(error,'output',''))
 (work/'native-timeout.original.log').write_text(output,encoding='utf-8')
 (work/'terminal.original.json').write_text(json.dumps({'stop_reason':type(error).__name__,'details':str(error),'acceptance_passed':False},indent=2)+'\n')
 print(output[-4000:]);raise
output=r.stdout+r.stderr;(work/'native.log').write_text(output,encoding='utf-8')
proof={'exit':r.returncode,'engine_errors':'ERROR:' in output,'headless':True,'rendered_frames':False,'source_unchanged':all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in inputs.items())}
(work/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
print(output[-3000:]);print(json.dumps(proof))
assert r.returncode==0 and 'ERROR:' not in output and proof['source_unchanged']

