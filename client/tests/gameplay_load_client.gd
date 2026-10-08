extends Node

## Sustained gameplay load client: real Game store and gateway; no market writes.
## Each process owns one isolated local-development account and exercises the
## same REST/WebSocket paths as the client store without rendering the UI.

var base_url := "http://127.0.0.1:5000"
var client_id := "probe"
var run_id := ""
var process_epoch := ""
var event_seq := 0
var group_id := 1
var report_path := ""
var stop_file := ""
var started_at_ms := 0
var last_status_at_ms := 0
var stop_requested := false
var finishing := false
var finished := false
var checks: Array = []
var operations: Array = []
var telemetry: Array = []
var audit_buffer: Array[String] = []
var audit_lost_count := 0
var status_seq := 0
var events: Dictionary = {}
var errors: Array = []
var own_user_id := ""
var scenario_started := false
var scenario_finished := false
var Game: Node
var cycles_completed := 0
var max_cycles := 0
var stage := "starting"
var last_progress_ms := 0
var active_match_id := ""
var verified_ready_match_id := ""
var ready_required := false
var ready_accepted := false
var ready_deadline_unix_ms := 0
var ready_attempts := 0
var hero_profile := "Mage"
var strategy := "baseline_all_hand"
var strategy_seed := 20260930
var strategy_rng := RandomNumberGenerator.new()
var cleanup_result: Dictionary = {"state": "Unknown", "reason": "not_started"}
var battle_metrics: Dictionary = {}
var current_battle_id := ""
var battle_started_ms := 0
var last_effective_ms := 0
var observed_hand_ids: Array = []
var terminal_battle_ids: Dictionary = {}
var load_profile := "cyclic-gameplay"
var hold_seconds := 600
var run_seconds := 1800
var cycle_limit_seconds := 240
var cycle_battles_won := 0
var last_effective_action_ms := 0

func _ready() -> void:
	load_profile = OS.get_environment("FANTASYCARD_LOAD_PROFILE")
	if load_profile not in ["cyclic-gameplay", "active-hold", "functional-cycles", "cleared-extraction"]: load_profile = "cyclic-gameplay"
	var requested_hold := OS.get_environment("FANTASYCARD_LOAD_HOLD_SECONDS")
	if requested_hold.is_valid_int(): hold_seconds = clampi(int(requested_hold), 1, 3600)
	var requested_run := OS.get_environment("FANTASYCARD_LOAD_RUN_SECONDS")
	if requested_run.is_valid_int(): run_seconds = maxi(1,int(requested_run))
	cycle_limit_seconds = _cycle_limit(OS.get_environment("FANTASYCARD_LOAD_CYCLE_LIMIT_SECONDS"))
	Game = get_node("/root/Game")
	base_url = OS.get_environment("FANTASYCARD_SERVER_URL").strip_edges().trim_suffix("/")
	if base_url.is_empty(): base_url = "http://127.0.0.1:5000"
	client_id = OS.get_environment("FANTASYCARD_LOAD_CLIENT_ID").strip_edges()
	if client_id.is_empty(): client_id = "probe"
	run_id = OS.get_environment("FANTASYCARD_LOAD_RUN_ID").strip_edges()
	process_epoch = OS.get_environment("FANTASYCARD_LOAD_PROCESS_EPOCH").strip_edges()
	group_id = int(OS.get_environment("FANTASYCARD_LOAD_GROUP"))
	if group_id <= 0: group_id = 1
	report_path = OS.get_environment("FANTASYCARD_LOAD_REPORT").strip_edges()
	stop_file = OS.get_environment("FANTASYCARD_LOAD_STOP_FILE").strip_edges()
	if report_path.is_empty(): report_path = ProjectSettings.globalize_path("res://evidence/cloud-load/%s.json" % client_id)
	started_at_ms = Time.get_ticks_msec()
	last_progress_ms = started_at_ms
	max_cycles = int(OS.get_environment("FANTASYCARD_LOAD_MAX_CYCLES"))
	hero_profile = OS.get_environment("FANTASYCARD_LOAD_HERO_CLASS")
	if hero_profile not in ["Mage", "Priest", "Guardian"]: hero_profile = "Mage"
	strategy = OS.get_environment("FANTASYCARD_LOAD_STRATEGY")
	if strategy not in ["baseline_all_hand", "basic", "build"]: strategy = "baseline_all_hand"
	if OS.get_environment("FANTASYCARD_LOAD_SEED").is_valid_int(): strategy_seed = int(OS.get_environment("FANTASYCARD_LOAD_SEED"))
	strategy_rng.seed = strategy_seed
	DirAccess.make_dir_recursive_absolute(report_path.get_base_dir())
	Game.gateway.persist_session = false
	Game.gateway.use_reusable_http = OS.get_environment("FANTASYCARD_LOAD_HTTP_TRANSPORT") != "per-request"
	Game.gateway.device_id = "load-%s-%s" % [client_id, Game.gateway.new_id()]
	Game.gateway.last_sequence = 0
	Game.gateway.room_id = ""
	Game.gateway.room_revision = 0
	Game.notice.connect(_on_notice)
	Game.gateway.failed.connect(_on_notice)
	Game.gateway.event_received.connect(_on_event)
	Game.network_telemetry.connect(_on_telemetry)
	if cycle_limit_seconds == 0:
		_finish(false, "Invalid expedition observation limit")
		return
	call_deferred("_run")

