extends RefCounted

class QuietGateway extends "res://network/gateway.gd":
	var sent: Array = []
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload.duplicate(true), "request_id": request_id})
		return true

func run_test() -> Dictionary:
	var checks := {}
	var gateway := QuietGateway.new()
	gateway.persist_session = false
	gateway.online = true
	var store: Node = load("res://state/game_store.gd").new()
	store.gateway = gateway
	var snapshot := {"room_id": "room", "match_id": "match", "room_revision": 3,
		"season": {"season_id": "season"}, "player": {"player_id": "self", "phase": "Pve", "combat_action": {"next_sequence": 7, "remaining_ms": 0}},
		"allowed_actions": ["battle.play_cards"]}
	store.room = snapshot
	store._adopt_room_context(snapshot)
	gateway.room_id = "room"
	gateway.current_match_id = "match"
	var queued := {"action": "battle.play_cards", "payload": {"battle_id": "battle", "target_id": "target", "card_instance_ids": ["card"]}}
	checks["new action sends"] = store._send_queued_command(queued)
	var original: Dictionary = gateway.sent[0]
	var action_id := str(original.payload.get("combat_action_id", ""))
	checks["server sequence prefixes random action id"] = action_id.begins_with("7:") and action_id.length() == 34
	checks["queued intent unchanged"] = not queued.payload.has("combat_action_id")
	checks["pending retains action id"] = store._pending_play.payload.combat_action_id == action_id
	checks["retry sends"] = store._send_queued_command({"action": "battle.play_cards", "payload": original.payload.duplicate(true), "retry": true})
	checks["retry keeps action id with new transport request"] = gateway.sent[1].payload.combat_action_id == action_id and gateway.sent[1].request_id != original.request_id
	snapshot.player.combat_action.remaining_ms = 500
	store._adopt_room_context(snapshot)
	checks["server remainder gates local input"] = not store.allowed("battle.play_cards")
	store._combat_ready_at = Time.get_ticks_msec()
	store._pending_commands.clear()
	store._pending_play = {}
	checks["local deadline expires without changing server sequence"] = store.allowed("battle.play_cards") and snapshot.player.combat_action.next_sequence == 7
	var origin: Dictionary = gateway.capture_context()
	store._pending_commands["old"] = {"action": "battle.play_cards"}
	store._pending_play = {"request_id": "old"}
	store._on_event("room.command_cancelled", {"room_id": "room", "match_id": "match", "command_type": "battle.play_cards",
		"reason": "CombatActionAlreadyApplied", "_command_action": "battle.play_cards", "_origin_context": origin, "_request_id": "old"})
	checks["old tombstone clears pending without closing room"] = store._pending_commands.is_empty() and store._pending_play.is_empty() and store.allowed("battle.play_cards")
	var proto: RefCounted = load("res://network/protobuf.gd").new()
	var body := {"combat_action_id": "1:" + "0".repeat(32)}
	checks["request tag 4 independent golden"] = proto.encode("BattlePlayCardsCommand", body).hex_encode() == "2222313a" + "30".repeat(32)
	var player := proto.decode("RoomPlayer", "b20105080710f403".hex_decode())
	checks["player tag 22 independent golden"] = proto.error.is_empty() and player.combat_action.next_sequence == 7 and player.combat_action.remaining_ms == 500
	var replay := proto.decode("BattleComboResolvedEvent", "e00101".hex_decode())
	checks["outcome tag 28 independent golden"] = proto.error.is_empty() and replay.action_replayed
	var delivered: Array = []
	gateway.event_received.connect(func(_kind, payload): delivered.append(payload))
	var outcome := proto.encode("BattleComboResolvedEvent", {"action_replayed": true})
	var envelope := proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "battle.combo_resolved", "sequence": 1, "payload": outcome})
	gateway._receive(envelope)
	checks["fresh-envelope action replay stays presentation-silent"] = delivered.size() == 1 and delivered[0].get("_replayed", false)
	store.free()
	gateway.free()
	return checks
