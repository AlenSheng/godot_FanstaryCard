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
var audit_segment_bytes: Array[int] = []
var audit_bytes_written := 0
var audit_events_written := 0
var audit_last_error := ""
var audit_writer_failed := false
var status_seq := 0
var events: Dictionary = {}
var errors: Array = []
var own_user_id := ""
var started_process_frames := 0
var scenario_started := false
var scenario_finished := false
var Game: Node
var cycles_completed := 0
var max_cycles := 0
var stage := "starting"
var last_progress_ms := 0
var last_transport_progress_ms := 0
var last_gameplay_progress_reason := "not_started"
var last_transport_progress_reason := "not_started"
var active_match_id := ""
var verified_ready_match_id := ""
var ready_required := false
var ready_accepted := false
var ready_deadline_unix_ms := 0
var known_ready_deadlines: Dictionary = {}
var ready_attempts := 0
var ready_successful_sends := 0
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
var battle_metric_context: Dictionary = {}
var battle_suspended_ms := 0
var _suspended_pve_metrics: Dictionary = {}
var _last_authority_command_signature: Dictionary = {}
var load_profile := "cyclic-gameplay"
var hold_seconds := 600
var run_seconds := 1800
var cycle_limit_seconds := 240
var cycle_battles_won := 0
var last_effective_action_ms := 0
var _config_package_digest: Variant = null
var _config_package_checked := false

func _config_package_hash() -> Variant:
	if not _config_package_checked:
		_config_package_checked = true
		var path := "res://data/generated/fantasycard.config.bytes"
		if FileAccess.file_exists(path):
			var hash := HashingContext.new()
			hash.start(HashingContext.HASH_SHA256)
			hash.update(FileAccess.get_file_as_bytes(path))
			_config_package_digest = hash.finish().hex_encode()
	return _config_package_digest

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
	started_process_frames = Engine.get_process_frames()
	last_progress_ms = started_at_ms
	last_transport_progress_ms = started_at_ms
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
	_update_context()
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
	return seconds if seconds >= 60 and seconds <= 2400 else 0

func _process(_delta: float) -> void:
	_update_context()
	if not stop_requested and not stop_file.is_empty() and FileAccess.file_exists(stop_file):
		stop_requested = true
	if Time.get_ticks_msec() - last_status_at_ms >= 5000:
		last_status_at_ms = Time.get_ticks_msec()
		_write_status()

func _run() -> void:
	stage = "login"
	_update_context()
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
	if stop_requested:
		await _graceful_cleanup()
		await _finish(false, "Coordinator cancelled class selection", 0)
		return
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
		_on_telemetry({"type": "lifecycle", "event_type": "cycle.completed", "match_id": active_match_id, "gameplay_progress":true, "progress_reason":"cycle_acknowledged"})
		cycles_completed += 1
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
	if stop_requested: return
	_check(Game.gateway.online, "realtime_connected")

func _run_expedition() -> void:
	cycle_battles_won = 0
	_update_context()
	stage = "preparation"
	await Game.prepare("Free", 0)
	if stop_requested: return
	if not _check(not Game.preparation.is_empty(), "create_free_preparation"): return
	_on_telemetry({"type": "lifecycle", "event_type": "preparation.created",
		"preparation_id": Game.preparation.get("preparationId", ""), "gameplay_progress":true, "progress_reason":"preparation_created"})
	active_match_id = ""
	verified_ready_match_id = ""
	ready_required = false
	ready_accepted = false
	ready_deadline_unix_ms = 0
	ready_attempts = 0
	ready_successful_sends = 0
	stage = "enqueue"
	await Game.enqueue()
	if stop_requested: return
	if not _check(not Game.ticket.is_empty(), "enqueue_match"): return
	_on_telemetry({"type": "lifecycle", "event_type": "match.queued",
		"preparation_id": Game.preparation.get("preparationId", ""),
		"ticket_id": Game.ticket.get("ticketId", ""), "gameplay_progress":true, "progress_reason":"match_queued"})
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
						ready_successful_sends = 0
						ready_accepted = false
					active_match_id = verified_match_id
					ready_required = true
					ready_deadline_unix_ms = _ready_deadline_for_match(verified_match_id)
					if Game.gateway.has_method("bind_prelaunch_ticket") and str(Game.ready_prompt.get("match_id", "")) == verified_match_id:
						Game.gateway.bind_prelaunch_ticket(verified_match_id, str(Game.ready_prompt.get("room_id", "")), ready_deadline_unix_ms, int(Game.get("_room_context_epoch")))
					ready_deadline_unix_ms = _ready_deadline_for_match(verified_match_id)
					if ready_deadline_unix_ms > 0 and int(Time.get_unix_time_from_system()*1000.0) >= ready_deadline_unix_ms:
						_check(false, "ready_deadline_expired")
						return
				elif str(ticket_result.data.get("status", "")) in ["Cancelled", "Expired"]:
					_check(false, "ready_ticket_terminal")
					return
		now_ms = Time.get_ticks_msec()
		now_unix_ms = int(Time.get_unix_time_from_system() * 1000.0)
		if Game.room.is_empty() and ready_required and not active_match_id.is_empty() and active_match_id == verified_match_id and not ready_accepted and ready_attempts < 3 and now_ms >= next_ready_send_ms and (ready_deadline_unix_ms == 0 or now_unix_ms < ready_deadline_unix_ms):
			ready_attempts += 1
			var sent: bool = Game.gateway.send("room.ready")
			if sent: ready_successful_sends += 1
			_on_telemetry({"type": "lifecycle", "event_type": "room.ready.send", "match_id": active_match_id, "attempt_no": ready_attempts, "result": "sent" if sent else "send_failed"})
			if ready_attempts == 3 and ready_successful_sends == 0:
				_check(false, "ready_send_exhausted")
				return
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
			if _try_stagnation_fallback():
				await _wait(0.4)
				continue
			if _try_battle_action():
				pass
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
			"match_id": settlement_match_id, "gameplay_progress":acknowledged, "progress_reason":"settlement_acknowledged" if acknowledged else "ack_failed"})
		scenario_finished = _check(acknowledged and settlement_match_id == active_match_id and Game.room.is_empty() and Game.settlement.is_empty(), "settlement_acknowledged")