func _cycle_limit(value: String) -> int:
	if value.is_empty(): return 240
	if not value.is_valid_int(): return 0
	var seconds := int(value)
	return seconds if seconds >= 60 and seconds <= 600 else 0

func _process(_delta: float) -> void:
	_update_context()
	if not stop_requested and not stop_file.is_empty() and FileAccess.file_exists(stop_file):
		stop_requested = true
	if Time.get_ticks_msec() - last_status_at_ms >= 5000:
		last_status_at_ms = Time.get_ticks_msec()
		_write_status()

func _run() -> void:
	stage = "login"
	await _login()
	if stop_requested:
		await _graceful_cleanup()
		await _finish(false, "Coordinator cancelled login", 0)
		return
	if not _check(not Game.lobby.is_empty() and Game.gateway.online, "login_and_bootstrap"):
		await _finish(false, "Login or bootstrap failed")
		return
	own_user_id = str(Game.lobby.get("player", {}).get("userId", ""))
	Game.select_class(hero_profile)
	var class_deadline := Time.get_ticks_msec() + 30000
	while Game._class_switch_request_active and Time.get_ticks_msec() < class_deadline and not stop_requested:
		await _wait(0.1)
	if not _check(str(Game.lobby.get("player", {}).get("selectedClass", "")) == hero_profile, "hero_class_confirmed"):
		await _graceful_cleanup()
		await _finish(false, "Hero class was not confirmed")
		return
	while not stop_requested:
		stage = "expedition"
		scenario_started = true
		scenario_finished = false
		await _run_expedition()
		if stop_requested: break
		if not scenario_finished:
			await _graceful_cleanup()
			await _finish(false, "Expedition did not reach acknowledged settlement")
			return
		_on_telemetry({"type": "lifecycle", "event_type": "cycle.completed", "match_id": active_match_id})
		cycles_completed += 1
		last_progress_ms = Time.get_ticks_msec()
		if max_cycles > 0 and cycles_completed >= max_cycles: break
		stage = "between_matches"
		await _wait(2.0)
	await _graceful_cleanup()
	if stop_requested:
		await _finish(false, "Coordinator cancelled current cycle", 0)
	else:
		await _finish(true, "Requested smoke cycles completed")

func _login() -> void:
	var account_name: String = ("L" + client_id + Game.gateway.new_id().left(4)).left(20)
	await Game.login(base_url, account_name)
	var deadline := Time.get_ticks_msec() + 30000
	while Time.get_ticks_msec() < deadline and (Game.lobby.is_empty() or not Game.gateway.online) and not stop_requested:
		await _wait(0.25)
	_check(Game.gateway.online, "realtime_connected")

