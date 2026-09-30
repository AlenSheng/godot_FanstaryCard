extends RefCounted

class PreviewGateway extends "res://network/gateway.gd":
	var sent: Array = []
	func new_id() -> String: return "preview-contract-" + str(sent.size())
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload.duplicate(true), "request_id": request_id})
		return true

func _snapshot() -> Dictionary:
	return {"room_id": "room", "room_revision": 10, "allowed_actions": ["battle.play_cards", "battle.select_target"],
		"player": {"player_id": "player", "hero_class": "Mage", "phase": "Pve", "combat": {"hp": 60, "maximum_hp": 70}, "hand": [{"instance_id": "card", "card_id": "C11"}], "battle_status": {}, "numerical_state": {"fenxian_policy": "CurrentRhythm", "guardian_policy": "CurrentSteps"}},
		"pve": {"battle_id": "battle", "current_target_id": "fire-bat", "monsters": [{"monster_id": "fire-bat", "hp": 20}, {"monster_id": "murk-snail", "hp": 20}]}}

func _prepare_request(store, request_id: String = "authority") -> void:
	store._preview_request = {"request_id": request_id, "context": store._preview_context(store.selected_cards), "revision": 10}
	store._preview_deadline = Time.get_ticks_msec() + 1000
	store.combat_preview = {}

func _authority(request_id: String = "authority") -> Dictionary:
	return {"_request_id": request_id, "_room_revision": 10, "battle_id": "battle", "target_id": "fire-bat", "card_instance_ids": ["card"], "damage": 6, "hp_damage": 6, "shield_damage": 0}