func _try_battle_action() -> bool:
	var pve: Dictionary = Game.room.get("pve", {})
	var current_dead: bool = pve.get("monsters", []).any(func(monster): return str(monster.get("monster_id", "")) == str(pve.get("current_target_id", "")) and int(monster.get("hp", 0)) <= 0)
	if current_dead and Game.allowed("battle.select_target"):
		for monster in pve.get("monsters", []):
			if int(monster.get("hp", 0)) > 0:
				Game.command("battle.select_target", {"battle_id": pve.get("battle_id", ""), "target_id": monster.get("monster_id", "")})
				break
		return true
	elif Game.allowed("battle.play_cards"):
		var hand: Array = Game.room.get("player", {}).get("hand", [])
		if not hand.is_empty():
			Game.selected_cards.clear()
			for instance_id in _select_cards(hand): Game.toggle_card(instance_id)
			Game.play_cards()
		return true
	return false

func _try_stagnation_fallback() -> bool:
	if load_profile != "cyclic-gameplay" or not Game.allowed("battle.abandon") or Time.get_ticks_msec() - last_effective_ms <= 60000:
		return false
	var origin: Dictionary = Game.gateway.capture_context()
	if Game.command("battle.abandon"):
		_on_telemetry({"type": "lifecycle", "event_type": "battle.abandon.fallback", "match_id": active_match_id,
			"battle_id": origin.get("battle_id"), "_origin_context": origin})
	# Preserve the original loop's wait/continue even if a permitted send failed.
	return true

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
		await _cancel_waiting_preparation(cleanup_generation, cleanup_cycle_match_id, cleanup_preparation_id, cleanup_ticket_id)
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
				# Bootstrap can temporarily omit a terminal receipt while its
				# asset holds are committing. Keep the local route and wait for
				# authoritative readiness within the existing cleanup deadline.
				await _wait(1.0)
				continue
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

func _cancel_waiting_preparation(generation: int, match_id: String, preparation_id: String, ticket_id: String) -> void:
	if ticket_id.is_empty():
		await Game.cancel_preparation()
		return
	# Enqueue's response remains Queued locally even after assignment. A STOP
	# must read this account's actual ticket before trying the queued-only DELETE.
	# Matched tickets keep their context until the real ready deadline/bootstrap
	# confirms release; a read failure never authorizes clearing or cancellation.
	var epoch: int = Game._room_context_epoch
	var ticket_preparation_id := str(Game.ticket.get("preparationId", ""))
	var authority: Dictionary = await Game.gateway.request("/api/v1/matches/tickets/" + ticket_id, HTTPClient.METHOD_GET, null, [0, 401, 503])
	var value: Dictionary = authority.data if authority.get("data") is Dictionary else {}
	var authoritative_match_id: Variant = value.get("matchId")
	var decision := "defer_unknown"
	var current: bool = Game.gateway.session_generation == generation and Game._room_context_epoch == epoch and active_match_id == match_id and str(Game.preparation.get("preparationId", "")) == preparation_id and str(Game.ticket.get("ticketId", "")) == ticket_id and str(Game.ticket.get("preparationId", "")) == ticket_preparation_id and Game.room.is_empty() and Game.settlement.is_empty()
	if not current:
		decision = "context_changed"
	elif authority.get("ok", false) and str(value.get("ticketId", "")) == ticket_id and not ticket_preparation_id.is_empty() and str(value.get("preparationId", "")) == ticket_preparation_id:
		if str(value.get("status", "")) in ["Queued", "Cancelled"] and (authoritative_match_id == null or (authoritative_match_id is String and authoritative_match_id.is_empty())):
			decision = "cancel_queued"
		elif str(value.get("status", "")) == "Matched" and authoritative_match_id is String and not authoritative_match_id.is_empty():
			decision = "defer_matched"
	_on_telemetry({"type": "lifecycle", "event_type": "cleanup.ticket_authority", "match_id": match_id,
		"ticket_id": ticket_id, "preparation_id": ticket_preparation_id, "session_generation": generation,
		"room_context_epoch": epoch, "http_status": authority.get("status"), "authority_status": value.get("status"),
		"authoritative_ticket_id": value.get("ticketId"), "authoritative_preparation_id": value.get("preparationId"),
		"decision": decision})
	if decision == "cancel_queued": await Game.cancel_preparation()

func _update_context() -> void:
	# A new authoritative battle is known before the local metrics tracker initializes.
	var battle: Dictionary = Game.room.get("duel", Game.room.get("pve", {}))
	var battle_id := str(battle.get("duel_id", battle.get("battle_id", "")))
	Game.gateway.telemetry_context = {"run_id": run_id, "client_id": client_id,
		"process_epoch": process_epoch, "cycle_id": "%s:%d" % [client_id, cycles_completed + 1],
		"phase": _current_phase(), "hero_class": hero_profile, "strategy": strategy,
		"load_profile": load_profile,
		"strategy_seed": strategy_seed, "config_version": Game.lobby.get("configVersion", ""),
		"config_package_sha256": _config_package_hash(),
		"config_package_unavailable_reason": "package_not_present" if _config_package_hash()==null else null,
		"battle_seed": null, "battle_seed_unavailable_reason": "not_published_by_authoritative_protocol",
		"effective_room_policy": Game.room.get("player", {}).get("numerical_state", {}).duplicate(true),
		"battle_id": battle_id}

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