func _run_expedition() -> void:
	cycle_battles_won = 0
	_update_context()
	await Game.prepare("Free", 0)
	if stop_requested: return
	if not _check(not Game.preparation.is_empty(), "create_free_preparation"): return
	_on_telemetry({"type": "lifecycle", "event_type": "preparation.created",
		"preparation_id": Game.preparation.get("preparationId", "")})
	active_match_id = ""
	verified_ready_match_id = ""
	ready_required = false
	ready_accepted = false
	ready_deadline_unix_ms = 0
	ready_attempts = 0
	await Game.enqueue()
	if stop_requested: return
	if not _check(not Game.ticket.is_empty(), "enqueue_match"): return
	_on_telemetry({"type": "lifecycle", "event_type": "match.queued",
		"preparation_id": Game.preparation.get("preparationId", ""),
		"ticket_id": Game.ticket.get("ticketId", "")})
	stage = "matchmaking"
	var deadline := Time.get_ticks_msec() + 60000
	var next_ready_send_ms := 0
	var next_verify_ms := 0
	var verified_match_id := ""
	while Game.room.is_empty() and Time.get_ticks_msec() < deadline and not stop_requested:
		var now_ms := Time.get_ticks_msec()
		var now_unix_ms := int(Time.get_unix_time_from_system() * 1000.0)
		# Poll the authoritative ticket even when the required notification was
		# missed. A matched ticket may trigger a bounded ready retry; the server
		# remains authoritative about the ready deadline and membership.
		if now_ms >= next_verify_ms and not ready_accepted:
			_update_context()
			var ticket_id := str(Game.ticket.get("ticketId", ""))
			if ticket_id.is_empty():
				_check(false, "ready_ticket_missing")
				return
			var ticket_result: Dictionary = await Game.gateway.request("/api/v1/matches/tickets/" + ticket_id)
			if stop_requested: return
			next_verify_ms = Time.get_ticks_msec() + 2000
			if ticket_result.ok and ticket_result.data is Dictionary:
				verified_match_id = str(ticket_result.data.get("matchId", ""))
				if not verified_match_id.is_empty() and str(ticket_result.data.get("status", "")) == "Matched":
					verified_ready_match_id = verified_match_id
					if active_match_id != verified_match_id:
						ready_attempts = 0
						ready_accepted = false
					active_match_id = verified_match_id
					ready_required = true
					ready_deadline_unix_ms = int(Game.ready_prompt.get("deadline_unix_ms", 0)) if str(Game.ready_prompt.get("match_id", "")) == verified_match_id else 0
				elif str(ticket_result.data.get("status", "")) in ["Cancelled", "Expired"]:
					_check(false, "ready_ticket_terminal")
					return
		now_ms = Time.get_ticks_msec()
		now_unix_ms = int(Time.get_unix_time_from_system() * 1000.0)
		if Game.room.is_empty() and ready_required and not active_match_id.is_empty() and active_match_id == verified_match_id and not ready_accepted and ready_attempts < 3 and now_ms >= next_ready_send_ms and (ready_deadline_unix_ms == 0 or now_unix_ms < ready_deadline_unix_ms):
			ready_attempts += 1
			var sent: bool = Game.gateway.send("room.ready")
			_on_telemetry({"type": "lifecycle", "event_type": "room.ready.send", "match_id": active_match_id, "attempt_no": ready_attempts, "result": "sent" if sent else "send_failed"})
			next_ready_send_ms = now_ms + 1000
		await _wait(0.25)
	if stop_requested: return
	if not _check(not Game.room.is_empty() and str(Game.room.get("match_id", "")) == active_match_id,
		"room_started" if not Game.room.is_empty() else "room_start_timeout"): return
	stage = "playing"
	# Capacity hold is an explicitly different workload: it keeps playing and
	# postpones voluntary extraction/fallback. Natural death remains terminal.
	deadline = Time.get_ticks_msec() + (maxi(cycle_limit_seconds, maxi(hold_seconds + 60, run_seconds + 30)) * 1000 if load_profile == "active-hold" else cycle_limit_seconds * 1000)
	var visited := {}
	while Game.settlement.is_empty() and Time.get_ticks_msec() < deadline and not stop_requested:
		_update_context()
		_observe_battle()
		if not Game.room.is_empty() and not Game.has_pending_commands():
			# This named functional scenario verifies clear/reward/move/abandon/
			# settlement/rejoin. It is never used as combat or capacity evidence.
			if load_profile == "functional-cycles" and cycle_battles_won > 0 and Game.allowed("battle.abandon"):
				if Game.command("battle.abandon"):
					_on_telemetry({"type": "lifecycle", "event_type": "battle.abandon.scenario", "match_id": active_match_id})
					_close_battle_metrics("ScenarioAbandon")
				await _wait(0.4)
				continue
			# This is an explicit script fallback, never a combat victory. Network
			# events and zero-damage combos cannot reset the effective-progress timer.
			if load_profile == "cyclic-gameplay" and Game.allowed("battle.abandon") and Time.get_ticks_msec() - last_effective_ms > 60000:
				if Game.command("battle.abandon"):
					_on_telemetry({"type": "lifecycle", "event_type": "battle.abandon.fallback", "match_id": active_match_id})
				await _wait(0.4)
				continue
			var pve: Dictionary = Game.room.get("pve", {})
			var current_dead: bool = pve.get("monsters", []).any(func(monster): return str(monster.get("monster_id", "")) == str(pve.get("current_target_id", "")) and int(monster.get("hp", 0)) <= 0)
			if current_dead and Game.allowed("battle.select_target"):
				for monster in pve.get("monsters", []):
					if int(monster.get("hp", 0)) > 0:
						Game.command("battle.select_target", {"battle_id": pve.get("battle_id", ""), "target_id": monster.get("monster_id", "")})
						break
			elif Game.allowed("battle.play_cards"):
				var hand: Array = Game.room.get("player", {}).get("hand", [])
				if not hand.is_empty():
					Game.selected_cards.clear()
					for instance_id in _select_cards(hand): Game.toggle_card(instance_id)
					Game.play_cards()
			elif Game.allowed("reward.choice.claim"):
				var options: Array = Game.room.get("reward_choice", {}).get("options", [])
				if not options.is_empty():
					var chosen: Dictionary = options[-1]
					if strategy != "baseline_all_hand":
						var combat: Dictionary = Game.room.get("player", {}).get("combat", {})
						for option in options:
							if int(option.get("kind", 0)) == 1 and int(combat.get("hp", 0)) > int(combat.get("maximum_hp", 1)) / 3:
								chosen = option
								break
					Game.command("reward.choice.claim", {"option_id": chosen.get("option_id", ""), "equip": strategy != "baseline_all_hand" and int(chosen.get("kind", 0)) == 1})
			elif Game.allowed("monster.choose"):
				var pending: Array = Game.room.get("player", {}).get("monster_pool", {}).get("pending", [])
				if not pending.is_empty(): Game.command("monster.choose", {"candidate_id": pending[0].get("instance_id", ""), "accept": false})
			elif _should_extract(visited):
				Game.command("action.extract")
			elif Game.allowed("action.spring"):
				Game.command("action.spring")
			elif Game.allowed("room.move"):
				var moves: Array = Game.room.get("legal_moves", []).duplicate()
				if not moves.is_empty():
					var move: Dictionary = _choose_move(moves, visited)
					var move_key: String = str(move.get("row", 0)) + ":" + str(move.get("column", 0))
					visited[move_key] = true
					Game.command("room.move", move)
		await _wait(0.4)
	if stop_requested: return
	_close_battle_metrics("Terminal" if not Game.settlement.is_empty() else "Censored")
	if Game.settlement.is_empty() and not Game.room.is_empty() and Game.allowed("action.extract"):
		Game.command("action.extract")
		await _wait(8.0)
	if not Game.settlement.is_empty():
		stage = "settlement"
		var settlement_match_id := str(Game.settlement.get("matchId", ""))
		var acknowledged: bool = await Game.acknowledge_settlement()
		_on_telemetry({"type": "lifecycle", "event_type": "settlement.acknowledged" if acknowledged else "settlement.ack_failed",
			"match_id": settlement_match_id})
		scenario_finished = _check(acknowledged and settlement_match_id == active_match_id and Game.room.is_empty() and Game.settlement.is_empty(), "settlement_acknowledged")

