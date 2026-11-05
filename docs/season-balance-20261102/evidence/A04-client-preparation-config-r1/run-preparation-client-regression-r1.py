import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

repo=Path.cwd();base=Path(__file__).parent;stage=sys.argv[1]
assert re.fullmatch(r'preparation-client-regression-r[1-9][0-9]*',stage)
work=base/stage;assert not work.exists();work.mkdir()
archive=base/'storage-r32/public-evidence.tar.gz'
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='4b85df8b3508964076b4f001bf63107d499ea49960843b23eedfb4fd877c99a8'
tests=['test_season_borrowed_decks.gd','test_config_archives.gd','test_class_selection_lobby_epoch.gd']
pending=['tests/'+name for name in tests];inputs={}
while pending:
    name=pending.pop()
    if 'client/'+name in inputs:continue
    source=repo/'client'/name;assert source.is_file(),name
    raw=source.read_bytes();inputs['client/'+name]=hashlib.sha256(raw).hexdigest()
    target=work/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    if Path(str(source)+'.uid').exists():shutil.copy2(Path(str(source)+'.uid'),Path(str(target)+'.uid'))
    if source.suffix=='.gd':
        text=raw.decode('utf-8-sig');pending+=re.findall(r'(?:preload|load)\(\s*"res://([^"]+)"',text)+re.findall(r'extends\s+"res://([^"]+)"',text)
# Palette loads these registered locale resources dynamically, outside preload().
for source in list((repo/'client/data').glob('*.json'))+list((repo/'client/data/locales').glob('*.json')):
    name=source.relative_to(repo/'client');target=work/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    inputs['client/'+name.as_posix()]=hashlib.sha256(source.read_bytes()).hexdigest()
fixture=work/'tests/config-client';fixture.mkdir()
with tarfile.open(archive) as bundle:
    audit=json.load(bundle.extractfile('audit.json'))
    for name in ['old.bundle','next.bundle','old.envelope','next.envelope','cases.json']:
        raw=bundle.extractfile('config-client/'+name).read();assert hashlib.sha256(raw).hexdigest()==audit['files']['config-client/'+name]
        (fixture/name).write_bytes(raw);inputs['CSharp/config-client/'+name]=hashlib.sha256(raw).hexdigest()
config=json.loads((repo/'client/data/localization_config.json').read_text(encoding='utf-8'))
registry=json.loads((repo/'client/data/localization_registry.json').read_text(encoding='utf-8'))
languages=list(dict.fromkeys([*config['languages'],*registry['languages']]))
(fixture/'languages.json').write_text(json.dumps(languages))
runner='''extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var results := {}
    var failures: Array[String] = []
    var total := 0
    for name in CASES:
        print("CASE_START "+name)
        var script = load("res://tests/" + name)
        if script == null or not script.can_instantiate():
            failures.append(name+":parse")
            continue
        var instance = script.new()
        if not instance.has_method("run_test"):
            failures.append(name+":entrypoint")
            continue
        var result: Dictionary = await instance.run_test()
        print("CASE_DONE "+name)
        results[name] = result
        var file := FileAccess.open("res://case-results.json",FileAccess.WRITE)
        file.store_string(JSON.stringify(results))
        file.close()
        var checks: Dictionary = result.get("checks", result)
        for label in checks:
            if checks[label] is bool:
                total += 1
                if not checks[label]: failures.append(name+":"+str(label))
        if result.has("ok") and not result.ok: failures.append(name+":suite")
    print(JSON.stringify({"ok":failures.is_empty(),"checks":total,"failures":failures,"cases":results}))
    quit(0 if failures.is_empty() else 1)
'''.replace('CASES',json.dumps(tests))
(work/'run.gd').write_text(runner)
(work/'project.godot').write_text('[application]\nconfig/name="Config client native"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
engine=Path('G:/Program Files/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe');env=runtime.isolated_environment(work);records=[]
for label,args in [('import',['--editor','--import','--quit']),('tests',['--script','res://run.gd'])]:
    try:
        result=runtime.guarded_run([str(engine),'--headless','--path',str(work),*args],env=env,timeout=90)
    except subprocess.TimeoutExpired as failure:
        output=(failure.output or '')+(failure.stderr or '')
        (work/(label+'.log')).write_text(output,encoding='utf-8')
        records.append({'label':label,'timeout_seconds':90,'engine_errors':'ERROR:' in output})
        (work/'result.json').write_text(json.dumps({'inputs':inputs,'runs':records,'languages':languages,'rendered_frames':False},indent=2)+'\n')
        print(output[-7000:],flush=True)
        raise
    output=result.stdout+result.stderr;(work/(label+'.log')).write_text(output,encoding='utf-8')
    records.append({'label':label,'exit':result.returncode,'engine_errors':'ERROR:' in output})
    (work/'result.json').write_text(json.dumps({'inputs':inputs,'runs':records,'engine_sha256':hashlib.sha256(engine.read_bytes()).hexdigest(),'languages':languages,'rendered_frames':False},indent=2)+'\n')
    print(output[-6000:],flush=True)
    assert result.returncode==0 and 'ERROR:' not in output
for name in ['data/config_bundle.gd','tests/test_config_archives.gd']:
    generated=Path(str(work/name)+'.uid');destination=Path(str(repo/'client'/name)+'.uid')
    if generated.exists() and not destination.exists():shutil.copy2(generated,destination)