func _strategy_wait_state() -> Dictionary:
	var waiting: Dictionary = Game.combat_wait_state().duplicate(true)
	var hand: Array = Game.room.get("player", {}).get("hand", [])
	if bool(waiting.get("legal_opportunity",false)) and not hand.is_empty() and _select_cards(hand).is_empty():
		waiting["reason"] = "strategy_wait"
		waiting["intentional_hold"] = true
		waiting["strategy"] = strategy
	return waiting

func _battle_metric_origin(battle_id: String) -> Dictionary:
	return {"run_id": run_id, "client_id": client_id, "process_epoch": process_epoch,
		"cycle_id": "%s:%d" % [client_id, cycles_completed + 1], "phase": _current_phase(),
		"room_id": Game.room.get("room_id", ""), "match_id": Game.room.get("match_id", active_match_id),
		"battle_id": battle_id, "battle_kind": "Pvp" if Game.room.has("duel") else "Pve"}

func _remember_terminal_battle(battle_id: String) -> void:
	terminal_battle_ids[battle_id] = true
	if terminal_battle_ids.size() > 100: terminal_battle_ids.erase(terminal_battle_ids.keys()[0])

func _emit_battle_summary(battle_id: String, metrics: Dictionary, origin: Dictionary, started_ms: int, suspended_ms: int, gap_ms: int, outcome: String, censor_reason: String = "") -> void:
	metrics["observed_ms"] = Time.get_ticks_msec() - started_ms
	metrics["observed_clock"] = "wall"
	metrics["suspended_ms"] = suspended_ms
	metrics["active_observed_ms"] = int(metrics.observed_ms) - suspended_ms
	metrics["effective_gap_clock"] = "active_excluding_suspended_pve"
	metrics["longest_effective_gap_ms"] = maxi(int(metrics.longest_effective_gap_ms), gap_ms)
	metrics["outcome"] = outcome
	if not censor_reason.is_empty(): metrics["censor_reason"] = censor_reason
	_on_telemetry({"type": "battle_summary", "event_type": "battle.summary", "battle_id": battle_id,
		"metrics": metrics.duplicate(true), "_origin_context": origin.duplicate(true)})

func _close_suspended_pve_metrics(battle_id: String, reason: String) -> void:
	var saved: Dictionary = _suspended_pve_metrics[battle_id]
	_suspended_pve_metrics.erase(battle_id)
	var paused_ms: int = Time.get_ticks_msec() - int(saved.paused_at_ms)
	_emit_battle_summary(battle_id, saved.metrics, saved.origin, int(saved.started_ms),
		int(saved.suspended_ms) + paused_ms, int(saved.gap_at_pause_ms), "Censored", reason)
	_remember_terminal_battle(battle_id)

func _discard_stale_suspended_pve_metrics() -> void:
	var current: Dictionary = _battle_metric_origin("")
	for battle_id in _suspended_pve_metrics.keys():
		var origin: Dictionary = _suspended_pve_metrics[battle_id].origin
		if ["run_id", "client_id", "process_epoch", "cycle_id", "room_id", "match_id"].any(func(key): return origin.get(key) != current.get(key)):
			_close_suspended_pve_metrics(str(battle_id), "RoomContextChangedWhileSuspended")

func _suspend_pve_metrics() -> void:
	var now := Time.get_ticks_msec()
	var gap := now - last_effective_action_ms
	battle_metrics["longest_effective_gap_ms"] = maxi(int(battle_metrics.longest_effective_gap_ms), gap)
	_suspended_pve_metrics[current_battle_id] = {"metrics": battle_metrics.duplicate(true),
		"origin": battle_metric_context.duplicate(true), "started_ms": battle_started_ms,
		"suspended_ms": battle_suspended_ms, "paused_at_ms": now, "gap_at_pause_ms": gap,
		"last_effective_ms": last_effective_ms, "last_effective_action_ms": last_effective_action_ms,
		"observed_hand_ids": observed_hand_ids.duplicate()}
	_on_telemetry({"type": "battle_lifecycle", "event_type": "battle.suspended", "trace_only": true,
		"battle_id": current_battle_id, "_origin_context": battle_metric_context.duplicate(true)})
	current_battle_id = ""
	battle_metrics = {}
	battle_metric_context = {}

