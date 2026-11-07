from pathlib import Path
import json,hashlib,re,shutil,importlib.util,sys
repo=Path.cwd();base=Path(__file__).parent;out=base/'config17-godot-r2';assert not out.exists();out.mkdir()
pending=['tests/test_mage_return_budget.gd','tests/test_combat_preview_state.gd','tests/test_protobuf.gd'];inputs={}
while pending:
 name=pending.pop()
 if name in inputs:continue
 source=repo/'client'/name;assert source.is_file(),name
 raw=source.read_bytes();inputs[name]=hashlib.sha256(raw).hexdigest();target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
 if source.suffix=='.gd':pending+=re.findall(r'(?:preload|load)\(\s*"res://([^"]+)"',raw.decode('utf-8-sig'))+re.findall(r'extends\s+"res://([^"]+)"',raw.decode('utf-8-sig'))
for p in list((repo/'client/data').glob('*.json'))+list((repo/'client/data/locales').glob('*.json')):
 n=p.relative_to(repo/'client');q=out/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);inputs[n.as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
target=out/'tests/sustain';target.mkdir()
for p in (base/'config17-native-r2/wire').glob('*.json'):shutil.copyfile(p,target/p.name)
shutil.copyfile(repo/'server/config/archive/season-v1-config-16/fantasycard.config.bytes',target/'original16.bytes')
(out/'run.gd').write_text('''extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var results := {}
    var ok := true
    for name in ["test_mage_return_budget.gd", "test_combat_preview_state.gd", "test_protobuf.gd"]:
        var result: Dictionary = load("res://tests/" + name).new().run_test()
        results[name] = result
        ok = ok and result.get("ok", false)
    FileAccess.open("res://cases.original.json", FileAccess.WRITE).store_string(JSON.stringify(results, "  "))
    print(JSON.stringify(results))
    quit(0 if ok else 1)
''')
(out/'project.godot').write_text('[application]\nconfig/name="Config17 native protocol"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
env=guard.isolated_environment(out);engine=Path('G:/Program Files/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe');records=[]
for label,args in [('import',['--editor','--import','--quit']),('tests',['--script','res://run.gd'])]:
 try:r=guard.guarded_run([str(engine),'--headless','--path',str(out),*args],env=env,timeout=90,wait_seconds=30)
 except Exception as e:
  (out/(label+'.interrupted.original.log')).write_text(str(e)+'\n'+str(getattr(e,'output','')));raise
 text=r.stdout+r.stderr;(out/(label+'.original.log')).write_text(text,encoding='utf-8');records.append(dict(stage=label,exit=r.returncode,errors='ERROR:' in text));print(text[-5500:])
 (out/'result.json').write_text(json.dumps(dict(inputs=inputs,runs=records,new_game_matches=0),indent=2)+'\n');assert r.returncode==0 and 'ERROR:' not in text
print('Config17 Godot targeted checks passed.')
