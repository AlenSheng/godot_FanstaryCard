from pathlib import Path
import json,hashlib,importlib.util,re,os,shutil,subprocess
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');work=b/'refresh-config-native-r1';assert not work.exists();work.mkdir()
tests=['test_reward_refresh_config.gd'];pending=['tests/'+n for n in tests];pins={}
while pending:
 n=pending.pop()
 if n in pins:continue
 p=repo/'client'/n;raw=p.read_bytes();pins[n]=hashlib.sha256(raw).hexdigest();q=work/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(raw)
 uid=Path(str(p)+'.uid')
 if uid.exists():shutil.copyfile(uid,Path(str(q)+'.uid'))
 if p.suffix=='.gd':pending+=re.findall(r'(?:preload|load)\(\s*"res://([^\"]+)"',raw.decode('utf-8-sig'))+re.findall(r'extends\s+"res://([^\"]+)"',raw.decode('utf-8-sig'))
for p in list((repo/'client/data').glob('*.json'))+list((repo/'client/data/locales').glob('*.json')):
 n=p.relative_to(repo/'client').as_posix();q=work/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);pins[n]=hashlib.sha256(p.read_bytes()).hexdigest()
source=b/'refresh-config-http-r1';cases=json.loads((source/'cases.json').read_text(encoding='utf-8'));assert len(cases)==4
fixture=work/'tests/refresh-config';fixture.mkdir()
for c in cases:
 for suffix,key in [('.envelope','envelope_sha256'),('.bundle','bundle_sha256')]:
  p=source/(c['name']+suffix);assert hashlib.sha256(p.read_bytes()).hexdigest()==c[key];shutil.copyfile(p,fixture/p.name)
shutil.copyfile(source/'cases.json',fixture/'cases.json')
(work/'project.godot').write_text('[application]\nconfig/name="Original refresh price interop"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
(work/'run.gd').write_text('''extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var result: Dictionary = load("res://tests/test_reward_refresh_config.gd").new().run_test()
    var file := FileAccess.open("res://native-result.json",FileAccess.WRITE)
    file.store_string(JSON.stringify(result));file.close()
    print(JSON.stringify(result))
    quit(0 if result.ok else 1)
''',encoding='utf-8')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
engine=Path(r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe');env=runtime.isolated_environment(work);records=[]
(work/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n',encoding='utf-8')
for label,extra in [('import',['--editor','--import','--quit']),('tests',['--script','res://run.gd'])]:
 r=runtime.guarded_run([str(engine),'--headless','--path',str(work),*extra],env=env,timeout=90);text=r.stdout+r.stderr;(work/(label+'.original.log')).write_text(text,encoding='utf-8');records.append(dict(stage=label,exit=r.returncode,engine_errors='ERROR:' in text));print(text[-5000:]);assert r.returncode==0 and 'ERROR:' not in text
result=json.loads((work/'native-result.json').read_text(encoding='utf-8'));assert result['ok'] and not any(v is False for v in result['checks'].values())
assert all(hashlib.sha256((repo/'client'/n).read_bytes()).hexdigest()==h for n,h in pins.items())
proof=dict(passed_checks=len(result['checks']),failed_checks=0,CSharp_cases=cases,source_unchanged=True,actual_game_matches=0,rendered_frames=False,runs=records)
(work/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(passed_checks=proof['passed_checks'],source_unchanged=True)))
for name in tests:
 p=repo/'client/tests'/name;uid=work/'tests'/(name+'.uid')
 if uid.exists() and not Path(str(p)+'.uid').exists():shutil.copyfile(uid,Path(str(p)+'.uid'))
