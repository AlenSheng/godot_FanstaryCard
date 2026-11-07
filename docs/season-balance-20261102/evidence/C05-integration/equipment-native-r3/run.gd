extends SceneTree
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
