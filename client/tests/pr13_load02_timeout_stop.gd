extends SceneTree

# Observer/coordination only: original GameStore and original load runner own all
# business requests, checks, cleanup and exit results. No replacement timeout.
class Load02Probe:
	extends "res://tests/gameplay_load_client.gd"
	var stop_observed := false
	var started_observed := false
	var first_failure: Dictionary = {}
	var completed_events: Array = []
	var entered_matches: Array = []
	var legal_terminal_actions: Array = []
	var mode := OS.get_environment("PR13_LOAD02_MODE")

	func _login() -> void:
		Game.gateway.device_id = OS.get_environment("PR13_LOAD02_DEVICE_ID")
		await Game.login(base_url, "Load02")
		var deadline := Time.get_ticks_msec() + 30000
		while Time.get_ticks_msec() < deadline and (Game.lobby.is_empty() or not Game.gateway.online) and not stop_requested:
			await _wait(0.25)
		_check(Game.gateway.online, "realtime_connected")

	func _snapshot(cutoff: String, outcome: String = "") -> Dictionary:
		var failed_checks: Array = checks.filter(func(entry): return not entry.passed)
		var started := 1 if scenario_started else 0
		var failed := 1 if not failed_checks.is_empty() or outcome == "failed" else 0
		var cancelled := 1 if started > 0 and failed == 0 and cycles_completed == 0 and outcome == "cancelled" else 0
		var pending := 1 if started > 0 and failed == 0 and cycles_completed == 0 and cancelled == 0 and not Game._settlement_ack_pending_id.is_empty() else 0
		return {"cutoff": cutoff, "monotonic_ms": Time.get_ticks_msec(), "at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0),
			"run_id": run_id, "client_id": client_id, "process_epoch": process_epoch, "cycle_id": "%s:%d" % [client_id, cycles_completed + 1],
			"pid": OS.get_process_id(), "session_generation": Game.gateway.session_generation, "room_context_epoch": Game._room_context_epoch,
			"dispatch_context": Game.gateway.capture_context(), "stage": stage, "stop_requested": stop_requested, "busy": Game.busy,
			"pending_ack": Game._settlement_ack_pending_id, "scenario_started": scenario_started, "scenario_finished": scenario_finished,
			"active_match_id": active_match_id, "checks": checks.duplicate(true), "errors": errors.duplicate(true),
			"events": events.duplicate(true), "completed_events": completed_events.duplicate(true), "cleanup": cleanup_result.duplicate(true),
			"partition": {"started": started, "completed": cycles_completed, "failed": failed, "cancelled": cancelled,
				"pending": pending, "incomplete": started - cycles_completed - failed - cancelled - pending}}

	func _write_observation(suffix: String, cutoff: String, outcome: String = "") -> void:
		var path := report_path + suffix
		var file := FileAccess.open(path + ".tmp", FileAccess.WRITE)
		if file == null:
			push_error("Cannot write owned LOAD02 observation")
			get_tree().quit(1)
			return
		file.store_string(JSON.stringify(_snapshot(cutoff, outcome), "\t"))
		file.flush()
		file.close()
		if DirAccess.rename_absolute(path + ".tmp", path) != OK:
			push_error("Cannot publish complete LOAD02 observation")
			get_tree().quit(1)

	func _process(delta: float) -> void:
		super._process(delta)
		if scenario_started and not started_observed:
			started_observed = true
			_write_observation(".started.json", "original_scenario_started")
		if stop_requested and not stop_observed:
			stop_observed = true
			_write_observation(".stop-observed.json", "original_process_observed_STOP")
		if not stop_requested and stage == "playing" and not Game.has_pending_commands():
			var action := "action.extract" if Game.allowed("action.extract") else "battle.abandon" if Game.allowed("battle.abandon") else ""
			if not action.is_empty() and Game.command(action):
				legal_terminal_actions.append({"action": action, "match_id": active_match_id, "monotonic_ms": Time.get_ticks_msec()})
				_on_telemetry({"type": "lifecycle", "event_type": "fixture.legal_terminal", "action": action, "match_id": active_match_id})

	func _check(passed: bool, name: String) -> bool:
		var result: bool = super._check(passed, name)
		if not result and first_failure.is_empty():
			first_failure = {"name": name, "monotonic_ms": Time.get_ticks_msec(), "at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0)}
			_write_observation(".first-failure.json", "original_failed_check_completed")
		return result

	func _on_event(kind: String, payload: Dictionary) -> void:
		super._on_event(kind, payload)
		if kind == "room.started" and str(payload.get("match_id", "")) not in entered_matches:
			entered_matches.append(str(payload.get("match_id", "")))

	func _on_telemetry(sample: Dictionary) -> void:
		super._on_telemetry(sample)
		if sample.get("event_type") == "cycle.completed": completed_events.append(sample.duplicate(true))

	func _finish(ok: bool, message: String, exit_code: int = -1) -> void:
		var outcome := "completed" if ok else ("cancelled" if exit_code == 0 else "failed")
		var accounting := _snapshot("same_final_cutoff_before_original_finish", outcome)
		accounting.merge({"mode": mode, "underlying_ok": ok, "underlying_message": message, "underlying_exit_argument": exit_code,
			"underlying_outcome": outcome, "first_failure": first_failure, "entered_matches": entered_matches,
			"legal_terminal_actions": legal_terminal_actions, "algorithm_version": "load02-observer-v1",
			"limitations": ["legal extraction/abandon driver; not full Boss or three gameplay routes", "partition derived from original scenario/checks/finish; no new production telemetry"]})
		FileAccess.open(report_path + ".accounting.json", FileAccess.WRITE).store_string(JSON.stringify(accounting, "\t"))
		await super._finish(ok, message, exit_code)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	root.add_child(Load02Probe.new())
