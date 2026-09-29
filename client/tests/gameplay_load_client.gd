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
var ready_required := false
var ready_accepted := false
var ready_deadline_unix_ms := 0
var ready_attempts := 0

func _ready() -> void:
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
	DirAccess.make_dir_recursive_absolute(report_path.get_base_dir())
	Game.gateway.persist_session = false
	Game.gateway.device_id = "load-%s-%s" % [client_id, Game.gateway.new_id()]
	Game.gateway.last_sequence = 0
	Game.gateway.room_id = ""
	Game.gateway.room_revision = 0
	Game.notice.connect(_on_notice)
	Game.gateway.failed.connect(_on_notice)
	Game.gateway.event_received.connect(_on_event)
	Game.network_telemetry.connect(_on_telemetry)
	call_deferred("_run")

func _process(_delta: float) -> void:
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
	await Game.prepare("Free", 0)
	if stop_requested: return
	if not _check(not Game.preparation.is_empty(), "create_free_preparation"): return
	_on_telemetry({"type": "lifecycle", "event_type": "preparation.created",
		"preparation_id": Game.preparation.get("preparationId", "")})
	active_match_id = ""
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
	while not ready_required and Game.room.is_empty() and Time.get_ticks_msec() < deadline and not stop_requested:
		await _wait(0.25)
	if stop_requested: return
	var next_ready_send_ms := 0
	var next_verify_ms := 0
	var verified_match_id := ""
	deadline = Time.get_ticks_msec() + 30000
	while Game.room.is_empty() and Time.get_ticks_msec() < deadline and not stop_requested:
		var now_ms := Time.get_ticks_msec()
		var now_unix_ms := int(Time.get_unix_time_from_system() * 1000.0)
		if ready_required and active_match_id != verified_match_id and now_ms >= next_verify_ms:
			var ticket_id := str(Game.ticket.get("ticketId", ""))
			if ticket_id.is_empty():
				_check(false, "ready_ticket_missing")
				return
			var ticket_result: Dictionary = await Game.gateway.request("/api/v1/matches/tickets/" + ticket_id)
			if stop_requested: return
			next_verify_ms = Time.get_ticks_msec() + 2000
			if ticket_result.ok and ticket_result.data is Dictionary:
				verified_match_id = str(ticket_result.data.get("matchId", ""))
				if verified_match_id != active_match_id:
					active_match_id = verified_match_id
					ready_required = not verified_match_id.is_empty() and str(Game.ready_prompt.get("match_id", "")) == verified_match_id
					ready_accepted = false
					ready_deadline_unix_ms = int(Game.ready_prompt.get("deadline_unix_ms", 0)) if ready_required else 0
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
	deadline = Time.get_ticks_msec() + 240000
	var visited := {}
	while Game.settlement.is_empty() and Time.get_ticks_msec() < deadline and not stop_requested:
		if not Game.room.is_empty() and not Game.has_pending_commands():
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
					for card in hand: Game.toggle_card(str(card.get("instance_id", "")))
					Game.play_cards()
			elif Game.allowed("reward.choice.claim"):
				var options: Array = Game.room.get("reward_choice", {}).get("options", [])
				if not options.is_empty(): Game.command("reward.choice.claim", {"option_id": options[-1].get("option_id", "")})
			elif Game.allowed("monster.choose"):
				var pending: Array = Game.room.get("player", {}).get("monster_pool", {}).get("pending", [])
				if not pending.is_empty(): Game.command("monster.choose", {"candidate_id": pending[0].get("instance_id", ""), "accept": false})
			elif Game.allowed("action.extract") and not visited.is_empty():
				Game.command("action.extract")
			elif Game.allowed("action.spring"):
				Game.command("action.spring")
			elif Game.allowed("room.move"):
				var moves: Array = Game.room.get("legal_moves", []).duplicate()
				if not moves.is_empty():
					moves.shuffle()
					var move: Dictionary = moves[0]
					for candidate in moves:
						if not visited.has(str(candidate.get("row", 0)) + ":" + str(candidate.get("column", 0))):
							move = candidate
							break
					var move_key: String = str(move.get("row", 0)) + ":" + str(move.get("column", 0))
					visited[move_key] = true
					Game.command("room.move", move)
		await _wait(0.4)
	if stop_requested: return
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

func _graceful_cleanup() -> void:
	stage = "cleanup"
	if stop_requested:
		Game.gateway.reconnect_enabled = false
		Game.gateway.socket.close()
		return
	if not Game.settlement.is_empty():
		await Game.acknowledge_settlement()
	elif not Game.room.is_empty() and Game.allowed("action.extract"):
		Game.command("action.extract")
		await _wait(5.0)
		if not Game.settlement.is_empty(): await Game.acknowledge_settlement()
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()

func _on_telemetry(sample: Dictionary) -> void:
	var copy: Dictionary = sample.duplicate(true)
	event_seq += 1
	copy["run_id"] = run_id
	copy["client_id"] = client_id
	copy["process_epoch"] = process_epoch
	copy["event_seq"] = event_seq
	copy["event_type"] = sample.get("event_type", sample.get("type", "unknown"))
	copy["cycle_id"] = "%s:%d" % [client_id, cycles_completed + 1]
	copy["phase"] = _current_phase()
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
		if active_match_id.is_empty(): active_match_id = event_match_id
		if event_match_id == active_match_id:
			if kind == "room.ready_required" and not ready_accepted:
				ready_required = true
				ready_deadline_unix_ms = int(_payload.get("deadline_unix_ms", 0))
			elif kind == "room.ready_accepted": ready_accepted = true
			elif kind == "room.started": ready_accepted = true
	if kind in ["match.found", "room.ready_required", "room.ready_accepted", "room.started", "room.moved", "battle.combo_resolved", "settlement.ready", "match.settled"]:
		last_progress_ms = Time.get_ticks_msec()
		_on_telemetry({"type": "lifecycle", "event_type": kind, "match_id": _payload.get("match_id"), "room_id": _payload.get("room_id")})
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
	_flush_audit()
	var status: Dictionary = {"client_id": client_id, "group": group_id, "pid": OS.get_process_id(), "started_at_unix_ms": int((Time.get_unix_time_from_system() - float(Time.get_ticks_msec() - started_at_ms) / 1000.0) * 1000.0), "now_unix_ms": int(Time.get_unix_time_from_system() * 1000.0), "online": Game.gateway.online, "socket_state": Game.gateway.socket.get_ready_state(), "room": not Game.room.is_empty(), "stage": stage, "last_progress_age_ms": Time.get_ticks_msec() - last_progress_ms, "cycles_completed": cycles_completed, "scenario_started": scenario_started, "scenario_finished": scenario_finished, "checks": checks, "operations": operations, "telemetry": telemetry, "events": events, "errors": errors}
	status.merge({"run_id": run_id, "process_epoch": process_epoch, "event_seq_max": event_seq, "phase": _current_phase(), "cycle_id": "%s:%d" % [client_id, cycles_completed + 1], "audit_lost_count": audit_lost_count})
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
	report.merge({"run_id": run_id, "process_epoch": process_epoch, "event_seq_max": event_seq, "audit_lost_count": audit_lost_count, "outcome": "completed" if ok else ("cancelled" if exit_code == 0 else "failed")})
	var file := FileAccess.open(report_path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	_write_status()
	get_tree().quit(exit_code if exit_code >= 0 else (0 if ok else 1))