func _observe_battle() -> void:
	var pve: Dictionary = Game.room.get("pve", {})
	var is_duel: bool = Game.room.has("duel")
	var battle: Dictionary = Game.room.get("duel", pve)
	var battle_id := str(battle.get("duel_id", battle.get("battle_id", "")))
	_discard_stale_suspended_pve_metrics()
	if terminal_battle_ids.has(battle_id): return
	if battle_id != current_battle_id:
		# The producer retains frozen PVE alongside the active duel. Neither its
		# identity, reset hand nor paused time belongs to the PVP observation.
		if not battle_metrics.is_empty() and is_duel and current_battle_id == str(pve.get("battle_id", "")) and battle_metric_context.get("battle_kind") == "Pve":
			_suspend_pve_metrics()
		else:
			_close_battle_metrics("PhaseChanged")
		current_battle_id = battle_id
		if battle_id.is_empty(): return
		if not is_duel and _suspended_pve_metrics.has(battle_id):
			var saved: Dictionary = _suspended_pve_metrics[battle_id]
			_suspended_pve_metrics.erase(battle_id)
			var paused_ms: int = Time.get_ticks_msec() - int(saved.paused_at_ms)
			battle_metrics = saved.metrics
			battle_metric_context = saved.origin
			battle_started_ms = int(saved.started_ms)
			battle_suspended_ms = int(saved.suspended_ms) + paused_ms
			last_effective_ms = int(saved.last_effective_ms) + paused_ms
			last_effective_action_ms = int(saved.last_effective_action_ms) + paused_ms
			observed_hand_ids = saved.observed_hand_ids
			_on_telemetry({"type": "battle_lifecycle", "event_type": "battle.resumed", "trace_only": true,
				"battle_id": battle_id, "_origin_context": battle_metric_context.duplicate(true)})
		else:
			battle_started_ms = Time.get_ticks_msec()
			battle_suspended_ms = 0
			battle_metric_context = _battle_metric_origin(battle_id)
			last_effective_ms = battle_started_ms
			last_effective_action_ms = battle_started_ms
			observed_hand_ids = Game.room.get("player", {}).get("hand", []).map(func(card): return str(card.get("instance_id", "")))
			battle_metrics = {"battle_id": battle_id, "actions": 0, "effective_actions": 0, "zero_effective_actions": 0,
				"hp_damage": 0, "shield_damage": 0, "heal": 0, "shield_gain": 0, "observed_cards_drawn": 0,
				"cards_spent":0, "heal_overflow":null, "heal_overflow_unavailable_reason":"not_published_by_authoritative_event",
				"first_effective_ms": null, "first_active_effective_ms": null, "longest_effective_gap_ms": 0}
	if battle_id.is_empty(): return
	var hand_ids: Array = Game.room.get("player", {}).get("hand", []).map(func(card): return str(card.get("instance_id", "")))
	var new_cards: int = hand_ids.filter(func(instance_id): return not observed_hand_ids.has(instance_id)).size()
	if new_cards > 0:
		battle_metrics.observed_cards_drawn += new_cards
		last_effective_ms = Time.get_ticks_msec()
		_on_telemetry({"type":"lifecycle", "event_type":"battle.cards_observed", "battle_id":battle_id,
			"new_card_instances":new_cards, "gameplay_progress":true, "progress_reason":"new_draw_opportunity"})
	observed_hand_ids = hand_ids
	var waiting: Dictionary = _strategy_wait_state()
	_on_telemetry({"type": "battle_observation", "event_type": "battle.observed", "battle_id": battle_id,
		"elapsed_ms": Time.get_ticks_msec() - battle_started_ms, "suspended_ms": battle_suspended_ms,
		"active_elapsed_ms": Time.get_ticks_msec() - battle_started_ms - battle_suspended_ms, "waiting": waiting,
		"last_effective_age_ms": Time.get_ticks_msec() - last_effective_ms,
		"player_hp": Game.room.get("player", {}).get("combat", {}).get("hp"), "player_shield": Game.room.get("player", {}).get("combat", {}).get("shield"),
		"library_count": Game.room.get("player", {}).get("library_count"), "discard_count": Game.room.get("player", {}).get("discard_count"),
		"monsters": [] if is_duel else pve.get("monsters", []).map(func(monster): return {"id": monster.get("monster_id"), "hp": monster.get("hp"), "shield": monster.get("shield"), "stun_remaining_ms": monster.get("stun_remaining_ms")})})

func _close_battle_metrics(outcome: String) -> void:
	if not battle_metrics.is_empty():
		_remember_terminal_battle(current_battle_id)
		_emit_battle_summary(current_battle_id, battle_metrics, battle_metric_context, battle_started_ms,
			battle_suspended_ms, Time.get_ticks_msec() - last_effective_action_ms, outcome)
	current_battle_id = ""
	battle_metrics = {}
	battle_metric_context = {}
	if outcome in ["Stopped", "Terminal", "Censored", "ScenarioAbandon"]:
		for battle_id in _suspended_pve_metrics.keys():
			_close_suspended_pve_metrics(str(battle_id), outcome + "WhileSuspended")

func _state_dict(value: Variant) -> Dictionary:
	return value if value is Dictionary else {}

func _command_room_state(room: Dictionary) -> Dictionary:
	var player := _state_dict(room.get("player"))
	var pve := _state_dict(room.get("pve"))
	var duel := _state_dict(room.get("duel"))
	var combat := _state_dict(player.get("combat"))
	var phase_value: Variant = player.get("phase")
	var phase: String = phase_value if phase_value is String else ""
	var pve_id := str(pve.get("battle_id", ""))
	var duel_id := str(duel.get("duel_id", ""))
	var actions: Variant = room.get("allowed_actions", [])
	return {"room_id": str(room.get("room_id", "")), "match_id": str(room.get("match_id", "")),
		"room_revision": room.get("room_revision"), "player_id": str(player.get("player_id", "")), "player_phase": phase,
		"stun_remaining_ms": player.get("stun_remaining_ms", 0), "stun_field_present": player.has("stun_remaining_ms"),
		"allowed_actions": actions.duplicate(true) if actions is Array else [], "allowed_actions_valid": actions is Array and actions.all(func(action): return action is String),
		"pve_battle_id": pve_id, "duel_id": duel_id,
		"active_battle_kind": "Duel" if phase == "Pvp" and not duel_id.is_empty() else ("Pve" if phase == "Pve" and not pve_id.is_empty() else "None"),
		"active_battle_id": duel_id if phase == "Pvp" else (pve_id if phase == "Pve" else ""),
		"player_hp": combat.get("hp"), "base_maximum_hp": combat.get("maximum_hp"), "effective_maximum_hp": combat.get("effective_maximum_hp")}

