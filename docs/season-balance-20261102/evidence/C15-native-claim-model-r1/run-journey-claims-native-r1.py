from pathlib import Path
import importlib.util,hashlib,json,os,re,shutil,subprocess,sys
sys.stdout.reconfigure(encoding='utf-8')
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');stage=sys.argv[1];assert re.fullmatch(r'journey-claims-native-r[1-9][0-9]*',stage)
work=base/stage;assert not work.exists();work.mkdir();tests=['test_journey_reward_claims.gd'];pending=['tests/'+n for n in tests];inputs={}
while pending:
    name=pending.pop()
    if 'client/'+name in inputs:continue
    source=repo/'client'/name;assert source.is_file(),name;raw=source.read_bytes();inputs['client/'+name]=hashlib.sha256(raw).hexdigest()
    target=work/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    if Path(str(source)+'.uid').exists():shutil.copyfile(Path(str(source)+'.uid'),Path(str(target)+'.uid'))
    if source.suffix=='.gd':pending+=re.findall(r'(?:preload|load)\(\s*"res://([^"]+)"',raw.decode('utf-8-sig'))+re.findall(r'extends\s+"res://([^"]+)"',raw.decode('utf-8-sig'))
for source in list((repo/'client/data').glob('*.json'))+list((repo/'client/data/locales').glob('*.json')):
    name=source.relative_to(repo/'client');target=work/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);inputs['client/'+name.as_posix()]=hashlib.sha256(source.read_bytes()).hexdigest()
source=base/'runtime-r108/public/results/journey-reward-client';audit=json.loads((base/'runtime-r108/collection-audit.json').read_text('utf-8'));target=work/'tests/journey-reward-client';target.mkdir(parents=True)
for source_file in source.iterdir():
    name='results/journey-reward-client/'+source_file.name;raw=source_file.read_bytes();assert hashlib.sha256(raw).hexdigest()==audit['files'][name];(target/source_file.name).write_bytes(raw);inputs['actual_HTTP/'+source_file.name]=hashlib.sha256(raw).hexdigest()
runner='''extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var cases := {}
    var failures: Array[String] = []
    var count := 0
    for name in CASES:
        var script = load("res://tests/" + name)
        if script == null or not script.can_instantiate():
            failures.append(name + ":parse")
            continue
        var result: Dictionary = script.new().run_test()
        cases[name] = result
        for key in result.get("checks", {}):
            count += 1
            if not result.checks[key]: failures.append(name + ":" + key)
        if not result.get("ok", false): failures.append(name + ":suite")
    var result := {"ok": failures.is_empty(), "checks": count, "failures": failures, "cases": cases}
    var output := FileAccess.open("res://case-results.json", FileAccess.WRITE)
    output.store_string(JSON.stringify(result))
    output.close()
    print(JSON.stringify(result))
    quit(0 if failures.is_empty() else 1)
'''.replace('CASES',json.dumps(tests))
(work/'run.gd').write_text(runner,encoding='utf-8');(work/'project.godot').write_text('[application]\nconfig/name="Journey claim actual HTTP bytes"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime);env=runtime.isolated_environment(work);engine=Path(r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe');runs=[]
for label,args in [('import',['--editor','--import','--quit']),('tests',['--script','res://run.gd'])]:
    try:r=runtime.guarded_run([str(engine),'--headless','--audio-driver','Dummy','--path',str(work),*args],env=env,timeout=90)
    except Exception as error:
        (work/'interrupted.original.json').write_text(json.dumps(dict(stage=label,error_type=type(error).__name__,error=str(error),output=str(getattr(error,'output',''))),indent=2)+'\n',encoding='utf-8');raise
    text=r.stdout+r.stderr;(work/(label+'.original.log')).write_text(text,encoding='utf-8');runs.append(dict(stage=label,exit=r.returncode,engine_errors='ERROR:' in text));(work/'result.json').write_text(json.dumps(dict(inputs=inputs,runs=runs,engine_sha256=hashlib.sha256(engine.read_bytes()).hexdigest(),rendered_frames=False,database_used=False,actual_http_network=False,new_full_routes=0,new_encounters=0),indent=2)+'\n',encoding='utf-8');print(text[-6500:],flush=True);assert r.returncode==0 and 'ERROR:' not in text
for name in tests:
    source=work/'tests'/(name+'.uid');target=repo/'client/tests'/(name+'.uid')
    if source.exists() and not target.exists():shutil.copyfile(source,target)
print('sources_unchanged',all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in inputs.items() if n.startswith('client/')))
