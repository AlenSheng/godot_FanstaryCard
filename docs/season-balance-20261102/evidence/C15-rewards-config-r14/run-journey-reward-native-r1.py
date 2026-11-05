from pathlib import Path
import importlib.util,hashlib,json,os,re,shutil,subprocess,sys
sys.stdout.reconfigure(encoding='utf-8')
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');stage=sys.argv[1];assert re.fullmatch(r'journey-reward-native-r[1-9][0-9]*',stage)
work=base/stage;assert not work.exists();work.mkdir();tests=['test_journey_reward_configuration.gd','test_reward_refresh_config.gd'];pending=['tests/'+n for n in tests];inputs={}
while pending:
    name=pending.pop()
    if 'client/'+name in inputs:continue
    source=repo/'client'/name;assert source.is_file(),name;raw=source.read_bytes();inputs['client/'+name]=hashlib.sha256(raw).hexdigest()
    target=work/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    if Path(str(source)+'.uid').exists():shutil.copyfile(Path(str(source)+'.uid'),Path(str(target)+'.uid'))
    if source.suffix=='.gd':pending+=re.findall(r'(?:preload|load)\(\s*"res://([^"]+)"',raw.decode('utf-8-sig'))+re.findall(r'extends\s+"res://([^"]+)"',raw.decode('utf-8-sig'))
for source in list((repo/'client/data').glob('*.json'))+list((repo/'client/data/locales').glob('*.json')):
    name=source.relative_to(repo/'client');target=work/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);inputs['client/'+name.as_posix()]=hashlib.sha256(source.read_bytes()).hexdigest()
source=base/'journey-reward-formal14-r2/refresh-http';cases=json.loads((source/'cases.json').read_text('utf-8'));target=work/'tests/refresh-config';target.mkdir(parents=True)
for entry in cases:
    for suffix,field in [('envelope','envelope_sha256'),('bundle','bundle_sha256')]:
        name=entry['name']+'.'+suffix;raw=(source/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==entry[field];(target/name).write_bytes(raw);inputs['CSharp/refresh-config/'+name]=entry[field]
shutil.copyfile(source/'cases.json',target/'cases.json');inputs['CSharp/refresh-config/cases.json']=hashlib.sha256((target/'cases.json').read_bytes()).hexdigest()
target=work/'tests/journey-rewards';target.mkdir()
for file,name in [('fantasycard.config.bytes','archive13.bundle'),('fantasycard.config.sha256','archive13.sha256')]:
    source=repo/'server/config/archive/season-v1-config-13'/file;shutil.copyfile(source,target/name);inputs['original13/'+name]=hashlib.sha256(source.read_bytes()).hexdigest()
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
(work/'run.gd').write_text(runner,encoding='utf-8');(work/'project.godot').write_text('[application]\nconfig/name="Journey reward native configuration"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
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
