extends SceneTree
const Proto=preload("res://network/protobuf.gd")
func _initialize() -> void:
	create_timer(30).timeout.connect(func():quit(1));call_deferred("run")
func run() -> void:
	var game=get_root().get_node("Game");game.set_process(false);game.gateway.set_process(false);game.gateway.persist_session=false;game.gateway.reconnect_enabled=false;game.gateway.socket.close()
	var sound=get_root().get_node("Sound");sound.persist_settings=false;sound.stop_all();sound.set_process(false)
	var folder := OS.get_environment("FANTASYCARD_ART_EVIDENCE")
	var checks := {}
	var proto := Proto.new()
	var envelope: Dictionary=proto.decode("ServerEnvelope",FileAccess.get_file_as_bytes(folder.path_join("regeneration.bin")))
	checks["actual CSharp projection envelope"]=proto.error.is_empty() and envelope.type=="room.snapshot" and envelope.sequence==1
	var state: Dictionary=proto.decode("RoomSnapshotEvent",envelope.payload)
	checks["original control version and season preserved"]=proto.error.is_empty() and state.config_version=="theme-control-wood" and state.season.config_version==state.config_version and state.season.season_id=="theme-wire"
	checks["one original boss"]=state.pve.monsters.size()==1 and state.pve.monsters[0].monster_id=="annihilation-core"
	var boss: Dictionary=state.pve.monsters[0]
	checks["new intent remains named regeneration"]=boss.intent_kind=="Regenerate"
	checks["published amount is actual5HP not200basispoints"]=boss.intent_value==5
	checks["initial boss HP has no theme multiplier"]=boss.maximum_hp==280 and boss.hp==187 and boss.boss_phase==1
	checks["Mage base70 remains legal"]=state.player.combat.maximum_hp==70
	var ok: bool=not checks.values().has(false)
	FileAccess.open(folder.path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"ok":ok,"checks":checks},"  "))
	print(JSON.stringify({"ok":ok,"checks":checks.size()}));quit(0 if ok else 1)