func _command_dispatch_state(sample: Dictionary) -> Dictionary:
	var state := _command_room_state(Game.room)
	var result := {"capture_site": "synchronous_command_sent_callback_after_encode", "local_snapshot": state,
		"identity_binding": "Unknown", "revision_relation": "Unknown", "battle_relation": "Unknown", "server_execution_state": "NotObserved"}
	for key in ["request_id", "run_id", "client_id", "process_epoch", "cycle_id", "room_id", "match_id", "packet_room_id", "packet_match_id"]:
		if not sample.get(key) is String or str(sample[key]).is_empty() or sample[key] == "Unknown": return result
	if sample.run_id != run_id or sample.client_id != client_id or sample.process_epoch != process_epoch or sample.cycle_id != "%s:%d" % [client_id, cycles_completed + 1]:
		result.identity_binding = "OriginMismatch"
		return result
	var current: Dictionary = Game.gateway.capture_context()
	for key in ["session_generation", "room_context_epoch"]:
		if typeof(sample.get(key)) != TYPE_INT or typeof(current.get(key)) != TYPE_INT: return result
		if sample[key] != current[key]:
			result.identity_binding = "OriginMismatch"
			return result
	if sample.room_id != state.room_id or sample.match_id != state.match_id or sample.packet_room_id != state.room_id or sample.packet_match_id != state.match_id or current.get("room_id") != state.room_id or current.get("match_id") != state.match_id or state.player_id != own_user_id:
		result.identity_binding = "RouteMismatch"
		return result
	result.identity_binding = "SameCurrentRoute"
	var sent: Variant = sample.get("packet_expected_revision")
	var observed: Variant = state.room_revision
	if typeof(sent) == TYPE_INT and typeof(observed) == TYPE_INT:
		result.revision_relation = "SameSnapshotRevision" if sent == observed else ("EarlierSnapshotRevision" if observed < sent else "LaterSnapshotRevision")
	var packet_battle := str(sample.get("packet_battle_id", ""))
	result.battle_relation = "NoBattleFieldValue" if packet_battle.is_empty() else ("SameActiveBattle" if packet_battle == state.active_battle_id else "DifferentActiveBattle")
	return result

func _observe_authority_command_state(payload: Dictionary) -> void:
	var state := _command_room_state(payload)
	var owner := _state_dict(payload.get("_receive_owner_context"))
	var origin := _state_dict(payload.get("_origin_context"))
	var current: Dictionary = {}
	var binding := "Unknown"
	if not state.room_id.is_empty() and not state.match_id.is_empty() and not state.player_id.is_empty() and not own_user_id.is_empty():
		current = Game.gateway.capture_context()
		binding = "SameCurrentRoute" if state.room_id == current.get("room_id") and state.match_id == current.get("match_id") and state.player_id == own_user_id else "RouteMismatch"
	if bool(payload.get("_replayed", false)): binding = "Replayed"
	if binding == "SameCurrentRoute":
		var physical: Dictionary = origin if not origin.is_empty() else owner
		for key in ["run_id", "client_id", "process_epoch"]:
			var expected: String = {"run_id":run_id,"client_id":client_id,"process_epoch":process_epoch}[key]
			if not physical.get(key) is String or str(physical[key]).is_empty() or physical[key] == "Unknown": binding = "Unknown"; break
			if physical[key] != expected: binding = "OriginMismatch"; break
		if not origin.is_empty():
			for key in ["session_generation", "room_context_epoch"]:
				if typeof(origin.get(key)) != TYPE_INT or origin[key] != current.get(key): binding = "OriginMismatch"; break
	var sequence: Variant = payload.get("_sequence")
	var missing: Array[String] = []
	if typeof(state.room_revision) != TYPE_INT or int(state.room_revision) < 0: missing.append("room_revision")
	if typeof(sequence) != TYPE_INT or int(sequence) < 0: missing.append("sequence")
	if state.player_phase.is_empty(): missing.append("player_phase")
	if not state.allowed_actions_valid: missing.append("allowed_actions")
	if typeof(state.stun_remaining_ms) != TYPE_INT or int(state.stun_remaining_ms) < 0: missing.append("stun_remaining_ms")
	var quality := "Complete" if missing.is_empty() else "Incomplete"
	var signature := {"room_id":state.room_id,"match_id":state.match_id,"player_id":state.player_id,"player_phase":state.player_phase,
		"pve_battle_id":state.pve_battle_id,"duel_id":state.duel_id,"stunned":typeof(state.stun_remaining_ms) == TYPE_INT and state.stun_remaining_ms > 0,
		"allowed_actions":state.allowed_actions,"session_generation":current.get("session_generation"),"room_context_epoch":current.get("room_context_epoch")}
	if binding == "SameCurrentRoute" and quality == "Complete":
		if signature == _last_authority_command_signature: return
		_last_authority_command_signature = signature.duplicate(true)
	_on_telemetry(_lifecycle_sample(payload, {"type":"authority_state", "event_type":"room.command_state_observed", "trace_only":true,
		"room_id":payload.get("room_id"), "match_id":payload.get("match_id"), "request_id":payload.get("_request_id"),
		"_origin_context":origin, "authority_state":{"snapshot":state,"identity_binding":binding,"state_evidence_quality":quality,"missing_fields":missing,"sequence":sequence,
		"event_revision":payload.get("_event_revision"),"replayed":payload.get("_replayed"),"receive_owner":owner.duplicate(true),
		"local_session_generation_at_capture":current.get("session_generation"),"local_room_context_epoch_at_capture":current.get("room_context_epoch")},
		"gameplay_progress":false}))

