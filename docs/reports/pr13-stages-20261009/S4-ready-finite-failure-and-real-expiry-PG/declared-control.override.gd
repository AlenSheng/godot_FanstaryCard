extends SceneTree

## OFFLINE/POSTGRES: production Game, gateway and load loop against full Program.
## Only transport delivery and coordinator STOP-file timing are controlled here.
const ProductionGateway = preload("res://network/gateway.gd")
const ProductionLoad = preload("res://tests/gameplay_load_client.gd")

class FaultGateway extends ProductionGateway:
	var probe: Node
	var trace: Array = []
	var required_seen := false
	var required_dropped := false
	var required_delivered := 0
	var connected_count := 0
	var ticket_reads := 0
	var ticket_inflight := false
	var held_required := PackedByteArray()
	var ready_send_count := 0
	var ready_send_after_stop := 0
	var duplicate_deliveries := 0
	var synthetic_sequence := 0
	var expected_room_id := ""
	var expected_match_id := ""
	var resume_send_count := 0
	var actual_deadline_unix_ms := 0
	var matched_reply_held := false
	const STALE_MATCH_ID := "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"

	func record(kind: String, extra: Dictionary = {}) -> void:
		var entry := {"event": kind, "at_ms": Time.get_ticks_msec()}
		entry.merge(extra)
		trace.append(entry)

	func request(path: String, method: int = HTTPClient.METHOD_GET, data: Variant = null, quiet_statuses: Array = []) -> Dictionary:
		var request_read_no := 0
		var is_ticket_read := path.begins_with("/api/v1/matches/tickets/") and method == HTTPClient.METHOD_GET
		if is_ticket_read:
			ticket_inflight = true
			ticket_reads += 1
			request_read_no = ticket_reads
		var result: Dictionary = await super.request(path, method, data, quiet_statuses)
		if method == HTTPClient.METHOD_POST and path == "/api/v1/preparations" and probe.case_name == "stop_prepare_await":
			probe.request_stop("prepare_response_held")
			await get_tree().create_timer(0.2).timeout
		if method == HTTPClient.METHOD_POST and path == "/api/v1/matches/enqueue":
			if probe.case_name == "stop_enqueue_await":
				probe.request_stop("enqueue_response_held")
				await get_tree().create_timer(0.2).timeout
			elif probe.case_name == "stop_ready_enqueue_await":
				var deadline := Time.get_ticks_msec() + 40000
				while not required_seen and Time.get_ticks_msec() < deadline:
					await get_tree().process_frame
				probe.request_stop("ready_during_enqueue_await")
				await get_tree().create_timer(0.2).timeout
			elif probe.case_name == "late_accepted_before_ticket":
				# Deliberately synthetic wire input; this case is SupportOnly.
				# It runs the real decoder/event entry, never assigns recovery flags.
				var codec := Proto.new()
				var payload: PackedByteArray = codec.encode("RoomReadyAcceptedEvent", {"match_id": STALE_MATCH_ID, "room_id": "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"})
				synthetic_sequence = last_sequence + 1
				var wire: PackedByteArray = codec.encode("ServerEnvelope", {"protocol_version": 1, "type": "room.ready_accepted", "sequence": synthetic_sequence, "payload": payload})
				record("synthetic_old_cycle_packet", {"support_only": true})
				super._receive(wire)
		if is_ticket_read and probe.case_name == "matched_reply_after_actual_deadline" and result.get("data") is Dictionary and str(result.data.get("status", "")) == "Matched":
			matched_reply_held = true
			var observed_wait_limit := Time.get_ticks_msec() + 20000
			while actual_deadline_unix_ms == 0 and Time.get_ticks_msec() < observed_wait_limit:
				await get_tree().process_frame
			var file := FileAccess.open(probe.report_path.get_base_dir().path_join("held-real-matched-response-read-%d.original.json" % request_read_no), FileAccess.WRITE)
			file.store_string(JSON.stringify(result))
			file.close()
			record("real_matched_response_held", {"request_read_no": request_read_no, "actual_deadline_unix_ms": actual_deadline_unix_ms, "observed_unix_ms": int(Time.get_unix_time_from_system()*1000.0), "ready_sends": ready_send_count})
			while actual_deadline_unix_ms > 0 and int(Time.get_unix_time_from_system()*1000.0) <= actual_deadline_unix_ms + 150 and Time.get_ticks_msec() < observed_wait_limit:
				await get_tree().create_timer(0.1).timeout
			record("real_matched_response_delivered_after_deadline", {"request_read_no": request_read_no, "actual_deadline_unix_ms": actual_deadline_unix_ms, "observed_unix_ms": int(Time.get_unix_time_from_system()*1000.0), "ready_sends": ready_send_count, "returned_status": result.data.get("status", "")})
		if is_ticket_read:
			record("ticket_response", {"status": result.get("data", {}).get("status", "") if result.get("data") is Dictionary else "", "read_no": request_read_no})
			if probe.case_name == "stop_ticket_await" and ticket_reads == 1:
				probe.request_stop("ticket_response_held")
				await get_tree().create_timer(0.2).timeout
			ticket_inflight = false
		return result

	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		if kind == "session.resume":
			resume_send_count += 1
			record("session.resume.attempt", payload)
		if kind == "room.ready":
			ready_send_count += 1
			if probe.stop_requested: ready_send_after_stop += 1
			record("room.ready.attempt", {"online": online, "after_stop": probe.stop_requested})
			if probe.case_name == "all_three_sends_false":
				record("controlled_all_send_false", {"attempt": ready_send_count, "socket_write_performed": false})
				return false
			if probe.case_name == "send_false_twice_then_success" and ready_send_count <= 2:
				record("controlled_send_false", {"attempt": ready_send_count, "socket_write_performed": false})
				return false
			# Preserve the original server packet for an actual late duplicate.
			if probe.case_name == "late_required_duplicate" and not held_required.is_empty():
				call_deferred("deliver_late_required")
		return super.send(kind, payload, request_id)

	func deliver_late_required() -> void:
		await get_tree().create_timer(0.5).timeout
		if held_required.is_empty(): return
		var packet := held_required
		held_required = PackedByteArray()
		super._receive(packet)
		super._receive(packet)
		duplicate_deliveries += 2
		record("late_required_duplicate_delivered")

	func _receive(packet: PackedByteArray) -> void:
		var codec := Proto.new()
		var envelope: Dictionary = codec.decode("ServerEnvelope", packet)
		var kind := str(envelope.get("type", ""))
		if kind in ["match.found", "room.ready_required", "room.ready_accepted", "room.started", "room.snapshot", "room.ready_removed"]:
			var schema: String = EVENTS.get(kind, "")
			var actual: Dictionary = codec.decode(schema, envelope.get("payload", PackedByteArray()))
			record("actual_server_envelope", {"kind": kind, "sequence": envelope.get("sequence", 0),
				"match_id": actual.get("match_id", ""), "room_id": actual.get("room_id", ""), "sequence_before": last_sequence})
			if kind in ["match.found", "room.ready_required"] and expected_match_id.is_empty():
				expected_match_id = str(actual.get("match_id", ""))
				expected_room_id = str(actual.get("room_id", ""))
		if probe.case_name == "matched_reply_after_actual_deadline" and kind in ["match.found", "room.ready_required"]:
			var authority: Dictionary = codec.decode(EVENTS[kind], envelope.get("payload", PackedByteArray()))
			actual_deadline_unix_ms = maxi(actual_deadline_unix_ms, int(authority.get("deadline_unix_ms", 0)))
		if kind == "session.connected": connected_count += 1
		if kind == "room.ready_required":
			required_seen = true
			record("required_transport_boundary", {"ticket_inflight": ticket_inflight})
			if probe.case_name == "required_lost_reconnect" and not required_dropped:
				required_dropped = true
				record("required_dropped_disconnect", {"sequence_before": last_sequence})
				socket.close()
				return
			if probe.case_name == "late_required_duplicate" and not required_dropped:
				required_dropped = true
				held_required = packet.duplicate()
				return
			required_delivered += 1
		super._receive(packet)
		if kind == "room.ready_required" and probe.case_name == "stop_ready_before_send":
			probe.request_stop("ready_before_send")

