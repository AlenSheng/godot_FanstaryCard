extends RefCounted

const Store = preload("res://state/game_store.gd")

class RecordingGateway extends "res://network/gateway.gd":
	var sent: Array = []
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload.duplicate(true), "request_id": request_id})
		return true

func snapshot() -> Dictionary:
	return {"room_id": "wait-room", "room_revision": 1,
		"allowed_actions": ["battle.play_cards", "battle.select_target", "relic.read"],
		"player": {"player_id": "player", "hero_class": "Mage", "phase": "Pve",
			"combat": {"hp": 70, "maximum_hp": 70}, "hand": [{"instance_id": "card", "card_id": "C11"}]},
		"pve": {"battle_id": "battle", "current_target_id": "fire-bat", "monsters": [
			{"monster_id": "fire-bat", "hp": 20, "maximum_hp": 20},
			{"monster_id": "murk-snail", "hp": 20, "maximum_hp": 20}]}}

func run_test() -> Dictionary:
	var store: Node = Store.new()
	var gateway: Node = RecordingGateway.new()
	gateway.persist_session = false
	gateway.online = true
	store.gateway = gateway
	store.room = snapshot()
	store.selected_cards = ["card"]
	var checks := {}
	var observed := {}
	checks["normal_hand_has_legal_opportunity"] = store.combat_wait_state().reason == "available" and store.combat_wait_state().legal_opportunity
	store.command("battle.select_target", {"battle_id": "battle", "target_id": "murk-snail"})
	observed["manual_debounce"] = store.combat_wait_state()
	checks["manual_target_debounce_has_specific_reason"] = observed.manual_debounce.reason == "target_confirming" and not observed.manual_debounce.legal_opportunity
	store._latest_commands["battle.select_target"].due = 0
	store._flush_latest_commands()
	observed["manual_inflight"] = store.combat_wait_state()
	var before: int = gateway.sent.size()
	store.play_cards()
	checks["manual_target_inflight_blocks_old_target_play"] = observed.manual_inflight.reason == "target_confirming" and gateway.sent.size() == before
	store._pending_commands.clear()
	store.room = snapshot()
	store.room.pve.monsters[0].hp = 0
	store._sync_pve_target()
	observed["death_fallback_queued"] = store.combat_wait_state()
	checks["death_fallback_sync_keeps_legal_opportunity"] = store.combat_target_id() == "murk-snail" and observed.death_fallback_queued.reason == "available" and observed.death_fallback_queued.legal_opportunity
	store._latest_commands["battle.select_target"].due = 0
	store._flush_latest_commands()
	observed["death_fallback_inflight"] = store.combat_wait_state()
	checks["death_fallback_inflight_keeps_legal_opportunity"] = observed.death_fallback_inflight.reason == "available" and observed.death_fallback_inflight.legal_opportunity
	store.play_cards()
	checks["explicit_play_targets_survivor"] = gateway.sent.back().kind == "battle.play_cards" and gateway.sent.back().payload.target_id == "murk-snail"
	observed["play_submitted"] = store.combat_wait_state()
	checks["submitted_play_waits_for_confirmation"] = observed.play_submitted.reason == "confirming" and not observed.play_submitted.legal_opportunity
	store._pending_commands.clear()
	store._pending_play.clear()
	store._latest_commands.clear()
	store.room = snapshot()
	store._pending_commands["read"] = {"action": "relic.read", "payload": {}}
	observed["unrelated_read"] = store.combat_wait_state()
	checks["unrelated_read_does_not_hide_legal_play"] = observed.unrelated_read.reason == "available" and observed.unrelated_read.legal_opportunity and store.allowed("battle.play_cards")
	store._pending_commands.clear()
	store._preview_request = {"request_id": "preview"}
	checks["readonly_preview_does_not_hide_legal_play"] = store.combat_wait_state().reason == "available" and store.combat_wait_state().legal_opportunity
	store._queued_command = {"action": "battle.play_cards", "payload": {}}
	checks["revision_retry_is_confirming"] = store.combat_wait_state().reason == "confirming" and not store.combat_wait_state().legal_opportunity
	store._queued_command.clear()
	gateway.recovering = true
	checks["connection_recovery_has_priority"] = store.combat_wait_state().reason == "recovering" and not store.combat_wait_state().legal_opportunity
	gateway.recovering = false
	store.room.player["stun_remaining_ms"] = 1500
	checks["stun_preserves_authoritative_duration"] = store.combat_wait_state().reason == "stunned" and store.combat_wait_state().remaining_ms == 1500
	store.room.player.erase("stun_remaining_ms")
	store.room.player.hand = []
	store.room.player["draw_block_remaining_ms"] = 900
	checks["draw_block_preserves_authoritative_duration"] = store.combat_wait_state().reason == "draw_blocked" and store.combat_wait_state().remaining_ms == 900
	store.room.player.erase("draw_block_remaining_ms")
	checks["empty_hand_waits_for_draw"] = store.combat_wait_state().reason == "drawing" and not store.combat_wait_state().legal_opportunity
	store.room.player.hand = snapshot().player.hand
	store.room.player.hand.append_array([{}, {}, {}, {}])
	checks["full_hand_still_allows_play"] = store.combat_wait_state().reason == "full_hand" and store.combat_wait_state().legal_opportunity
	store.free()
	gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks, "observed": observed}
