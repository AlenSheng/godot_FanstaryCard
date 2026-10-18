extends RefCounted

class Probe extends "res://tests/gameplay_load_client.gd":
	func _ready() -> void: set_process(false)

class QuietGateway extends "res://network/gateway.gd":
	var recovery_requests := 0
	func connect_realtime() -> void: recovery_requests += 1

class OfflineStore extends "res://state/game_store.gd":
	func _ready() -> void: set_process(false)
	func _process_client_info() -> void: pass
	func _check_shop_rotation() -> void: pass

func run_test() -> Dictionary:
	var checks := {}
	var store = OfflineStore.new()
	var gateway = QuietGateway.new()
	gateway.persist_session = false
	store.gateway = gateway
	var probe = Probe.new()
	probe.Game = store
	probe.own_user_id = "self"
	probe.hero_profile = "Priest"
	probe.active_match_id = "match"
	probe.stage = "playing"
	probe.last_progress_ms = 1
	probe.last_transport_progress_ms = 1
	store.room = {"room_id":"room", "match_id":"match", "player":{"hand":[], "combat":{"hp":80,"maximum_hp":70}}, "pve":{"battle_id":"battle"}}
	probe._on_event("pong", {})
	probe._on_event("room.snapshot", {})
	probe._on_event("room.snapshot", {})
	checks["pong and duplicate snapshots only advance transport"] = probe.last_progress_ms == 1 and probe.last_transport_progress_ms > 1
	probe._observe_battle()
	probe.last_progress_ms = 1
	probe._on_event("battle.combo_resolved", {"attacker_id":"self", "battle_id":"battle", "card_instance_ids":["spent"], "hp_damage":0,"shield_damage":0,"heal":0,"shield_gain":0})
	checks["zero effect combo cannot keep gameplay alive"] = probe.last_progress_ms == 1 and not probe.telemetry[-1].gameplay_progress and probe.battle_metrics.zero_effective_actions == 1
	store.room.player.hand = [{"instance_id":"new-draw"}]
	probe._observe_battle()
	checks["new draw is legal progress despite zero damage with explicit reason"] = probe.last_progress_ms > 1 and probe.last_gameplay_progress_reason == "new_draw_opportunity" and probe.battle_metrics.observed_cards_drawn == 1
	probe.last_progress_ms = 1
	probe._observe_battle()
	checks["same hand observed twice does not invent another opportunity"] = probe.last_progress_ms == 1 and probe.battle_metrics.observed_cards_drawn == 1
	checks["legal Priest 80 over 70 display data untouched"] = store.room.player.combat.hp == 80 and store.room.player.combat.maximum_hp == 70
	probe._on_telemetry({"type":"realtime", "result":"rejected", "request_id":"rejected", "action":"battle.play_cards"})
	probe._on_telemetry({"type":"command_lifecycle", "event_type":"command.sent", "result":"sent", "request_id":"sent"})
	probe._on_telemetry({"type":"command_lifecycle", "event_type":"command.timeout", "result":"timeout", "execution_outcome":"unknown", "request_id":"unknown"})
	checks["sent rejected and unknown timeout are independent not gameplay success"] = probe.last_progress_ms == 1 and probe.telemetry[-1].result == "timeout" and probe.telemetry[-1].execution_outcome == "unknown" and not probe.telemetry[-1].gameplay_progress
	probe._on_event("battle.combo_resolved", {"attacker_id":"self", "battle_id":"battle", "card_instance_ids":["real"], "hp_damage":2})
	checks["positive effective combo still advances gameplay"] = probe.last_progress_ms > 1 and probe.last_gameplay_progress_reason == "effective_combo" and probe.battle_metrics.effective_actions == 1
	probe.ready_accepted = false
	probe.stage = "matchmaking"
	checks["waiting stage distinguishes ticket authority"] = probe._progress_waiting_stage() == "ticket_authority"
	probe.ready_successful_sends = 1
	checks["waiting stage distinguishes command acceptance"] = probe._progress_waiting_stage() == "ready_acceptance"
	probe.ready_accepted = true
	checks["waiting stage distinguishes started"] = probe._progress_waiting_stage() == "started"
	probe.stage = "settlement"
	checks["waiting stage locates acknowledgement instead of generic settlement"] = probe._progress_waiting_stage() == "settlement_acknowledgement"
	var traces: Array = []
	store.network_telemetry.connect(func(sample): traces.append(sample.duplicate(true)))
	store.room = {}
	store._pending_commands["unconfirmed"] = {"deadline":0, "action":"battle.play_cards", "origin_context":{"match_id":"old-match","room_id":"old-room","cycle_id":"old-cycle"}}
	store._process(0.0)
	checks["actual store expiry emits unknown timeout and removes without retry"] = traces.size() == 1 and traces[0].event_type == "command.timeout" and traces[0].execution_outcome == "unknown" and traces[0].match_id == "old-match" and traces[0].cycle_id == "old-cycle" and store._pending_commands.is_empty() and gateway.recovery_requests == 0
	store._pending_commands["confirmed"] = {"deadline":0, "action":"room.move", "confirmed":true, "origin_context":{"match_id":"old-match","room_id":"old-room"}}
	store._process(0.0)
	checks["confirmed state timeout remains distinct and preserves existing recovery"] = traces.size() == 2 and traces[1].event_type == "command.state_timeout" and traces[1].result == "state_timeout" and traces[1].execution_outcome == "confirmed_state_missing" and gateway.recovery_requests == 1 and store._pending_commands.is_empty()
	checks["diagnostic trace contains no packet or authentication bytes"] = traces.all(func(sample): return not sample.has("payload") and not sample.has("Authorization") and not sample.has("access_token"))
	probe.free()
	store.free()
	gateway.free()
	return {"ok":not checks.values().has(false), "checks":checks, "scope":"OFFLINE deterministic consumer/deadline regression fixtures, no new authority worlds or LIVE/PG claim"}