func _should_extract(visited: Dictionary) -> bool:
	if not Game.allowed("action.extract"): return false
	if load_profile == "cleared-extraction": return cycle_battles_won > 0
	return load_profile == "cyclic-gameplay" and not visited.is_empty()

func _choose_move(moves: Array, visited: Dictionary) -> Dictionary:
	if moves.is_empty(): return {}
	# Preserve the original seeded move selection for its original profiles.
	var shuffled: Array = moves.duplicate(true)
	for index in range(shuffled.size()-1,0,-1):
		var other := strategy_rng.randi_range(0,index)
		var temporary: Variant = shuffled[index]
		shuffled[index] = shuffled[other]
		shuffled[other] = temporary
	var unvisited: Array = shuffled.filter(func(candidate): return not visited.has(str(candidate.get("row",0))+":"+str(candidate.get("column",0))))
	if load_profile != "cleared-extraction": return shuffled[0] if unvisited.is_empty() else unvisited[0]
	# This separate functional profile searches the outer legal ring before
	# voluntarily going inward. Evacuation/monster/path secrets are absent from
	# this decision: only supplied legal positions and our visited set are read.
	var options: Array = shuffled if unvisited.is_empty() else unvisited
	var best: Dictionary = options[0]
	var best_layer := mini(mini(int(best.row),int(best.column)),mini(5-int(best.row),5-int(best.column)))
	for candidate in options:
		var layer := mini(mini(int(candidate.row),int(candidate.column)),mini(5-int(candidate.row),5-int(candidate.column)))
		if layer<best_layer:
			best=candidate
			best_layer=layer
	return best

