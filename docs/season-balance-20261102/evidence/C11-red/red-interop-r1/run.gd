extends SceneTree
const Proto=preload("res://network/protobuf.gd")
func _initialize() -> void:
    create_timer(30).timeout.connect(func(): quit(1))
    call_deferred("run")
func run() -> void:
    var game=get_root().get_node("Game")
    game.set_process(false);game.gateway.set_process(false);game.gateway.persist_session=false;game.gateway.reconnect_enabled=false;game.gateway.socket.close()
    var sound=get_root().get_node("Sound");sound.persist_settings=false;sound.stop_all();sound.set_process(false)
    var output := OS.get_environment("FANTASYCARD_ART_EVIDENCE")
    var checks := {}
    var proto := Proto.new()
    for name in ["pending","evaluating","legacy"]:
        var envelope: Dictionary=proto.decode("ServerEnvelope",FileAccess.get_file_as_bytes(output.path_join(name+".bin")))
        checks[name+" actual server envelope"]=proto.error.is_empty() and envelope.type=="room.snapshot" and envelope.sequence==1
        var body: Dictionary=proto.decode("RoomSnapshotEvent",envelope.payload)
        checks[name+" source context and legal70 sentinel"]=proto.error.is_empty() and body.season.season_id=="original-season" and body.player.combat.hp==70 and body.room_revision==9
        checks[name+" red evaluation flag"]=bool(body.player.red_evaluation_pending)==(name=="evaluating")
        if name=="pending":
            checks["actual server reserved item"]=body.player.pending_red_item.item_id=="00000000-0000-0000-0000-000000000001" and body.player.pending_red_item.equipment.unique_affix=="Inferno" and body.player.pending_red_item.equipment.stats_version=="season-equipment-v1" and body.player.pending_red_item.equipment.level==0
            checks["actual server actions"]=body.allowed_actions==["choice.read","choice.pick"]
        else: checks[name+" no invented pending item"]=body.player.get("pending_red_item")==null
    var payload: PackedByteArray=proto.encode("RewardChoiceClaimCommand",{"option_id":"red:00000000-0000-0000-0000-000000000001","replace_item_id":"original-bag-item","equip":false})
    var command: PackedByteArray=proto.encode("ClientEnvelope",{"protocol_version":1,"type":"reward.choice.claim","request_id":"red-interop","expected_revision":9,"payload":payload})
    checks["claim encoded"]=proto.error.is_empty() and not command.is_empty()
    FileAccess.open(output.path_join("godot-claim.bin"),FileAccess.WRITE).store_buffer(command)
    var ok: bool=not checks.values().has(false)
    FileAccess.open(output.path_join("godot-checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"ok":ok,"checks":checks},"  "))
    print(JSON.stringify({"ok":ok,"checks":checks.size()}))
    quit(0 if ok else 1)