func _on_telemetry(sample: Dictionary) -> void:
	var copy: Dictionary = sample.duplicate(true)
	var now := Time.get_ticks_msec()
	var sample_type := str(sample.get("type", ""))
	var response_received := sample_type in ["rtt", "realtime"] or (sample_type == "http" and int(sample.get("status", 0)) > 0)
	copy["transport_progress"] = bool(sample.get("transport_progress", false)) or response_received
	copy["gameplay_progress"] = bool(sample.get("gameplay_progress", false))
	if copy.transport_progress:
		last_transport_progress_ms = now
		last_transport_progress_reason = str(sample.get("event_type", sample_type))
	if copy.gameplay_progress:
		last_progress_ms = now
		last_gameplay_progress_reason = str(sample.get("progress_reason", sample.get("event_type", "unknown")))
	copy["gameplay_progress_reason"] = last_gameplay_progress_reason
	copy["transport_progress_age_ms"] = maxi(0, now - last_transport_progress_ms)
	copy["gameplay_progress_age_ms"] = maxi(0, now - last_progress_ms)
	# Command feedback carries its dispatch context, including late responses.
	# Never assign the current cycle to a previous cycle's completion.
	var origin_value: Variant = sample.get("_origin_context", {})
	var origin: Dictionary = origin_value if origin_value is Dictionary else {}
	for key in origin:
		if not copy.has(key) or copy[key] == null: copy[key] = origin[key]
	var asynchronous := sample_type in ["http", "http_attempt", "realtime", "realtime_timeout", "rtt", "command_lifecycle", "lifecycle_guard", "protocol_observation"] or sample.has("_origin_context")
	var local_context := {"run_id": run_id, "client_id": client_id, "process_epoch": process_epoch,
		"cycle_id": "%s:%d" % [client_id, cycles_completed + 1], "phase": _current_phase(),
		"room_id": Game.room.get("room_id", ""), "match_id": Game.room.get("match_id", active_match_id)}
	var context_keys: Array[String] = ["run_id", "client_id", "process_epoch", "cycle_id", "phase", "room_id", "match_id"]
	if sample_type in ["http", "http_attempt"]: context_keys.append("logical_request_id")
	var missing_fields: Array[String] = []
	for key in context_keys:
		var value: Variant = copy.get(key)
		var absent: bool = not value is String or value == "Unknown" or (key not in ["room_id", "match_id"] and value.is_empty())
		if not absent: continue
		if asynchronous:
			copy[key] = "Unknown"
			missing_fields.append(key)
		elif local_context.has(key):
			copy[key] = local_context[key]
	# The observer owns storage/sequence; the business identity belongs to
	# the dispatch. Missing asynchronous context must never borrow this frame.
	copy["observer_context"] = local_context
	copy["origin_context_state"] = ("Complete" if missing_fields.is_empty() else "Unknown") if asynchronous else "Local"
	copy["origin_context_missing_fields"] = missing_fields
	copy["observation_phase"] = "drain" if stop_requested or finishing else "active"
	event_seq += 1
	copy["event_seq"] = event_seq
	copy["event_type"] = sample.get("event_type", sample.get("type", "unknown"))
	if sample_type == "command_lifecycle" and copy.event_type == "command.sent":
		copy["dispatch_state"] = _command_dispatch_state(copy)
	copy["monotonic_ms"] = Time.get_ticks_msec()
	copy["at_unix_ms"] = int(Time.get_unix_time_from_system() * 1000.0)
	if not copy.has("battle_seed"):
		copy["battle_seed"] = null
		copy["battle_seed_unavailable_reason"] = "not_published_by_authoritative_protocol"
	var serialized := JSON.stringify(copy)
	if serialized.to_utf8_buffer().size() + 1 > _audit_record_limit_bytes():
		audit_lost_count += 1
		audit_last_error = "record_size_limit"
		return
	if copy.get("type", "") == "http":
		operations.append(copy)
		if operations.size() > 300: operations.pop_front()
	audit_buffer.append(serialized)
	if audit_buffer.size() >= 64: _flush_audit()
	telemetry.append(copy)
	if telemetry.size() > 300: telemetry.pop_front()

func _lifecycle_sample(payload: Dictionary, sample: Dictionary) -> Dictionary:
	# An unsolicited push has no client dispatch. Keep its business origin
	# Unknown while retaining the owner captured at the Gateway receive site.
	if not payload.has("_origin_context"):
		var owner_value: Variant = payload.get("_receive_owner_context", {})
		if owner_value is Dictionary:
			for key in ["run_id", "client_id", "process_epoch"]:
				if owner_value.has(key): sample[key] = owner_value[key]
			sample["context_capture_kind"] = "uncorrelated_receive"
			sample["record_owner_source"] = "gateway_receive"
	return sample