func _graceful_cleanup() -> void:
	stage = "cleanup"
	var cleanup_generation: int = Game.gateway.session_generation
	var cleanup_cycle_match_id := active_match_id
	var cleanup_preparation_id := str(Game.preparation.get("preparationId", ""))
	var cleanup_ticket_id := str(Game.ticket.get("ticketId", ""))
	_update_context()
	_close_battle_metrics("Stopped" if stop_requested else "Terminal")
	# A deliberate drain uses the same legal exit as a player. Its abandon/ACK
	# is recorded separately and cannot increase completed gameplay cycles.
	if Game.settlement.is_empty() and not Game.room.is_empty():
		var exit_deadline := Time.get_ticks_msec() + 6000
		while Time.get_ticks_msec() < exit_deadline and Game.settlement.is_empty():
			var exit_action := "battle.abandon" if Game.allowed("battle.abandon") else "action.extract" if Game.allowed("action.extract") else ""
			if not exit_action.is_empty() and Game.command(exit_action):
				_on_telemetry({"type": "lifecycle", "event_type": "cleanup.exit_requested", "match_id": active_match_id, "action": exit_action})
				break
			await _wait(0.2)
		var settlement_deadline := Time.get_ticks_msec() + 6000
		while Game.settlement.is_empty() and not Game.room.is_empty() and Time.get_ticks_msec() < settlement_deadline:
			await _wait(0.2)
	if Game.room.is_empty() and Game.settlement.is_empty() and (not Game.ticket.is_empty() or not Game.preparation.is_empty()):
		await Game.cancel_preparation()
	if not Game.settlement.is_empty():
		var cleanup_match_id := str(Game.settlement.get("matchId", ""))
		if await Game.acknowledge_settlement():
			_on_telemetry({"type": "lifecycle", "event_type": "settlement.acknowledged", "match_id": cleanup_match_id, "completion_stage": "drain_ack_only"})
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	# A disconnected live room needs the server's grace/settlement workers.
	# The coordinator separately bounds process drain; unresolved business state
	# is preserved explicitly instead of claiming socket close released assets.
	cleanup_result = {"state": "Unknown", "reason": "verification_failed"}
	var cleanup_deadline := Time.get_ticks_msec() + 22000
	var cleanup_ack_attempts := 0
	while Time.get_ticks_msec() < cleanup_deadline:
		var verification: Dictionary = await Game.gateway.request("/api/v1/bootstrap", HTTPClient.METHOD_GET, null, [0, 401, 503])
		if not verification.ok or not verification.data is Dictionary: break
		if Game.gateway.session_generation != cleanup_generation or active_match_id != cleanup_cycle_match_id or str(Game.preparation.get("preparationId", "")) not in ["", cleanup_preparation_id] or str(Game.ticket.get("ticketId", "")) not in ["", cleanup_ticket_id]:
			cleanup_result = {"state": "Unknown", "reason": "cleanup_context_changed"}
			break
		if str(verification.data.get("configVersion", "")) != str(Game.CATALOG.data.version) or not verification.data.has_all(["activePreparation", "unfinishedMatch", "unfinishedSettlement"]):
			cleanup_result = {"state": "Unknown", "reason": "invalid_bootstrap_contract"}
			break
		var unfinished: Variant = verification.data.get("unfinishedSettlement")
		if unfinished is Dictionary and str(unfinished.get("matchId", "")) == active_match_id:
			if cleanup_ack_attempts >= 3:
				cleanup_result = {"state": "Unknown", "reason": "settlement_ack_unresolved"}
				break
			cleanup_ack_attempts += 1
			Game.settlement = unfinished
			if await Game.acknowledge_settlement():
				_on_telemetry({"type": "lifecycle", "event_type": "settlement.acknowledged", "match_id": active_match_id, "completion_stage": "drain_ack_only"})
			else: await _wait(1.0)
			continue
		var pending: bool = verification.data.get("activePreparation") is Dictionary or verification.data.get("unfinishedMatch") is Dictionary or unfinished is Dictionary
		cleanup_result = {"state": "Unknown" if pending else "Passed", "reason": "server_state_pending" if pending else "server_state_clear",
			"active_preparation": verification.data.get("activePreparation"), "unfinished_match": verification.data.get("unfinishedMatch"), "unfinished_settlement": unfinished}
		if not pending:
			if not Game.room.is_empty() or not Game.settlement.is_empty():
				cleanup_result = {"state": "Unknown", "reason": "client_terminal_pending"}
				break
			# A matched ticket cannot be DELETE-cancelled. After its actual ready
			# deadline the socket may already be closed, so ready_removed cannot
			# clear this local context. Clear only after the same session/cycle's
			# complete authoritative bootstrap confirms no unfinished business.
			Game.ticket = {}
			Game.preparation = {}
			Game.ready_prompt = {}
			Game.lobby["activePreparation"] = null
			if verification.data.get("inventory") is Dictionary:
				Game.update_cache("inventory", verification.data.inventory)
			Game.changed.emit()
			break
		await _wait(1.0)
	_on_telemetry({"type": "lifecycle", "event_type": "cleanup.verified", "cleanup": cleanup_result})

