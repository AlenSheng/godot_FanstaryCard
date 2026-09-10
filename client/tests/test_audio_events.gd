extends RefCounted

class AudioGateway extends Node:
	const EVENTS := {}
	var online := true
	var recovering := false
	var token := ""
	var room_id := ""
	var room_revision := 0
	var session_generation := 0
	var sent: Array = []
	func new_id() -> String: return "sound-request-" + str(sent.size())
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload, "request_id": request_id})
		return true

func _snapshot(room_id: String = "room", battle_id: String = "battle", hand: Array = ["a"]) -> Dictionary:
	return {"room_id": room_id, "match_id": "match-" + room_id, "room_revision": 10, "player": {"player_id": "self", "phase": "Pve", "hand": hand.map(func(id): return {"instance_id": id})}, "pve": {"battle_id": battle_id, "current_target_id": "monster", "monsters": [{"monster_id": "monster", "hp": 10}]}, "allowed_actions": ["battle.play_cards"]}

func _dispatch(store: Node, gateway: Node, action: String) -> String:
	store._send_queued_command({"action": action, "payload": {}})
	return gateway.sent.back().request_id

func run_test() -> Dictionary:
	var store = load("res://state/game_store.gd").new()
	var gateway := AudioGateway.new()
	store.gateway = gateway
	var sounds: Array = []
	var checks: Dictionary = {}
	store.sound_requested.connect(func(cue): sounds.append(cue))
	store._on_event("room.snapshot", _snapshot())
	checks.first_snapshot_silent = sounds.is_empty()
	store._on_event("room.snapshot", _snapshot("room", "battle", ["a", "b"]))
	checks.new_card_once = sounds == ["card_draw"]
	sounds.clear()
	store._on_event("room.snapshot", _snapshot("room", "battle", ["a", "b"]))
	store._on_event("room.snapshot", _snapshot("room", "new-battle", ["c"]))
	checks.same_hand_and_new_battle_silent = sounds.is_empty()
	store.toggle_card("missing")
	store.toggle_card("c")
	store.toggle_card("c")
	checks.valid_selection_only = sounds == ["card_select", "card_select"]
	sounds.clear()
	gateway.recovering = true
	store.toggle_card("c")
	checks.recovery_selection_locked = sounds.is_empty()
	gateway.recovering = false
	var hit := {"battle_id": "new-battle", "attacker_id": "self", "target_id": "monster", "card_instance_ids": ["c"], "damage": 9, "damage_segments": [{"kind": "Fire", "amount": 3}, {"kind": "Water", "amount": 6}], "heal": 2, "shield_gain": 3, "_sequence": 1}
	store._on_event("combat.previewed", hit)
	checks.preview_silent = sounds.is_empty()
	store._on_event("battle.combo_resolved", hit)
	checks.combat_cues = sounds == ["card_play", "hit_water", "heal", "shield"]
	sounds.clear()
	store._on_event("battle.combo_resolved", hit)
	hit._sequence = 2
	hit.battle_id = "old-battle"
	store._on_event("battle.combo_resolved", hit)
	checks.duplicate_and_old_battle_silent = sounds.is_empty()
	hit.battle_id = "new-battle"
	hit.attacker_id = "opponent"
	hit.target_id = "self"
	hit.heal = 0
	hit.shield_gain = 0
	store._on_event("combat.hit", hit)
	checks.incoming_no_card_play = sounds == ["hit_water"]
	sounds.clear()
	for index in range(6):
		hit._sequence = 3 + index
		hit.damage_segments = [{"kind": ["Direct", "Fire", "Water", "Wood", "Metal", "Earth"][index], "amount": 9}]
		store._on_event("combat.hit", hit)
	checks.all_damage_types = sounds == ["hit_direct", "hit_fire", "hit_water", "hit_wood", "hit_metal", "hit_earth"]
	sounds.clear()
	hit._sequence = 9
	hit.damage = 0
	hit.damage_segments = []
	store._on_event("combat.hit", hit)
	checks.zero_damage_silent = sounds.is_empty()
	var actions := ["reward.choice.claim", "relic.take", "relic.replace", "inventory.equip", "inventory.unequip", "action.potion", "room.move", "action.extract"]
	var events := ["reward.choice_claimed", "relic.taken", "relic.replaced", "inventory.changed", "inventory.changed", "action.potion_used", "room.moved", "action.extract_started"]
	for index in range(actions.size()):
		var request_id := _dispatch(store, gateway, actions[index])
		var payload := {"_request_id": request_id, "action": actions[index]}
		store._on_event(events[index], payload)
		store._on_event(events[index], payload)
	checks.confirmed_actions_once = sounds == ["reward", "reward", "reward", "equip", "equip", "potion", "move", "extract_start"]
	sounds.clear()
	store._on_event("relic.taken", {"_request_id": "unsent-request"})
	var failed_request := _dispatch(store, gateway, "inventory.equip")
	store._on_event("error.command_rejected", {"_request_id": failed_request})
	store._on_event("inventory.changed", {"_request_id": failed_request, "action": "inventory.equip"})
	checks.failed_command_no_success = sounds == ["error"]
	sounds.clear()
	var stale_request := _dispatch(store, gateway, "relic.take")
	store._on_event("room.snapshot", _snapshot("room-next"))
	store._on_event("relic.taken", {"_request_id": stale_request})
	checks.other_room_ack_silent = sounds.is_empty()
	store._on_event("action.extract_completed", {"status": "Completed", "_event_revision": 9})
	checks.old_transition_silent = sounds.is_empty()
	store._on_event("action.extract_completed", {"status": "Completed", "_event_revision": 11})
	var terminal := _snapshot("room-next")
	terminal.player.phase = "Extracted"
	store._on_event("room.snapshot", terminal)
	store.settlement = {"settlementId": "settled"}
	store._on_event("settlement.ready", {"settlement_id": "settled", "match_id": "match-room-next", "result": "Extracted"})
	checks.terminal_event_snapshot_settlement_once = sounds == ["extract_success"]
	sounds.clear()
	store._on_event("room.snapshot", _snapshot("room-death"))
	terminal = _snapshot("room-death")
	terminal.player.phase = "Dead"
	store._on_event("room.snapshot", terminal)
	store._on_event("player.died", {"player_id": "self", "_event_revision": 10})
	checks.snapshot_death_once = sounds == ["death"]
	sounds.clear()
	terminal = _snapshot("old-finished-room")
	terminal.player.phase = "Extracted"
	store._on_event("room.snapshot", terminal)
	store._on_event("action.extract_completed", {"status": "Completed"})
	checks.existing_terminal_room_silent = sounds.is_empty()
	store._on_event("room.snapshot", _snapshot("room-settlement"))
	store._on_event("settlement.ready", {"settlement_id": "settled", "match_id": "other-match", "result": "Extracted"})
	checks.other_match_settlement_silent = sounds.is_empty()
	store._on_event("settlement.ready", {"settlement_id": "settled", "match_id": "match-room-settlement", "result": "Extracted"})
	store._on_event("match.settled", {"settlement_id": "settled", "match_id": "match-room-settlement", "result": "Extracted"})
	checks.settlement_fallback_once = sounds == ["extract_success"]
	sounds.clear()
	store._on_event("room.snapshot", _snapshot("room-reconnect"))
	var pending := _dispatch(store, gateway, "relic.take")
	store._on_connection_changed("正在连接实时服务")
	store._on_event("room.snapshot", _snapshot("room-reconnect", "battle", ["recovered"]))
	store._on_event("relic.taken", {"_request_id": pending})
	checks.reconnected_baseline_and_pending_silent = sounds.is_empty()
	var replay := _snapshot("room-reconnect", "battle", ["recovered", "during-replay"])
	replay._replayed = true
	store._on_event("room.snapshot", replay)
	store._on_event("action.extract_completed", {"status": "Completed", "_replayed": true})
	checks.replayed_snapshot_and_terminal_silent = sounds.is_empty()
	store.free()
	gateway.free()
	checks.wire_replay = _wire_replay_test()
	return {"ok": checks.values().all(func(value): return value == true), "message": "Audio follows confirmed current actions; previews, duplicates, stale rooms/battles and reconnect replay stay silent", "checks": checks}

