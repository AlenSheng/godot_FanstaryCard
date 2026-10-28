extends RefCounted

class Store extends "res://state/game_store.gd":
	func _ready() -> void: set_process(false)
	func _process_client_info() -> void: pass
	func _check_shop_rotation() -> void: pass

class RecordingGateway extends "res://network/gateway.gd":
	var sent: Array = []
	var attempts: Array = []
	var serial := 0
	var send_ok := true
	var reconnects := 0
	var reply_on_read: Callable
	func new_id() -> String:
		serial += 1
		return "rejected-state-" + str(serial)
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		var row := {"kind":kind,"payload":payload.duplicate(true),"request_id":request_id}
		attempts.append(row)
		if not send_ok: return false
		sent.append(row)
		if kind == "room.snapshot.read" and reply_on_read.is_valid(): reply_on_read.call(request_id)
		return true
	func connect_realtime() -> void:
		reconnects += 1
		online = false

func _room(revision: int = 10, room_id: String = "room", match_id: String = "match") -> Dictionary:
	return {"room_id":room_id,"match_id":match_id,"room_revision":revision,
		"allowed_actions":["battle.play_cards","battle.select_target","room.move"],
		"player":{"player_id":"self","phase":"Pve","hand":[{"instance_id":"card"}],"combat":{"hp":80,"maximum_hp":70}},
		"pve":{"battle_id":"battle","current_target_id":"monster","monsters":[{"monster_id":"monster","hp":84}]}}

func _reject(store, original: String) -> void:
	store._on_event("error.command_rejected", {"_request_id":original,"_command_action":"battle.play_cards",
		"_command_result":"rejected","_origin_context":{"session_generation":2,"room_context_epoch":7,"room_id":"room","match_id":"match"},
		"code":"COMMAND_REJECTED","detail":"Duel is not active in this room."})

func _synchronous_snapshot(request_id: String, store) -> void:
	var fresh := _room(12)
	fresh["_request_id"] = request_id
	fresh["config_version"] = store.CATALOG.data.version
	store._on_event("room.snapshot", fresh)