func _update_context() -> void:
	Game.gateway.telemetry_context = {"run_id": run_id, "client_id": client_id,
		"process_epoch": process_epoch, "cycle_id": "%s:%d" % [client_id, cycles_completed + 1],
		"phase": _current_phase(), "hero_class": hero_profile, "strategy": strategy,
		"load_profile": load_profile,
		"strategy_seed": strategy_seed, "config_version": Game.lobby.get("configVersion", ""),
		"battle_id": current_battle_id}

func _select_cards(hand: Array) -> Array:
	var all_ids: Array = hand.map(func(card): return str(card.get("instance_id", "")))
	if strategy == "baseline_all_hand": return all_ids
	var combat: Dictionary = Game.room.get("player", {}).get("combat", {})
	var elemental_counts: Dictionary = {}
	for instance in hand:
		var definition: Dictionary = Game.CatalogIndex.card(str(instance.get("card_id", "")))
		if int(definition.get("elemental_damage", 0)) > 0 and int(definition.get("secondary_elemental_damage", 0)) == 0:
			var element := str(definition.get("element", "None"))
			if element != "None": elemental_counts[element] = int(elemental_counts.get(element, 0)) + 1
	var has_group: bool = elemental_counts.values().any(func(count): return int(count) >= 2)
	var healthy: bool = int(combat.get("hp", 0)) > int(combat.get("maximum_hp", 1)) / 4
	if healthy and hand.size() < 3 and not has_group:
		return []
	var best: Array = []
	var best_score := -INF
	for mask in range(1, 1 << hand.size()):
		var selected: Array = []
		for index in hand.size():
			if mask & (1 << index): selected.append(all_ids[index])
		var orders: Array = [selected]
		if strategy == "build":
			for first in selected:
				var ordered: Array = selected.duplicate()
				ordered.erase(first)
				ordered.push_front(first)
				orders.append(ordered)
		for ordered in orders:
			# The pure client preview reads current hand/public target only.
			var preview: Dictionary = Game._calculate_combat_preview(ordered)
			if preview.is_empty(): continue
			var score: float = float(preview.get("hp_damage", 0)) + float(preview.get("shield_damage", 0)) + .8 * float(preview.get("heal", 0)) + .5 * float(preview.get("shield_gain", 0)) + .7 * float(preview.get("stun_seconds", 0)) + 2 * float(preview.get("immediate_draw", 0)) + 2 * float(preview.get("draw_charge", 0)) - .25 * ordered.size()
			if score > best_score:
				best_score = score
				best = ordered.duplicate()
	return best if not best.is_empty() else all_ids

func _observe_battle() -> void:
	var pve: Dictionary = Game.room.get("pve", {})
	var duel: Dictionary = Game.room.get("duel", {})
	var battle_id := str(pve.get("battle_id", duel.get("duel_id", "")))
	if terminal_battle_ids.has(battle_id): return
	if battle_id != current_battle_id:
		_close_battle_metrics("PhaseChanged")
		current_battle_id = battle_id
		if battle_id.is_empty(): return
		battle_started_ms = Time.get_ticks_msec()
		last_effective_ms = battle_started_ms
		last_effective_action_ms = battle_started_ms
		observed_hand_ids = Game.room.get("player", {}).get("hand", []).map(func(card): return str(card.get("instance_id", "")))
		battle_metrics = {"battle_id": battle_id, "actions": 0, "effective_actions": 0, "zero_effective_actions": 0,
			"hp_damage": 0, "shield_damage": 0, "heal": 0, "shield_gain": 0, "observed_cards_drawn": 0,
			"first_effective_ms": null, "longest_effective_gap_ms": 0}
	if battle_id.is_empty(): return
	var hand_ids: Array = Game.room.get("player", {}).get("hand", []).map(func(card): return str(card.get("instance_id", "")))
	var new_cards: int = hand_ids.filter(func(instance_id): return not observed_hand_ids.has(instance_id)).size()
	if new_cards > 0:
		battle_metrics.observed_cards_drawn += new_cards
		last_effective_ms = Time.get_ticks_msec()
	observed_hand_ids = hand_ids
	var waiting: Dictionary = Game.combat_wait_state()
	_on_telemetry({"type": "battle_observation", "event_type": "battle.observed", "battle_id": battle_id,
		"elapsed_ms": Time.get_ticks_msec() - battle_started_ms, "waiting": waiting,
		"last_effective_age_ms": Time.get_ticks_msec() - last_effective_ms,
		"player_hp": Game.room.get("player", {}).get("combat", {}).get("hp"), "player_shield": Game.room.get("player", {}).get("combat", {}).get("shield"),
		"library_count": Game.room.get("player", {}).get("library_count"), "discard_count": Game.room.get("player", {}).get("discard_count"),
		"monsters": pve.get("monsters", []).map(func(monster): return {"id": monster.get("monster_id"), "hp": monster.get("hp"), "shield": monster.get("shield"), "stun_remaining_ms": monster.get("stun_remaining_ms")})})