func _wire_replay_test() -> bool:
	var store = load("res://state/game_store.gd").new()
	var gateway = load("res://network/gateway.gd").new()
	var proto = load("res://network/protobuf.gd").new()
	gateway.persist_session = false
	gateway.online = true
	store.gateway = gateway
	gateway.event_received.connect(store._on_event)
	gateway.connection_changed.connect(store._on_connection_changed)
	var sounds: Array = []
	var replay_flags: Array = []
	store.sound_requested.connect(func(cue): sounds.append(cue))
	gateway.event_received.connect(func(_kind, payload): replay_flags.append(payload.get("_replayed", false)))
	store._on_event("room.snapshot", _snapshot())
	gateway.last_sequence = 10
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "session.connected", "sequence": 14}))
	for sequence in [11, 12, 13]:
		var kind := "action.extract_completed" if sequence < 13 else "player.died"
		var schema := "ActionExtractEvent" if sequence < 13 else "PlayerDiedEvent"
		gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": kind, "sequence": sequence, "payload": proto.encode(schema, {"status": "Completed", "player_id": "self"})}))
	var ok: bool = sounds.is_empty() and replay_flags == [true, true, true] and not gateway.recovering
	replay_flags.clear()
	gateway.last_sequence = 20
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "session.connected", "sequence": 24}))
	var snapshot := _snapshot()
	snapshot.config_version = store.CATALOG.data.version
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "room.snapshot", "sequence": 21, "payload": proto.encode("RoomSnapshotEvent", snapshot)}))
	for sequence in [22, 23]:
		gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "player.died", "sequence": sequence, "payload": proto.encode("PlayerDiedEvent", {"player_id": "self"})}))
	ok = ok and sounds.is_empty() and replay_flags == [true, true, true] and not gateway.recovering
	store._on_event("room.snapshot", _snapshot())
	store._sound_commands["wire-claim"] = {"action": "reward.choice.claim", "room_id": "room"}
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "reward.choice_claimed", "sequence": 25, "request_id": "wire-claim", "payload": proto.encode("RewardChoiceClaimedEvent", {"option_id": "reward", "applied": 1})}))
	ok = ok and sounds == ["reward"]
	store.free()
	gateway.free()
	return ok