class LoadProbe extends ProductionLoad:
	var case_name := ""
	var stop_boundary := ""
	var observed_room_id := ""
	var observed_match_id := ""
	var observed_room_checks := false
	var case_passed := false
	var probe_gateway: Node
	var late_guard_started := 0

	func _ready() -> void:
		case_name = OS.get_environment("FANTASYCARD_READY_STOP_CASE")
		print("READY_PROBE ready " + case_name)
		super._ready()

	func _login() -> void:
		await super._login()
		if Game.lobby.is_empty() or not Game.gateway.online: return
		var work := report_path.get_base_dir()
		var fixture_request := FileAccess.open(work.path_join("fixture-login.json"), FileAccess.WRITE)
		fixture_request.store_string(JSON.stringify({"player_id": Game.lobby.get("player", {}).get("userId", "")}))
		fixture_request.close()
		var fixture_deadline := Time.get_ticks_msec() + 10000
		while not FileAccess.file_exists(work.path_join("fixture-seeded.json")) and Time.get_ticks_msec() < fixture_deadline:
			await get_tree().process_frame
		_check(FileAccess.file_exists(work.path_join("fixture-seeded.json")), "owned_equipment_fixture_seeded")
		# Consume the seeded loadout using the real response entry, never prefill
		# internal preparation, ticket, READY or recovery state.
		await Game.refresh_lobby()

	func request_stop(boundary: String) -> void:
		if not stop_boundary.is_empty(): return
		stop_boundary = boundary
		probe_gateway.record("coordinator_stop", {"boundary": boundary})
		var file := FileAccess.open(stop_file, FileAccess.WRITE)
		file.store_string("STOP\n")
		file.close()

	func _process(delta: float) -> void:
		super._process(delta)
		if finishing or finished: return
		if not Game.room.is_empty() and observed_room_id.is_empty():
			observed_room_id = str(Game.room.get("room_id", ""))
			observed_match_id = str(Game.room.get("match_id", ""))
		if case_name == "stop_queue_wait" and probe_gateway.ticket_reads > 0 and Game.room.is_empty(): request_stop("queued_wait")
		if not Game.room.is_empty() and stage == "playing":
			observed_room_checks = checks.any(func(item): return item.name == "room_started" and item.passed)
			if case_name in ["normal_ready", "required_lost_reconnect", "late_required_duplicate", "send_false_twice_then_success"]: request_stop("room_started_then_stop")
			if case_name in ["ready_required_all_lost_ticket", "ready_started_all_lost_snapshot", "ready_accepted_lost_resume", "ready_started_lost_reconnect", "ready_replies_lost_reconnect", "ready_send_lost_reconnect"]:
				request_stop("authority_recovered_room_started_then_stop")
		if case_name == "ready_send_all_lost_stop" and FileAccess.file_exists(report_path.get_base_dir().path_join("transport/request-stop.json")):
			request_stop("three_actual_ready_frames_dropped")
		if case_name == "late_accepted_before_ticket" and not Game.ticket.is_empty():
			if late_guard_started == 0: late_guard_started = Time.get_ticks_msec()
			if Time.get_ticks_msec() - late_guard_started >= 3500:
				request_stop("support_observation_window_complete")

	func _finish(_ok: bool, message: String, _exit_code: int = -1) -> void:
		finishing = true
		_flush_audit()
		# Probe the full server's in-memory player route through a new actual
		# session, rather than infer route release solely from bootstrap/SQL.
		var route_gateway := ProductionGateway.new()
		route_gateway.persist_session = false
		get_tree().root.add_child(route_gateway)
		var route_events: Array = []
		route_gateway.event_received.connect(func(kind, _payload): route_events.append(kind))
		var expiry := Time.get_datetime_string_from_unix_time(int(Game.gateway.token_expires_at)) + "Z"
		var route_authenticated: bool = route_gateway.accept_session(Game.gateway.token, expiry, own_user_id)
		if route_authenticated: route_gateway.connect_realtime()
		var route_deadline := Time.get_ticks_msec() + 5000
		while not route_gateway.online and Time.get_ticks_msec() < route_deadline:
			await get_tree().process_frame
		await get_tree().create_timer(0.75).timeout
		var route_clear: bool = route_gateway.online and not route_events.any(func(kind): return kind in ["room.snapshot", "room.started", "room.ready_required"])
		route_gateway.reconnect_enabled = false
		route_gateway.socket.close()
		while route_gateway.socket.get_ready_state() != WebSocketPeer.STATE_CLOSED and Time.get_ticks_msec() < route_deadline:
			route_gateway.socket.poll()
			await get_tree().process_frame
		route_gateway.queue_free()
		var recovery_ok := true
		if case_name in ["normal_ready", "required_lost_reconnect", "late_required_duplicate", "send_false_twice_then_success"]:
			recovery_ok = observed_room_checks and not observed_room_id.is_empty() and observed_match_id == active_match_id
		if case_name == "required_lost_reconnect":
			recovery_ok = recovery_ok and probe_gateway.required_dropped and probe_gateway.connected_count >= 2 and probe_gateway.required_delivered > 0
		if case_name == "late_required_duplicate": recovery_ok = recovery_ok and probe_gateway.duplicate_deliveries >= 2
		if case_name == "late_accepted_before_ticket": recovery_ok = probe_gateway.ticket_reads >= 2 and active_match_id != FaultGateway.STALE_MATCH_ID
		if case_name in ["ready_required_all_lost_ticket", "ready_started_all_lost_snapshot", "ready_accepted_lost_resume", "ready_started_lost_reconnect", "ready_replies_lost_reconnect", "ready_send_lost_reconnect"]:
			recovery_ok = observed_room_checks and not observed_room_id.is_empty() and observed_match_id == active_match_id and observed_match_id == probe_gateway.expected_match_id and observed_room_id == probe_gateway.expected_room_id
			if case_name.ends_with("reconnect"): recovery_ok = recovery_ok and probe_gateway.connected_count >= 2
			if case_name == "ready_accepted_lost_resume": recovery_ok = recovery_ok and probe_gateway.resume_send_count >= 1
			if case_name == "ready_required_all_lost_ticket": recovery_ok = recovery_ok and probe_gateway.required_delivered==0 and probe_gateway.ticket_reads>=1 and probe_gateway.ready_send_count>=1
		if case_name == "ready_send_all_lost_stop": recovery_ok = probe_gateway.ready_send_count == 3 and observed_room_id.is_empty()
		if case_name == "send_false_twice_then_success":
			var false_events: Array = probe_gateway.trace.filter(func(e): return e.event == "controlled_send_false")
			var authority_events: Array = probe_gateway.trace.filter(func(e): return e.event == "actual_server_envelope" and e.kind in ["room.ready_accepted", "room.started"])
			recovery_ok = recovery_ok and probe_gateway.ready_send_count == 3 and ready_attempts == 3 and ready_successful_sends == 1 and false_events.size() == 2 and authority_events.any(func(e): return e.kind == "room.ready_accepted") and authority_events.any(func(e): return e.kind == "room.started")
		if case_name == "all_three_sends_false":
			var false_events: Array = probe_gateway.trace.filter(func(e): return e.event == "controlled_all_send_false")
			recovery_ok = not _ok and probe_gateway.ready_send_count == 3 and ready_attempts == 3 and ready_successful_sends == 0 and false_events.size() == 3 and observed_room_id.is_empty() and checks.any(func(e): return e.name == "ready_send_exhausted" and not e.passed)
			stop_boundary = "expected_bounded_ready_send_exhausted_terminal"
		if case_name == "matched_reply_after_actual_deadline":
			var delivered: Array = probe_gateway.trace.filter(func(e): return e.event == "real_matched_response_delivered_after_deadline")
			recovery_ok = not _ok and probe_gateway.ready_send_count == 0 and ready_attempts == 0 and ready_successful_sends == 0 and observed_room_id.is_empty() and checks.any(func(e): return e.name in ["ready_ticket_terminal", "ready_ticket_missing", "room_start_timeout"] and not e.passed) and not delivered.is_empty()
			if not delivered.is_empty():
				recovery_ok = recovery_ok and delivered.all(func(e): return e.actual_deadline_unix_ms > 0 and e.observed_unix_ms > e.actual_deadline_unix_ms)
			stop_boundary = "expected_authoritative_expired_ready_ticket_terminal"
		var local_terminal: bool = Game.preparation.is_empty() and Game.ticket.is_empty() and Game.ready_prompt.is_empty() and Game.room.is_empty() and Game.settlement.is_empty()
		case_passed = recovery_ok and route_clear and local_terminal and cleanup_result.state == "Passed" and probe_gateway.ready_send_after_stop == 0 and not stop_boundary.is_empty()
		var result := {"case": case_name, "passed": case_passed, "Accepted": false,
			"coverage": "SupportOnly" if case_name == "late_accepted_before_ticket" else "OFFLINE_POSTGRES_FULL_PROGRAM",
			"stop_boundary": stop_boundary, "original_finish_ok": _ok, "message": message, "checks": checks, "errors": errors,
			"active_match_id": active_match_id, "observed_match_id": observed_match_id, "observed_room_id": observed_room_id,
			"own_user_id": own_user_id, "cleanup": cleanup_result, "client_ticket": Game.ticket, "client_preparation": Game.preparation,
			"local_terminal": local_terminal, "client_ready_prompt": Game.ready_prompt,
			"client_room": not Game.room.is_empty(), "client_settlement": not Game.settlement.is_empty(),
			"connected_count": probe_gateway.connected_count, "required_dropped": probe_gateway.required_dropped,
			"expected_match_id": probe_gateway.expected_match_id, "expected_room_id": probe_gateway.expected_room_id,
			"resume_send_count": probe_gateway.resume_send_count,
			"route_probe_clear": route_clear, "route_probe_events": route_events,
			"required_delivered": probe_gateway.required_delivered, "ticket_reads": probe_gateway.ticket_reads,
			"ready_send_count": probe_gateway.ready_send_count, "ready_send_after_stop": probe_gateway.ready_send_after_stop,
			"actual_load_ready_attempts": ready_attempts, "actual_load_ready_successful_sends": ready_successful_sends,
			"trace": probe_gateway.trace}
		var output := FileAccess.open(report_path, FileAccess.WRITE)
		output.store_string(JSON.stringify(result, "\t"))
		output.close()
		finished = true
		print(JSON.stringify({"case": case_name, "passed": case_passed, "Accepted": false, "cleanup": cleanup_result.state}))
		get_tree().quit(0 if case_passed else 1)

func _initialize() -> void:
	print("READY_PROBE initialize")
	call_deferred("_run_fixture")

func _run_fixture() -> void:
	print("READY_PROBE fixture_start")
	var store: Node = root.get_node("Game")
	var old_gateway: Node = store.gateway
	old_gateway.reconnect_enabled = false
	old_gateway.queue_free()
	var gateway: Node = FaultGateway.new()
	store.gateway = gateway
	store.add_child(gateway)
	gateway.failed.connect(func(message): store.notice.emit(message))
	gateway.event_received.connect(store._on_event)
	gateway.telemetry.connect(store._on_gateway_telemetry)
	gateway.connection_changed.connect(store._on_connection_changed)
	gateway.authentication_required.connect(store._on_authentication_required)
	var probe: Node = LoadProbe.new()
	gateway.probe = probe
	probe.probe_gateway = gateway
	root.add_child(probe)
	print("READY_PROBE fixture_attached")