func _close_battle_metrics(outcome: String) -> void:
	if not battle_metrics.is_empty():
		terminal_battle_ids[current_battle_id] = true
		if terminal_battle_ids.size() > 100: terminal_battle_ids.erase(terminal_battle_ids.keys()[0])
		battle_metrics["observed_ms"] = Time.get_ticks_msec() - battle_started_ms
		battle_metrics["longest_effective_gap_ms"] = maxi(int(battle_metrics.longest_effective_gap_ms), Time.get_ticks_msec() - last_effective_action_ms)
		battle_metrics["outcome"] = outcome
		_on_telemetry({"type": "battle_summary", "event_type": "battle.summary", "battle_id": current_battle_id, "metrics": battle_metrics.duplicate(true)})
	current_battle_id = ""
	battle_metrics = {}

func _on_telemetry(sample: Dictionary) -> void:
	var copy: Dictionary = sample.duplicate(true)
	# Command feedback carries its dispatch context, including late responses.
	# Never assign the current cycle to a previous cycle's completion.
	var origin: Dictionary = sample.get("_origin_context", {})
	for key in origin:
		if not copy.has(key): copy[key] = origin[key]
	for key in ["room_id", "match_id"]:
		if copy.get(key) == null:
			copy[key] = origin.get(key, Game.room.get(key, active_match_id if key == "match_id" else ""))
	event_seq += 1
	copy["run_id"] = run_id
	copy["client_id"] = client_id
	copy["process_epoch"] = process_epoch
	copy["event_seq"] = event_seq
	copy["event_type"] = sample.get("event_type", sample.get("type", "unknown"))
	copy["cycle_id"] = copy.get("cycle_id", "%s:%d" % [client_id, cycles_completed + 1])
	copy["phase"] = copy.get("phase", _current_phase())
	copy["monotonic_ms"] = Time.get_ticks_msec()
	copy["at_unix_ms"] = int(Time.get_unix_time_from_system() * 1000.0)
	if copy.get("type", "") == "http":
		operations.append(copy)
		if operations.size() > 300: operations.pop_front()
	audit_buffer.append(JSON.stringify(copy))
	if audit_buffer.size() >= 64: _flush_audit()
	telemetry.append(copy)
	if telemetry.size() > 300: telemetry.pop_front()

func _on_event(kind: String, _payload: Dictionary) -> void:
	var event_match_id := str(_payload.get("match_id", ""))
	if kind in ["match.found", "room.ready_required", "room.ready_accepted", "room.started"] and not event_match_id.is_empty():
		# Acceptance can arrive from a previous cycle while enqueue awaits its
		# response. Only the current ticket read may authorize that latch; an
		# unverified accepted hint must not suppress authoritative recovery.
		if active_match_id.is_empty() and kind != "room.ready_accepted": active_match_id = event_match_id
		if event_match_id == active_match_id:
			if kind == "room.ready_required" and not ready_accepted:
				ready_required = true
				ready_deadline_unix_ms = int(_payload.get("deadline_unix_ms", 0))
			elif kind == "room.ready_accepted" and event_match_id == verified_ready_match_id: ready_accepted = true
			elif kind == "room.started": ready_accepted = true
	if kind == "battle.combo_resolved" and str(_payload.get("attacker_id", "")) == own_user_id:
		if not battle_metrics.is_empty() and str(_payload.get("battle_id", "")) == current_battle_id:
			battle_metrics.actions += 1
			var effective := 0
			for field in ["hp_damage", "shield_damage", "heal", "shield_gain"]:
				var value := int(_payload.get(field, 0))
				battle_metrics[field] += value
				effective += value
			if effective > 0:
				battle_metrics.effective_actions += 1
				if battle_metrics.first_effective_ms == null: battle_metrics.first_effective_ms = Time.get_ticks_msec() - battle_started_ms
				battle_metrics.longest_effective_gap_ms = maxi(int(battle_metrics.longest_effective_gap_ms), Time.get_ticks_msec() - last_effective_action_ms)
				last_effective_action_ms = Time.get_ticks_msec()
				last_effective_ms = Time.get_ticks_msec()
			else: battle_metrics.zero_effective_actions += 1
			if _payload.get("battle_ended", false):
				cycle_battles_won += 1
				_close_battle_metrics("Victory")
	if kind in ["room.moved", "battle.target_selected", "settlement.ready", "match.settled"]:
		last_effective_ms = Time.get_ticks_msec()
	if kind in ["match.found", "room.ready_required", "room.ready_accepted", "room.started", "room.moved", "battle.combo_resolved", "settlement.ready", "match.settled"]:
		last_progress_ms = Time.get_ticks_msec()
		_on_telemetry({"type": "lifecycle", "event_type": kind, "match_id": _payload.get("match_id"), "room_id": _payload.get("room_id"), "_origin_context": _payload.get("_origin_context", {}), "battle_id": _payload.get("battle_id"), "request_id": _payload.get("_request_id")})
	events[kind] = int(events.get(kind, 0)) + 1
	if kind == "error.command_rejected": _on_notice("command_rejected: " + JSON.stringify(_payload))

