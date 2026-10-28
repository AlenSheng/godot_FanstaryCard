extends SceneTree

# Original load runner and GameStore against an owned full Program process.
# The additional driver requests an extraction only when the actual room says
# it is legal. It never replaces prepare, enqueue, READY, receipt or ACK results.
class LoadProbe:
	extends "res://tests/gameplay_load_client.gd"
	var stop_observed := false
	var completed_events: Array = []
	var entered_matches: Array = []
	var legal_extractions := 0

	func _login() -> void:
		Game.gateway.device_id = OS.get_environment("PR13_ACK_DEVICE_ID")
		await Game.login(base_url, "AckCycle")
		var deadline := Time.get_ticks_msec() + 30000
		while Time.get_ticks_msec() < deadline and (Game.lobby.is_empty() or not Game.gateway.online) and not stop_requested:
			await _wait(0.25)
		_check(Game.gateway.online, "realtime_connected")

	func _process(delta: float) -> void:
		super._process(delta)
		if stop_requested and not stop_observed:
			stop_observed = true
			FileAccess.open(stop_file + ".observed", FileAccess.WRITE).store_string(JSON.stringify({
				"stop_requested": stop_requested, "busy": Game.busy,
				"pending_ack": Game._settlement_ack_pending_id,
				"stage": stage, "cycles_completed": cycles_completed}))
		if not stop_requested and stage == "playing" and not Game.has_pending_commands() and Game.allowed("action.extract"):
			if Game.command("action.extract"):
				legal_extractions += 1
				_on_telemetry({"type": "lifecycle", "event_type": "fixture.legal_extract", "match_id": active_match_id})

	func _on_event(kind: String, payload: Dictionary) -> void:
		super._on_event(kind, payload)
		if kind == "room.started" and str(payload.get("match_id", "")) not in entered_matches:
			entered_matches.append(str(payload.get("match_id", "")))

	func _on_telemetry(sample: Dictionary) -> void:
		super._on_telemetry(sample)
		if sample.get("event_type") == "cycle.completed":
			completed_events.append({"match_id": sample.get("match_id"), "cycle_id": "%s:%d" % [client_id, cycles_completed + 1]})

	func _finish(ok: bool, message: String, exit_code: int = -1) -> void:
		var mode := OS.get_environment("PR13_ACK_FAULT_MODE")
		var expected := 3 if mode == "cycles-middle-response-loss" else 0
		var completed_matches: Array = completed_events.map(func(entry): return entry.match_id)
		var distinct: Dictionary = {}
		for match_id in completed_matches: distinct[match_id] = true
		var correct: bool = cycles_completed == expected and completed_events.size() == expected and distinct.size() == expected and cleanup_result.get("state") == "Passed"
		if expected == 3:
			correct = correct and ok and entered_matches.size() == 3 and not stop_requested
		else:
			correct = correct and stop_observed and stop_requested and not ok and exit_code == 0 and entered_matches.size() == 1
		FileAccess.open(report_path + ".accounting.json", FileAccess.WRITE).store_string(JSON.stringify({
			"ok": correct, "mode": mode, "completed": cycles_completed, "completed_events": completed_events,
			"entered_matches": entered_matches, "legal_extractions": legal_extractions,
			"stop_observed": stop_observed, "cleanup": cleanup_result,
			"underlying_ok": ok, "message": message,
			"limitations": ["original production lifecycle with an additional legal extraction driver", "no prepared Boss, combat balance, LIVE or RENDER acceptance"]}, "\t"))
		await super._finish(ok, message, exit_code)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var probe := LoadProbe.new()
	root.add_child(probe)
