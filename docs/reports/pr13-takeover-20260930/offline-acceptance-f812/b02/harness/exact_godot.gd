extends SceneTree

var failures: Array[String] = []
var rows: Array = []
var game: Node
const Proto = preload("res://network/protobuf.gd")

func _initialize() -> void:
	call_deferred("_run")

func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)

func packet(revision: int, sequence: int, request_id: String, damage: int) -> PackedByteArray:
	var proto := Proto.new()
	var payload := proto.encode("BattleComboResolvedEvent", {"battle_id":"00000000-0000-0000-0000-000000000020", "target_id":"monster-a", "card_instance_ids":game.selected_cards.duplicate(), "damage":damage})
	return proto.encode("ServerEnvelope", {"protocol_version":1,"type":"combat.previewed","trace_id":"b02","payload":payload,"event_id":"event-"+str(sequence),"sequence":sequence,"occurred_at_unix_ms":10000,"request_id":request_id,"room_revision":revision})

func _run() -> void:
	game = root.get_node("Game")
	game.set_process(false)
	game.gateway.set_process(false)
	game.gateway.persist_session = false
	game.gateway.online = true
	game.gateway.recovering = false
	game.gateway.last_sequence = 0
	game.selected_cards = ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]
	var ids: Array = game.selected_cards.duplicate()
	var proto := Proto.new()
	var payload := {"battle_id":"00000000-0000-0000-0000-000000000020","target_id":"monster-a","card_instance_ids":ids}
	var encoded := proto.encode("BattlePlayCardsCommand",payload)
	var decoded := proto.decode("BattlePlayCardsCommand",encoded)
	check(decoded.card_instance_ids == ids,"Godot real repeated protobuf order")
	var reversed: Array = [ids[1],ids[0]]
	payload.card_instance_ids = reversed
	var reversed_decoded := proto.decode("BattlePlayCardsCommand",proto.encode("BattlePlayCardsCommand",payload))
	check(reversed_decoded.card_instance_ids == reversed,"Godot real reversed protobuf order")
	var wire_files := DirAccess.get_files_at(OS.get_environment("B02_EXACT_EVIDENCE"))
	var cpp_rows: Array=[]
	for name in wire_files:
		if name.begins_with("wire-") and name.ends_with(".bin"):
			var bytes := FileAccess.get_file_as_bytes(OS.get_environment("B02_EXACT_EVIDENCE")+"/"+name)
			var envelope := proto.decode("ClientEnvelope",bytes)
			var from_csharp := proto.decode("BattlePlayCardsCommand",envelope.payload)
			check(proto.error.is_empty() and from_csharp.card_instance_ids.size()==2,"C# to Godot real protocol decode "+name)
			var roundtrip := proto.decode("BattlePlayCardsCommand",proto.encode("BattlePlayCardsCommand",from_csharp))
			check(roundtrip.card_instance_ids == from_csharp.card_instance_ids,"C# to Godot to Godot roundtrip order "+name)
			cpp_rows.append({"file":name,"card_instance_ids":from_csharp.card_instance_ids,"roundtrip_ids":roundtrip.card_instance_ids})
	check(cpp_rows.size()==4,"all four C# wire receipts decoded")
	rows.append({"case_id":"PR13-B02.3-T02","actual":{"godot_order":decoded.card_instance_ids,"godot_reversed":reversed_decoded.card_instance_ids,"csharp_wire_rows":cpp_rows}})
	game.room = {"room_id":"room-a","room_revision":9,"allowed_actions":["battle.play_cards"],"player":{"hand":[{"instance_id":ids[0]},{"instance_id":ids[1]}]},"pve":{"battle_id":payload.battle_id,"current_target_id":"monster-a","monsters":[{"monster_id":"monster-a","hp":100,"shield":0}]}}
	game._preview_request = {"request_id":"current-request","context":game._preview_context(ids),"revision":9}
	game._preview_deadline = Time.get_ticks_msec()+10000
	var before_room: Dictionary = game.room.duplicate(true)
	game.gateway._receive(packet(9,1,"current-request",19))
	check(game.combat_preview.get("authoritative",false) and game.combat_preview.get("damage",0)==19,"current true wire preview accepted")
	var current: Dictionary = game.combat_preview.duplicate(true)
	game._preview_request = {"request_id":"new-request","context":game._preview_context(ids),"revision":9}
	game._preview_deadline = Time.get_ticks_msec()+10000
	game.gateway._receive(packet(8,2,"new-request",777))
	check(game.combat_preview==current and game.room==before_room,"expired revision true wire reply preserves current")
	game.gateway._receive(packet(9,3,"older-request",778))
	check(game.combat_preview==current,"older request true wire reply preserves current")
	rows.append({"case_id":"PR13-B02.3-T03","actual":{"current_revision":9,"stale_revision":8,"current_preview":current,"after_late_preview":game.combat_preview.duplicate(true),"room_unchanged":game.room==before_room,"protocol_sequence":game.gateway.last_sequence,"entry":"production Gateway._receive -> Game._on_event -> _accept_combat_preview"}})
	var out := {"suite":"b02-exact-godot","ok":failures.is_empty(),"failures":failures,"rows":rows,"server_override":game.gateway.base_url}
	var f := FileAccess.open(OS.get_environment("B02_GODOT_OUTPUT"),FileAccess.WRITE)
	f.store_string(JSON.stringify(out,"  "));f.close()
	print(JSON.stringify(out))
	quit(0 if failures.is_empty() else 1)