func _on_notice(message: String) -> void:
	if message.is_empty(): return
	errors.append({"at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0), "message": message})
	if errors.size() > 100: errors.pop_front()

func _check(passed: bool, name: String) -> bool:
	if checks.size() > 200: checks.pop_front()
	checks.append({"name": name, "passed": passed, "at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0)})
	return passed

func _wait(seconds: float) -> void:
	await get_tree().create_timer(seconds).timeout

func _current_phase() -> String:
	match stage:
		"login": return "login"
		"starting", "expedition": return "initial"
		"matchmaking": return "matchmaking"
		"playing": return "playing"
		"settlement": return "settlement"
		_: return "cleanup"

func _flush_audit() -> void:
	if audit_buffer.is_empty(): return
	var path := report_path + ".telemetry.jsonl"
	var audit := FileAccess.open(path, FileAccess.READ_WRITE if FileAccess.file_exists(path) else FileAccess.WRITE)
	if audit == null:
		audit_lost_count += audit_buffer.size()
		audit_buffer.clear()
		return
	audit.seek_end()
	for line in audit_buffer: audit.store_line(line)
	audit.flush()
	if audit.get_error() != OK: audit_lost_count += audit_buffer.size()
	audit.close()
	audit_buffer.clear()

func _write_status() -> void:
	status_seq += 1
	_flush_audit()
	var status: Dictionary = {"client_id": client_id, "group": group_id, "pid": OS.get_process_id(), "started_at_unix_ms": int((Time.get_unix_time_from_system() - float(Time.get_ticks_msec() - started_at_ms) / 1000.0) * 1000.0), "now_unix_ms": int(Time.get_unix_time_from_system() * 1000.0), "online": Game.gateway.online, "socket_state": Game.gateway.socket.get_ready_state(), "room": not Game.room.is_empty(), "stage": stage, "last_progress_age_ms": Time.get_ticks_msec() - last_progress_ms, "cycles_completed": cycles_completed, "scenario_started": scenario_started, "scenario_finished": scenario_finished, "checks": checks, "operations": operations, "telemetry": telemetry, "events": events, "errors": errors}
	status.merge({"status_seq": status_seq, "run_id": run_id, "process_epoch": process_epoch, "event_seq_max": event_seq, "phase": _current_phase(), "cycle_id": "%s:%d" % [client_id, cycles_completed + 1], "audit_lost_count": audit_lost_count,
		"cleanup": cleanup_result, "hero_class": hero_profile, "strategy": strategy, "strategy_seed": strategy_seed, "load_profile": load_profile})
	status["cycle_limit_seconds"] = cycle_limit_seconds
	var file := FileAccess.open(report_path + ".status.json.tmp", FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(status))
		file.close()
		DirAccess.rename_absolute(report_path + ".status.json.tmp", report_path + ".status.json")

func _finish(ok: bool, message: String, exit_code: int = -1) -> void:
	if finished: return
	finished = true
	_flush_audit()
	var report: Dictionary = {"ok": ok, "message": message, "client_id": client_id, "group": group_id, "pid": OS.get_process_id(), "user_id": own_user_id, "started_at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0) - (Time.get_ticks_msec() - started_at_ms), "ended_at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0), "elapsed_ms": Time.get_ticks_msec() - started_at_ms, "cycles_completed": cycles_completed, "checks": checks, "operations": operations, "telemetry": telemetry, "events": events, "errors": errors}
	report.merge({"run_id": run_id, "process_epoch": process_epoch, "event_seq_max": event_seq, "audit_lost_count": audit_lost_count, "cleanup": cleanup_result, "hero_class": hero_profile, "strategy": strategy, "strategy_seed": strategy_seed, "load_profile": load_profile, "outcome": "completed" if ok else ("cancelled" if exit_code == 0 else "failed")})
	report["cycle_limit_seconds"] = cycle_limit_seconds
	var file := FileAccess.open(report_path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	_write_status()
	get_tree().quit(exit_code if exit_code >= 0 else (0 if ok else 1))