func run_test() -> Dictionary:
	var checks := {}
	var store = load("res://state/game_store.gd").new()
	var gateway := PreviewGateway.new()
	gateway.persist_session = false
	gateway.online = true
	store.gateway = gateway
	store.room = _snapshot()
	store.toggle_card("card")
	checks["local_feedback_is_immediate_estimate"] = not store.combat_preview.is_empty() and not store.combat_preview.get("authoritative", false)
	# Run the real process entry after the existing selection debounce.
	if not store._preview_request.is_empty(): store._preview_request["due"] = 0
	store._process(0)
	var requests: Array = gateway.sent.filter(func(row): return row.kind == "combat.preview")
	checks["selection_sends_one_readonly_preview"] = requests.size() == 1 and store._pending_commands.is_empty()
	if not requests.is_empty():
		store._on_event("combat.previewed", _authority(requests[0].request_id))
	checks["live_authority_event_is_displayed"] = store.combat_preview.get("authoritative", false) and int(store.combat_preview.get("damage", 0)) == 6
	store._process(0)
	checks["no_preview_per_frame_loop"] = gateway.sent.filter(func(row): return row.kind == "combat.preview").size() == 1
	for scenario in ["health", "shield", "status", "policy", "weapon", "stun", "hand_level", "target_health", "target_death", "config", "future_revision", "wrong_target", "wrong_order", "recovering", "replayed"]:
		store.room = _snapshot()
		store.selected_cards = ["card"]
		gateway.recovering = false
		_prepare_request(store)
		var payload := _authority()
		match scenario:
			"health": store.room.player.combat.hp -= 1
			"shield": store.room.player.combat["shield"] = 1
			"status": store.room.player.battle_status["combo"] = 5
			"policy": store.room.player.numerical_state.fenxian_policy = "CoreCardsSpent"
			"weapon": store.room.player["weapon_level"] = 5
			"stun": store.room.player["stun_remaining_ms"] = 1000
			"hand_level": store.room.player.hand[0]["level"] = 5
			"target_health": store.room.pve.monsters[0].hp -= 1
			"target_death": store.room.pve.monsters[0].hp = 0
			"config": store.room["config_version"] = "changed-config"
			"future_revision": payload._room_revision = 11
			"wrong_target": payload.target_id = "murk-snail"
			"wrong_order": payload.card_instance_ids = ["other-card"]
			"recovering": gateway.recovering = true
			"replayed": payload["_replayed"] = true
		store._accept_combat_preview(payload)
		checks["reject_changed_" + scenario] = not store.combat_preview.get("authoritative", false)
	gateway.recovering = false
	store.room = _snapshot()
	store.selected_cards = ["card"]
	_prepare_request(store)
	store._accept_combat_preview(_authority())
	store._on_event("combat.hit", {"battle_id": "battle", "target_id": "fire-bat", "_request_id": "synthetic-hit"})
	checks["hit_invalidates_authority_before_snapshot"] = not store.combat_preview.get("authoritative", false) and store._preview_request.is_empty()
	store.room = _snapshot()
	store.selected_cards = ["card"]
	_prepare_request(store)
	store._accept_combat_preview(_authority())
	store.command("battle.select_target", {"battle_id": "battle", "target_id": "murk-snail"})
	var plays_before: int = gateway.sent.filter(func(row): return row.kind == "battle.play_cards").size()
	store.play_cards()
	checks["manual_target_click_invalidates_old_preview"] = not store.combat_preview.get("authoritative", false)
	checks["manual_target_confirmation_blocks_old_target_play"] = gateway.sent.filter(func(row): return row.kind == "battle.play_cards").size() == plays_before
	store._latest_commands.clear()
	store._pending_commands.clear()
	store._pending_play.clear()
	var dead := _snapshot()
	dead.room_revision = 11
	dead.pve.monsters[0].hp = 0
	store._on_event("room.snapshot", dead)
	checks["gdd_death_fallback_keeps_left_to_right_target"] = store.combat_target_id() == "murk-snail" and store.selected_cards == ["card"]
	store.play_cards()
	var plays: Array = gateway.sent.filter(func(row): return row.kind == "battle.play_cards")
	checks["explicit_play_after_gdd_fallback_uses_survivor"] = not plays.is_empty() and plays.back().payload.target_id == "murk-snail"
	store._pending_commands.clear()
	store._pending_play.clear()
	store._latest_commands.clear()
	store.room = _snapshot()
	store.selected_cards = ["card"]
	_prepare_request(store)
	store._accept_combat_preview(_authority())
	store._on_connection_changed("recovering")
	checks["connection_transition_invalidates_authority"] = store.combat_preview.is_empty() and store._preview_request.is_empty()
	store.room = _snapshot()
	store.selected_cards = ["card"]
	_prepare_request(store)
	store._preview_deadline = Time.get_ticks_msec() - 1
	store._process(0)
	var sent_before: int = gateway.sent.size()
	store._process(0)
	checks["timeout_does_not_resubmit_preview"] = store._preview_request.is_empty() and gateway.sent.size() == sent_before
	_prepare_request(store)
	store._on_event("combat.preview_rejected", {"_request_id": "authority", "code": "REVISION_CONFLICT"})
	store._process(0)
	checks["preview_rejection_does_not_retry_business_command"] = store._preview_request.is_empty() and store._pending_commands.is_empty() and store._queued_command.is_empty() and gateway.sent.size() == sent_before
	_prepare_request(store)
	var saved_room: Dictionary = store.room.duplicate(true)
	store._accept_combat_preview(_authority())
	store._on_event("combat.hit", {"battle_id": "old-battle", "target_id": "fire-bat"})
	checks["old_battle_hit_keeps_current_authority"] = store.combat_preview.get("authoritative", false)
	checks["readonly_preview_does_not_mutate_health_or_hand"] = store.room == saved_room
	store._on_event("battle.target_selected", {"battle_id": "battle", "target_id": "murk-snail"})
	checks["target_event_invalidates_authority_before_snapshot"] = not store.combat_preview.get("authoritative", false)
	# Two selections within the debounce produce one request with explicit order.
	store.room = _snapshot()
	store.room.player.hand.append({"instance_id": "other-card", "card_id": "C06"})
	store.selected_cards = []
	store.toggle_card("other-card")
	store.toggle_card("card")
	store._preview_request.due = 0
	store._process(0)
	var ordered_request: Dictionary = gateway.sent.back()
	checks["debounce_preserves_explicit_latest_order"] = ordered_request.kind == "combat.preview" and ordered_request.payload.card_instance_ids == ["other-card", "card"]
	store.toggle_card("other-card")
	var stale: Dictionary = _authority(ordered_request.request_id)
	stale.card_instance_ids = ["other-card", "card"]
	store._on_event("combat.previewed", stale)
	checks["new_selection_rejects_inflight_old_order"] = not store.combat_preview.get("authoritative", false)
	store.free()
	gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks}