func run_test() -> Dictionary:
	var checks := {}
	for scenario in ["plain","unrelated_snapshot","stale_snapshot","replayed_snapshot","old_generation_reply","old_epoch_reply","duplicate_notice","read_failed","timeout","old_rejection","synchronous_reply","wire_rejection"]:
		var store := Store.new()
		var gateway := RecordingGateway.new()
		gateway.persist_session = false
		gateway.online = true
		gateway.session_generation = 2
		gateway.room_context_epoch = 7
		gateway.room_id = "room"
		gateway.current_match_id = "match"
		store.gateway = gateway
		store._room_context_epoch = 7
		store._room_context_room_id = "room"
		store._room_context_match_id = "match"
		store.room = _room()
		store.selected_cards = ["card"]
		var intent := {"battle_id":"battle","target_id":"monster","card_instance_ids":["card"]}
		store.command("battle.play_cards", intent)
		var original: String = gateway.sent[0].request_id
		if scenario == "old_rejection":
			gateway.session_generation = 3
			store._room_context_epoch = 8
			store.room = _room(20,"new-room","new-match")
			_reject(store,original)
			checks[scenario+": obsolete rejection cannot block or refresh a new room"] = store.room.room_id == "new-room" and store.allowed("room.move") and gateway.attempts.size() == 1
			store.free();gateway.free();continue
		if scenario == "read_failed": gateway.send_ok = false
		if scenario == "synchronous_reply": gateway.reply_on_read = _synchronous_snapshot.bind(store)
		if scenario == "wire_rejection":
			var failures: Array = []
			gateway.event_received.connect(store._on_event)
			gateway.failed.connect(func(message): failures.append(message))
			var proto = load("res://network/protobuf.gd").new()
			gateway._receive(proto.encode("ServerEnvelope", {"protocol_version":1,"type":"error.command_rejected","sequence":gateway.last_sequence+1,"request_id":original,"payload":proto.encode("CommandRejectedEvent",{"code":"COMMAND_REJECTED","detail":"Duel is not active in this room."})}))
			checks[scenario+": actual protobuf rejection still reaches the original failure signal"] = failures.size() == 1 and str(failures[0]).contains("Duel is not active")
		else: _reject(store,original)
		var reads: Array = gateway.attempts.filter(func(row): return row.kind == "room.snapshot.read")
		var snapshot_id: String = str(reads[0].request_id) if reads.size() == 1 else "missing-read"
		if scenario == "synchronous_reply":
			checks[scenario+": state read registered before synchronous callback"] = reads.size() == 1 and gateway.sent.filter(func(row): return row.kind == "battle.play_cards").size() == 1
			checks[scenario+": completed synchronous read is not made pending again"] = store.allowed("battle.play_cards") and not store.has_pending_commands()
			store.free();gateway.free();continue
		checks[scenario+": rejection starts one state read without retrying the write"] = reads.size() == 1 and gateway.sent.filter(func(row): return row.kind == "battle.play_cards").size() == 1 and not store._pending_commands.has(original)
		checks[scenario+": pending state blocks same and different stale writes"] = store.has_pending_commands() and not store.command("battle.play_cards",intent) and not store.command("room.move",{"row":1,"column":1})
		checks[scenario+": stale card selection and preview are retired"] = store.selected_cards.is_empty() and store.combat_preview.is_empty()
		if scenario == "duplicate_notice": _reject(store,original)
		if scenario in ["read_failed","timeout"]:
			var started := Time.get_ticks_msec()
			while Time.get_ticks_msec()-started < 3050: await Engine.get_main_loop().process_frame
			store._process(0)
			checks[scenario+": original three second state budget enters one authority recovery"] = store.room.is_empty() and store.room_authority_recovering() and gateway.reconnects == 1 and gateway.sent.filter(func(row): return row.kind == "battle.play_cards").size() == 1
			store._process(0)
			checks[scenario+": recovery and failed read are not repeated per frame"] = gateway.reconnects == 1 and gateway.attempts.filter(func(row): return row.kind == "room.snapshot.read").size() == 1
			store.free();gateway.free();continue
		var fresh := _room(12)
		fresh["_request_id"] = snapshot_id
		fresh["config_version"] = store.CATALOG.data.version
		if scenario in ["unrelated_snapshot","stale_snapshot","replayed_snapshot","old_generation_reply","old_epoch_reply"]:
			var unqualified := fresh.duplicate(true)
			if scenario == "unrelated_snapshot": unqualified._request_id = "periodic-read"
			elif scenario == "stale_snapshot": unqualified.room_revision = 9
			elif scenario == "replayed_snapshot": unqualified["_replayed"] = true
			else: unqualified["_origin_context"] = {"session_generation":1 if scenario == "old_generation_reply" else 2,"room_context_epoch":6 if scenario == "old_epoch_reply" else 7,"room_id":"room","match_id":"match"}
			store._on_event("room.snapshot",unqualified)
			checks[scenario+": unqualified state cannot release the write gate"] = not store.allowed("battle.play_cards") and store.has_pending_commands()
		store._on_event("room.snapshot",fresh)
		checks[scenario+": fresh correlated state allows only a new explicit intent"] = store.allowed("battle.play_cards") and not store.has_pending_commands() and store.command("battle.play_cards",intent) and gateway.sent.filter(func(row): return row.kind == "battle.play_cards").size() == 2 and gateway.sent.back().request_id != original
		checks[scenario+": exactly one read preserves legal80over70 and rejection outcome"] = gateway.attempts.filter(func(row): return row.kind == "room.snapshot.read").size() == 1 and store.room.player.combat.hp == 80 and store.room.player.combat.maximum_hp == 70
		store.free();gateway.free()
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual store rejection and elapsed3second recovery budget with recorded gateway; no server world or capacity acceptance"}
