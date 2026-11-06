import hashlib,importlib.util,json,sys
from pathlib import Path
repo=Path.cwd();base=Path(__file__).parent;work=base/sys.argv[1]
assert work.name.startswith('equipment-native-r') and not work.exists();work.mkdir()
runner='''extends SceneTree
func _initialize() -> void:
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
    var result: Dictionary=await load("res://tests/test_season_equipment.gd").new().run_test()
    var checks: Dictionary=result.checks
    var art=load("res://ui/art.gd")
    for slot in ["head","chest","hands","legs","feet"]:
        for element in ["fire","wood","earth","metal","water"]:
            var key="Equipment/Red/"+slot+"_"+element+".png"
            var texture=art.texture(key)
            checks[key+" resolves actual red atlas"]=texture is AtlasTexture and texture.get_width()>0 and texture.get_height()>0
    var http=load("res://network/http_protocol.gd")
    var proto_http=load("res://network/protobuf.gd").new(true)
    var sample={"instanceId":"11111111-1111-1111-1111-111111111111","slot":"Head","quality":"Red","level":5,"element":"Fire","effectAffix":"Piercing","secondaryTrait":"DrawInterval","uniqueAffix":"Inferno","uniqueElement":"Fire","statsVersion":"season-equipment-v1"}
    for message in ["EquipmentResponse","PreparationEquipmentSnapshotResponse"]:
        var wire=http.to_wire(message,sample)
        var encoded=proto_http.encode(message,wire)
        var decoded=proto_http.decode(message,encoded)
        var actual=http.from_wire(message,decoded)
        checks[message+" native appended fields roundtrip"]=proto_http.error.is_empty() and actual.uniqueAffix=="Inferno" and actual.uniqueElement=="Fire" and actual.statsVersion=="season-equipment-v1"
    var proto=load("res://network/protobuf.gd").new()
    var wire={"slot":"Head","quality":"Red","element":"Fire","effect_affix":"Piercing","secondary_trait":"DrawInterval","level":5,"unique_affix":"Inferno","unique_element":"Fire","stats_version":"season-equipment-v1"}
    var decoded=proto.decode("RoomEquipment",proto.encode("RoomEquipment",wire))
    checks["RoomEquipment native appended fields roundtrip"]=proto.error.is_empty() and decoded.unique_affix=="Inferno" and decoded.unique_element=="Fire" and decoded.stats_version=="season-equipment-v1"
    var legacy={"slot":"Head","quality":"Red","element":"Fire","level":0,"effectAffix":"Piercing","secondaryTrait":"DrawInterval","uniqueAffix":"Inferno","uniqueElement":"Water"}
    var values=load("res://ui/equipment_compare_model.gd").aggregate_attributes([legacy])
    checks["legacy different-element Inferno preserved"]=is_equal_approx(float(values.damage_Fire),.32) and is_equal_approx(float(values.damage_Water),.35)
    result.ok=not checks.values().has(false)
    result["check_count"]=checks.size()
    result["extra_scope"]="25 real red atlas resources and appended native HTTP/WSS roundtrip; not a live network interoperability or quota claim."
    FileAccess.open(OS.get_environment("FANTASYCARD_ART_EVIDENCE").path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify(result,"  "))
    print(JSON.stringify({"ok":result.ok,"checks":checks.size()}))
    quit(0 if result.ok else 1)
'''
(work/'run.gd').write_text(runner,encoding='utf-8')
inputs={}
for folder in ['ui','data','network']:
    for p in (repo/'client'/folder).rglob('*'):
        if p.is_file() and p.suffix in ['.gd','.json','.bytes']:inputs[str(p.relative_to(repo)).replace('\\','/')]=hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['client/tests/test_season_equipment.gd','client/assets/imported/manifest.json','client/assets/generated/equipment/red-atlas-v1.png']:
    inputs[name]=hashlib.sha256((repo/name).read_bytes()).hexdigest()
(work/'source-pin.json').write_text(json.dumps(inputs,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
env=runtime.isolated_environment(work,FANTASYCARD_SERVER_URL='http://127.0.0.1:9',FANTASYCARD_ART_EVIDENCE=str(work))
engine=Path('G:/Program Files/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64.exe')
r=runtime.guarded_run([str(engine),'--headless','--path',str(repo/'client'),'--script',str(work/'run.gd')],env=env,timeout=90)
output=r.stdout+r.stderr;(work/'tests.log').write_text(output,encoding='utf-8')
unchanged=all(hashlib.sha256((repo/name).read_bytes()).hexdigest()==h for name,h in inputs.items())
proof={'exit':r.returncode,'engine_errors':'ERROR:' in output,'headless':True,'rendered_frames':False,'source_unchanged':unchanged,'engine_sha256':hashlib.sha256(engine.read_bytes()).hexdigest()}
(work/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
print(output[-2500:],flush=True);print(json.dumps(proof))
assert r.returncode==0 and 'ERROR:' not in output and unchanged

