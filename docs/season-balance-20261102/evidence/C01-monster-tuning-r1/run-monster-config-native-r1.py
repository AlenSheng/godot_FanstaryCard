from pathlib import Path
import json,hashlib,importlib.util,os,re,shutil,sys

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;work=base/'monster-config-native-r1';assert not work.exists();work.mkdir()
pending=['tests/test_monster_tuning_configuration.gd'];pins={}
while pending:
 name=pending.pop()
 if name in pins:continue
 source=repo/'client'/name;raw=source.read_bytes();target=work/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);pins[name]=hashlib.sha256(raw).hexdigest()
 uid=Path(str(source)+'.uid')
 if uid.exists():shutil.copyfile(uid,Path(str(target)+'.uid'))
 if source.suffix=='.gd':pending+=re.findall(r'(?:preload|load)\(\s*"res://([^\"]+)"',raw.decode('utf-8-sig'))+re.findall(r'extends\s+"res://([^\"]+)"',raw.decode('utf-8-sig'))
for source in list((repo/'client/data').glob('*.json'))+list((repo/'client/data/locales').glob('*.json')):
 name=source.relative_to(repo/'client').as_posix();target=work/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);pins[name]=hashlib.sha256(source.read_bytes()).hexdigest()
wire=base/'monster-config-wire-r1/data';cases=json.loads((wire/'cases.json').read_bytes());fixture=work/'tests/monster-config';fixture.mkdir()
for case in cases:
 for suffix,key in [('.bundle','bundle_sha256'),('.envelope','envelope_sha256')]:
  source=wire/(case['name']+suffix);assert hashlib.sha256(source.read_bytes()).hexdigest()==case[key];shutil.copyfile(source,fixture/source.name)
shutil.copyfile(wire/'cases.json',fixture/'cases.json')
(work/'project.godot').write_text('[application]\nconfig/name="Monster configuration transport"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
(work/'run.gd').write_text('''extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var result: Dictionary = load("res://tests/test_monster_tuning_configuration.gd").new().run_test()
    var file := FileAccess.open("res://native-result.json",FileAccess.WRITE)
    file.store_string(JSON.stringify(result));file.close()
    print(JSON.stringify(result))
    quit(0 if result.ok else 1)
''',encoding='utf-8')
spec=importlib.util.spec_from_file_location('runtime',repo/'client/tests/fixture_runtime.py');runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime);env=runtime.isolated_environment(work)
for f in work.rglob('*'):
 if f.is_file() and (repo/'client'/f.relative_to(work)).is_file():pins[f.relative_to(work).as_posix()]=hashlib.sha256(f.read_bytes()).hexdigest()
(work/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n');engine=Path(r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe');stages=[]
for label,args in [('import',['--editor','--import','--quit']),('tests',['--script','res://run.gd'])]:
 r=runtime.guarded_run([str(engine),'--headless','--path',str(work),*args],env=env,timeout=90,wait_seconds=180);text=r.stdout+r.stderr;(work/(label+'.original.log')).write_text(text,encoding='utf-8');print(text[-3200:]);stages.append({'stage':label,'exit':r.returncode,'engine_errors':'ERROR:' in text});assert r.returncode==0 and 'ERROR:' not in text
result=json.loads((work/'native-result.json').read_bytes());assert result['ok'] and all(result['checks'].values());assert all(hashlib.sha256((repo/'client'/n).read_bytes()).hexdigest()==h for n,h in pins.items())
(work/'result.json').write_text(json.dumps({'passed_checks':len(result['checks']),'failed':0,'actual_CSharp_versions':[c['version'] for c in cases],'source_unchanged':True,'runs':stages,'headless_hidden_BelowNormal':True,'rendered_frames':0,'HTTP_network_claimed':False,'C16_encounters':0,'B05_encounters':0},indent=2)+'\n')
uid=work/'tests/test_monster_tuning_configuration.gd.uid';target=repo/'client/tests/test_monster_tuning_configuration.gd.uid'
if uid.exists() and not target.exists():shutil.copyfile(uid,target)
print('Native configuration transport checks:',len(result['checks']))