func _on_event(kind: String, _payload: Dictionary) -> void:
	last_transport_progress_ms = Time.get_ticks_msec()
	last_transport_progress_reason = kind
	if kind == "room.snapshot": _observe_authority_command_state(_payload)
	var effective_combo := false
	var event_match_id := str(_payload.get("match_id", ""))
	if kind in ["match.found", "room.ready_required", "room.ready_accepted"] and not event_match_id.is_empty():
		_remember_ready_deadline(event_match_id, int(_payload.get("deadline_unix_ms", 0)))
	if kind in ["match.found", "room.ready_required", "room.ready_accepted", "room.started"] and not event_match_id.is_empty():
		# Acceptance can arrive from a previous cycle while enqueue awaits its
		# response. Only the current ticket read may authorize that latch; an
		# unverified accepted hint must not suppress authoritative recovery.
		if active_match_id.is_empty() and kind != "room.ready_accepted": active_match_id = event_match_id
		if event_match_id == active_match_id:
			if kind == "room.ready_required" and not ready_accepted:
				ready_required = true
				ready_deadline_unix_ms = _ready_deadline_for_match(event_match_id)
			elif kind == "room.ready_accepted" and event_match_id == verified_ready_match_id: ready_accepted = true
			elif kind == "room.started": ready_accepted = true
	if kind == "battle.combo_resolved" and str(_payload.get("attacker_id", "")) == own_user_id:
		if not battle_metrics.is_empty() and str(_payload.get("battle_id", "")) == current_battle_id:
			battle_metrics.actions += 1
			battle_metrics.cards_spent += _payload.get("card_instance_ids",[]).size()
			var effective := 0
			for field in ["hp_damage", "shield_damage", "heal", "shield_gain"]:
				var value := int(_payload.get(field, 0))
				battle_metrics[field] += value
				effective += value
			if effective > 0:
				effective_combo = true
				battle_metrics.effective_actions += 1
				if battle_metrics.first_effective_ms == null:
					battle_metrics.first_effective_ms = Time.get_ticks_msec() - battle_started_ms
					battle_metrics.first_active_effective_ms = int(battle_metrics.first_effective_ms) - battle_suspended_ms
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
		var advances := effective_combo if kind == "battle.combo_resolved" else kind in ["room.started", "room.moved", "settlement.ready", "match.settled"] or (kind == "room.ready_accepted" and ready_accepted and event_match_id == verified_ready_match_id)
		_on_telemetry(_lifecycle_sample(_payload, {"type": "lifecycle", "event_type": kind, "match_id": _payload.get("match_id"), "room_id": _payload.get("room_id"), "_origin_context": _payload.get("_origin_context", {}), "battle_id": _payload.get("battle_id"), "request_id": _payload.get("_request_id"),
			"transport_progress":true, "gameplay_progress":advances, "progress_reason":"effective_combo" if effective_combo else kind}))
	if kind in ["player.died", "action.extract_completed"]:
		# Preserve terminal authority separately from progress clocks. A command
		# can already be in flight when this packet reaches a distant client.
		# Missing wire room/match IDs remain explicit rather than inferred proof.
		_on_telemetry(_lifecycle_sample(_payload, {"type": "lifecycle", "event_type": kind, "match_id": _payload.get("match_id"), "room_id": _payload.get("room_id"),
			"wire_match_id_present": _payload.has("match_id"), "wire_room_id_present": _payload.has("room_id"),
			"player_id": _payload.get("player_id"), "own_player_id": own_user_id, "status": _payload.get("status"), "duel_id": _payload.get("duel_id"),
			"_sequence": _payload.get("_sequence"), "_event_revision": _payload.get("_event_revision"), "_replayed": _payload.get("_replayed"),
			"_origin_context": _payload.get("_origin_context", {}), "request_id": _payload.get("_request_id")}))
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
		"starting", "expedition", "preparation", "enqueue": return "initial"
		"matchmaking": return "matchmaking"
		"playing": return "playing"
		"settlement": return "settlement"
		_: return "cleanup"

func _audit_segment_limit_bytes() -> int:
	return 16 * 1024 * 1024

func _audit_record_limit_bytes() -> int:
	return 64 * 1024

func _audit_max_segments() -> int:
	return 8

func _audit_segment_path(index: int) -> String:
	return report_path + ".telemetry" + ("" if index == 0 else "." + str(index)) + ".jsonl"

func _audit_storage_observation() -> Dictionary:
	var pending_bytes := 0
	for line in audit_buffer: pending_bytes += line.to_utf8_buffer().size() + 1
	return {"version":1, "record_limit_bytes":_audit_record_limit_bytes(), "segment_limit_bytes":_audit_segment_limit_bytes(),
		"max_segments":_audit_max_segments(), "segment_count":audit_segment_bytes.size(), "segment_bytes":audit_segment_bytes.duplicate(),
		"bytes_written":audit_bytes_written, "events_written":audit_events_written,
		"buffer_count":audit_buffer.size(), "buffer_serialized_bytes":pending_bytes, "last_error":audit_last_error}

func _flush_audit() -> void:
	if audit_buffer.is_empty(): return
	if audit_writer_failed:
		audit_lost_count += audit_buffer.size()
		audit_buffer.clear()
		return
	var completed := 0
	var unflushed := 0
	var audit: FileAccess = null
	for line in audit_buffer:
		var raw := (line + "\n").to_utf8_buffer()
		if raw.size() > _audit_record_limit_bytes() or raw.size() > _audit_segment_limit_bytes():
			audit_last_error = "record_size_limit"
			audit_lost_count += 1
			completed += 1
			continue
		if audit_segment_bytes.is_empty(): audit_segment_bytes.append(0)
		var index := audit_segment_bytes.size() - 1
		if int(audit_segment_bytes[index]) + raw.size() > _audit_segment_limit_bytes():
			if audit != null:
				audit.flush()
				if audit.get_error() != OK:
					audit_last_error = "flush_failed"
					audit_lost_count += audit_buffer.size() - completed + unflushed
					audit_writer_failed = true
					audit.close()
					audit_buffer.clear()
					return
				audit.close()
				audit = null
				unflushed = 0
			if audit_segment_bytes.size() >= _audit_max_segments():
				audit_last_error = "archive_size_limit"
				audit_lost_count += audit_buffer.size() - completed
				audit_writer_failed = true
				break
			audit_segment_bytes.append(0)
			index += 1
		if audit == null:
			var path := _audit_segment_path(index)
			audit = FileAccess.open(path, FileAccess.READ_WRITE if FileAccess.file_exists(path) else FileAccess.WRITE)
			if audit == null:
				audit_last_error = "open_failed"
				audit_lost_count += audit_buffer.size() - completed
				break
			if audit.get_length() != int(audit_segment_bytes[index]):
				audit_last_error = "unexpected_existing_bytes"
				audit_lost_count += audit_buffer.size() - completed
				audit_writer_failed = true
				break
			audit.seek_end()
		audit.store_buffer(raw)
		if audit.get_error() != OK:
			audit_last_error = "write_failed"
			audit_lost_count += audit_buffer.size() - completed
			audit_writer_failed = true
			break
		audit_segment_bytes[index] += raw.size()
		audit_bytes_written += raw.size()
		audit_events_written += 1
		unflushed += 1
		completed += 1
	if audit != null:
		audit.flush()
		if audit.get_error() != OK:
			audit_last_error = "flush_failed"
			audit_lost_count += unflushed
			audit_writer_failed = true
		audit.close()
	audit_buffer.clear()

