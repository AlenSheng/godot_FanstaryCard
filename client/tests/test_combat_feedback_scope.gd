extends RefCounted

func run_test() -> Dictionary:
	var store = load("res://state/game_store.gd").new()
	var gateway = load("res://network/gateway.gd").new()
	var proto = load("res://network/protobuf.gd").new()
	gateway.persist_session = false
	store.gateway = gateway
	gateway.event_received.connect(store._on_event)
	var delivered: Array = []
	var changes: Array = []
	store.combat_feedback.connect(func(payload): delivered.append(payload))
	store.changed.connect(func(): changes.append(true))
	store.room = {"room_id": "room", "player": {"player_id": "self"}, "pve": {"battle_id": "battle-new", "monsters": [{"monster_id": "reused-monster", "hp": 0}]}}
	for target_id in ["self", "reused-monster"]:
		store._on_event("combat.hit", {"battle_id": "battle-old", "target_id": target_id})
	store._on_event("combat.hit", {"battle_id": "battle-new", "target_id": "other-room-player"})
	store._on_event("combat.hit", {"battle_id": "battle-new", "target_id": ""})
	store._on_event("combat.hit", {"target_id": "self"})
	var ok: bool = delivered.is_empty() and changes.is_empty()
	for target_id in ["self", "reused-monster"]:
		store._on_event("combat.hit", {"battle_id": "battle-new", "target_id": target_id})
	ok = ok and delivered.size() == 2 and changes.is_empty()
	delivered.clear()
	store.room.erase("pve")
	store.room.duel = {"duel_id": "duel-new", "opponent_id": "opponent"}
	store._on_event("battle.combo_resolved", {"battle_id": "duel-old", "target_id": "self"})
	store._on_event("battle.combo_resolved", {"battle_id": "duel-new", "target_id": "reused-monster"})
	ok = ok and delivered.is_empty()
	for target_id in ["self", "opponent"]:
		store._on_event("battle.combo_resolved", {"battle_id": "duel-new", "target_id": target_id})
	ok = ok and delivered.size() == 2
	delivered.clear()
	gateway.last_sequence = 10
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "session.connected", "sequence": 14}))
	ok = ok and gateway.recovering
	# Include the final replay packet, which clears recovering before dispatch.
	for sequence in [11, 12, 13]:
		var battle_id := "duel-old" if sequence == 11 else "duel-new"
		gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "combat.hit", "sequence": sequence, "payload": proto.encode("BattleComboResolvedEvent", {"battle_id": battle_id, "target_id": "self", "damage": 7})}))
	ok = ok and delivered.is_empty() and not gateway.recovering and gateway.last_sequence == 14
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "combat.hit", "sequence": 15, "payload": proto.encode("BattleComboResolvedEvent", {"battle_id": "duel-new", "target_id": "self", "damage": 7})}))
	ok = ok and delivered.size() == 1
	delivered.clear()
	store.room = {}
	store._on_event("combat.hit", {"battle_id": "duel-new", "target_id": "self"})
	ok = ok and delivered.is_empty() and changes.is_empty()
	store.free()
	gateway.free()
	return {"ok": ok, "message": "Combat feedback stays within the current battle and visible targets; reconnect replay, including its final packet, never animates"}
