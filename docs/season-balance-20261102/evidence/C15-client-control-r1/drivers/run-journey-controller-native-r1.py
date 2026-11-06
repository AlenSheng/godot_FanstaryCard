from pathlib import Path
import importlib.util,re,json,hashlib,shutil,sys,subprocess
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();b=Path(__file__).parent;stage=sys.argv[1];assert re.fullmatch(r'journey-controller-native-r[1-9][0-9]*',stage);work=b/stage;assert not work.exists();work.mkdir();pending=['tests/test_journey_reward_controller.gd'];pins={}
while pending:
    name=pending.pop()
    if 'client/'+name in pins:continue
    source=repo/'client'/name;raw=source.read_bytes();pins['client/'+name]=hashlib.sha256(raw).hexdigest();target=work/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    if source.suffix=='.gd':pending+=re.findall(r'(?:preload|load)\(\s*"res://([^"]+)"',raw.decode('utf-8-sig'))+re.findall(r'extends\s+"res://([^"]+)"',raw.decode('utf-8-sig'))
for source in list((repo/'client/data').glob('*.json'))+list((repo/'client/data/locales').glob('*.json')):
    name=source.relative_to(repo/'client');target=work/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);pins['client/'+name.as_posix()]=hashlib.sha256(source.read_bytes()).hexdigest()
audit=json.loads((b/'runtime-r108/collection-audit.json').read_text('utf-8'));target=work/'tests/journey-reward-client';target.mkdir(parents=True)
for source in (b/'runtime-r108/public/results/journey-reward-client').iterdir():
    raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==audit['files']['results/journey-reward-client/'+source.name];(target/source.name).write_bytes(raw)
(work/'project.godot').write_text('[application]\nconfig/name="Journey controller isolated fixture"\n[autoload]\nGame="*res://state/game_store.gd"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
(work/'run.gd').write_text('''extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var script = load("res://tests/test_journey_reward_controller.gd")
    if script == null or not script.can_instantiate():
        quit(2)
        return
    var result: Dictionary = await script.new().run_test()
    var failures: Array[String] = []
    for key in result.get("checks", {}):
        if not result.checks[key]: failures.append(key)
    var output := {"ok": result.get("ok", false) and failures.is_empty(), "checks": result.get("checks", {}).size(), "failures": failures, "case": result}
    var file := FileAccess.open("res://case-results.json", FileAccess.WRITE)
    file.store_string(JSON.stringify(output))
    file.close()
    print(JSON.stringify(output))
    quit(0 if output.ok else 1)
''',encoding='utf-8')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard);env=guard.isolated_environment(work);engine=Path(r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe');runs=[]
for name,args in [('import',['--editor','--import','--quit']),('test',['--script','res://run.gd'])]:
    try:r=guard.guarded_run([str(engine),'--headless','--audio-driver','Dummy','--path',str(work),*args],env=env,timeout=90,wait_seconds=60)
    except Exception as error:
        (work/'interrupted.original.json').write_text(json.dumps(dict(stage=name,error=str(error),type=type(error).__name__,output=str(getattr(error,'output',''))),indent=2)+'\n',encoding='utf-8');raise
    text=r.stdout+r.stderr;(work/(name+'.original.log')).write_text(text,encoding='utf-8');runs.append(dict(stage=name,exit=r.returncode,engine_errors='ERROR:' in text));(work/'result.json').write_text(json.dumps(dict(inputs=pins,runs=runs,rendered_frames=False,actual_native_network=False),indent=2)+'\n',encoding='utf-8');print(text[-10000:],flush=True);assert r.returncode==0 and 'ERROR:' not in text
for source in (work/'ui').glob('*.gd.uid'):
    destination=repo/'client/ui'/source.name
    if not destination.exists():shutil.copyfile(source,destination)
source=work/'tests/test_journey_reward_controller.gd.uid';destination=repo/'client/tests/test_journey_reward_controller.gd.uid'
if source.exists() and not destination.exists():shutil.copyfile(source,destination)
assert all(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest for name,digest in pins.items())