func _frame_clock_observation() -> Dictionary:
	var observed_ms := maxi(0, Time.get_ticks_msec() - started_at_ms)
	var frames := maxi(0, Engine.get_process_frames() - started_process_frames)
	return {"process_frames": frames, "observed_ms": observed_ms,
		"mean_process_fps": float(frames) * 1000.0 / float(observed_ms) if observed_ms > 0 else null,
		"engine_max_fps": Engine.max_fps, "clock": "local Time.get_ticks_msec",
		"scope": "SceneTree process frames, including headless; not rendered FPS or network packet rate"}

func _write_status() -> void:
	status_seq += 1
	_flush_audit()
	var status: Dictionary = {"client_id": client_id, "group": group_id, "pid": OS.get_process_id(), "started_at_unix_ms": int((Time.get_unix_time_from_system() - float(Time.get_ticks_msec() - started_at_ms) / 1000.0) * 1000.0), "now_unix_ms": int(Time.get_unix_time_from_system() * 1000.0), "online": Game.gateway.online, "socket_state": Game.gateway.socket.get_ready_state(), "room": not Game.room.is_empty(), "stage": stage, "last_progress_age_ms": Time.get_ticks_msec() - last_progress_ms, "cycles_completed": cycles_completed, "scenario_started": scenario_started, "scenario_finished": scenario_finished, "checks": checks, "operations": operations, "telemetry": telemetry, "events": events, "errors": errors}
	status.merge({"status_seq": status_seq, "run_id": run_id, "process_epoch": process_epoch, "event_seq_max": event_seq, "phase": _current_phase(), "cycle_id": "%s:%d" % [client_id, cycles_completed + 1], "audit_lost_count": audit_lost_count,
		"cleanup": cleanup_result, "hero_class": hero_profile, "strategy": strategy, "strategy_seed": strategy_seed, "load_profile": load_profile})
	status["audit_storage"] = _audit_storage_observation()
	status["generator_frame_clock"] = _frame_clock_observation()
	status["transport_progress_age_ms"] = maxi(0, Time.get_ticks_msec() - last_transport_progress_ms)
	status["gameplay_progress_age_ms"] = maxi(0, Time.get_ticks_msec() - last_progress_ms)
	status["gameplay_progress_reason"] = last_gameplay_progress_reason
	status["transport_progress_reason"] = last_transport_progress_reason
	status["waiting_stage"] = _progress_waiting_stage()
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
	report["audit_storage"] = _audit_storage_observation()
	report["generator_frame_clock"] = _frame_clock_observation()
	report["cycle_limit_seconds"] = cycle_limit_seconds
	report["transport_progress_age_ms"] = maxi(0, Time.get_ticks_msec() - last_transport_progress_ms)
	report["gameplay_progress_age_ms"] = maxi(0, Time.get_ticks_msec() - last_progress_ms)
	report["gameplay_progress_reason"] = last_gameplay_progress_reason
	report["transport_progress_reason"] = last_transport_progress_reason
	report["waiting_stage"] = _progress_waiting_stage()
	var file := FileAccess.open(report_path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	_write_status()
	get_tree().quit(exit_code if exit_code >= 0 else (0 if ok else 1))

func _progress_waiting_stage() -> String:
	if stage == "settlement": return "settlement_acknowledgement"
	if stage == "matchmaking":
		return "started" if ready_accepted else "ready_acceptance" if ready_successful_sends > 0 else "ticket_authority"
	if stage == "playing":
		if not Game.settlement.is_empty(): return "settlement_acknowledgement"
		if Game.has_pending_commands(): return "command_confirmation"
		if not Game.room.get("pve", Game.room.get("duel", {})).is_empty(): return str(_strategy_wait_state().get("reason", "battle"))
	return stage

func _remember_ready_deadline(match_id: String, deadline_ms: int) -> void:
	if match_id.is_empty() or deadline_ms <= 0: return
	# Preserve the first authoritative deadline even after ready_removed clears
	# the UI hint. A late callback cannot extend this match's known lifetime.
	known_ready_deadlines[match_id] = mini(int(known_ready_deadlines.get(match_id, deadline_ms)), deadline_ms)
	while known_ready_deadlines.size() > 8: known_ready_deadlines.erase(known_ready_deadlines.keys()[0])

func _ready_deadline_for_match(match_id: String) -> int:
	if str(Game.ready_prompt.get("match_id", "")) == match_id:
		_remember_ready_deadline(match_id, int(Game.ready_prompt.get("deadline_unix_ms", 0)))
	return int(known_ready_deadlines.get(match_id, 0))
