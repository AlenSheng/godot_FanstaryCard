extends SceneTree

const Proto = preload("res://network/protobuf.gd")
const M := "11111111-1111-1111-1111-111111111111"
const N := "22222222-2222-2222-2222-222222222222"
const RECEIPT := "33333333-3333-3333-3333-333333333333"
var game: Node
var checks: Dictionary = {}
var failures: Array = []
var samples: Array = []
var case_deadline := 0
var sequence := 0

func _initialize() -> void: _run.call_deferred()

func _control(data: Dictionary) -> Dictionary:
	var http := HTTPRequest.new()
	root.add_child(http)
	http.timeout = 2.0
	var error := http.request(game.gateway.base_url + "/fixture/control", ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(data))
	if error != OK:
		http.queue_free()
		checks.control_request = false
		return {}
	var result: Array = await http.request_completed
	http.queue_free()
	return JSON.parse_string(result[3].get_string_from_utf8()) if int(result[1]) == 200 else {}

func _begin(id: String) -> void:
	checks = {}
	samples = []
	case_deadline = Time.get_ticks_msec() + int(OS.get_environment("PR13_CALLBACK_CASE_SECONDS")) * 1000
	game.logout()
	game.gateway.begin_sign_in(game.gateway.base_url)
	game.gateway.accept_session("callback-token-A", "2099-01-01T00:00:00Z", "callback-A")
	sequence = 0
	await _control({"op": "reset", "case_id": id})

func _plan(paused := false, receipt := false, path := "/api/v1/bootstrap", account := "callback-A") -> void:
	await _control({"op": "plan", "path": path, "paused": paused, "receipt_id": RECEIPT if receipt else "", "match_id": M, "account": account})

func _until_started(index: int) -> void:
	while Time.get_ticks_msec() < case_deadline:
		var state := await _control({"op": "state"})
		if state.get("plans", []).size() > index and state.plans[index].started: return
		await create_timer(0.01).timeout
	checks["request_started_" + str(index)] = false

func _drain() -> void:
	while not game.gateway._pending_http.is_empty() and Time.get_ticks_msec() < case_deadline:
		await process_frame
	for _frame in 4: await process_frame
	checks.requests_completed_within_fixed_budget = game.gateway._pending_http.is_empty()

func _snapshot(match_id: String, room_id := "", phase := "Exploring", promote := true) -> void:
	sequence += 1
	var proto := Proto.new()
	var next_room_id: String = room_id if not room_id.is_empty() else "room-" + match_id
	if promote:
		# This fixture supplies a new verified ticket before delivering its
		# snapshot. An unrelated snapshot alone cannot promote M to N. Keep the
		# store's epoch and recovery state intact so adoption must invalidate them.
		if game.gateway.current_match_id != match_id or game.gateway.room_id != next_room_id:
			game.gateway.room_id = ""
			game.gateway.room_revision = 0
		game.gateway.bind_prelaunch_ticket(match_id, next_room_id,
			int(Time.get_unix_time_from_system() * 1000.0) + 30000, game._room_context_epoch)
	var snapshot := {"match_id": match_id, "room_id": next_room_id,
		"room_revision": 8, "config_version": game.CATALOG.data.version,
		"player": {"player_id": game.gateway.authenticated_user_id, "phase": phase, "hand": []}}
	game.gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "room.snapshot", "sequence": sequence,
		"room_revision": 8, "payload": proto.encode("RoomSnapshotEvent", snapshot)}))
	if promote:
		checks["authoritative_snapshot_" + str(sequence)] = game.room.get("match_id", "") == match_id and game.gateway.room_id == next_room_id

func _origin() -> Dictionary: return game.gateway.capture_context()

func _error(origin: Dictionary) -> void:
	game._on_event("error.command_rejected", {"code": "NOT_IN_ROOM", "_origin_context": origin.duplicate(true)})

func _wire_correlated_error() -> void:
	var socket := WebSocketPeer.new()
	game.gateway.socket = socket
	socket.connect_to_url(game.gateway.base_url.replace("http://", "ws://") + "/ws/v1/callback?sequence=" + str(sequence + 1))
	while socket.get_ready_state() != WebSocketPeer.STATE_OPEN and Time.get_ticks_msec() < case_deadline:
		socket.poll()
		await process_frame
	checks.real_websocket_command_sent = game.gateway.send("room.snapshot.read", {}, "callback-actual-command")
	while socket.get_available_packet_count() == 0 and Time.get_ticks_msec() < case_deadline:
		socket.poll()
		await process_frame
	if socket.get_available_packet_count() > 0:
		checks.real_websocket_response_received = true
		sequence += 1
		game.gateway._receive(socket.get_packet())
	else:
		checks.real_websocket_response_received = false
	socket.close()

func _wire_unrelated_error() -> void:
	sequence += 1
	var proto := Proto.new()
	game.gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "error.command_rejected",
		"sequence": sequence, "room_revision": 8, "payload": proto.encode("CommandRejectedEvent", {"code": "NOT_IN_ROOM"})}))

func _state(label: String) -> void:
	samples.append({"label": label, "session_generation": game.gateway.session_generation,
		"account": game.gateway.authenticated_user_id, "match_id": game.room.get("match_id", ""),
		"room_id": game.gateway.room_id, "recovery_match_id": game._settlement_recovery_match_id,
		"receipt_id": game.settlement.get("settlementId", ""), "polling": game._settlement_polling,
		"loading": game._settlement_loading})

func _finish(id: String, expected: String) -> void:
	var ok := not checks.values().has(false)
	if not ok: failures.append(id)
	print(JSON.stringify({"callback_case": id, "expected": expected, "actual": samples, "checks": checks,
		"status": "Passed" if ok else "Failed", "profile": "OFFLINE", "Accepted": false,
		"remaining_profiles": ["POSTGRES", "LIVE"]}))

func _run() -> void:
	game = root.get_node("Game")
	game.set_process(false)
	game.gateway.set_process(false)
	game.gateway.persist_session = false
	await process_frame
	await _begin("PR13-A03.1-T01")
	_snapshot(M)
	var origin := _origin()
	await _plan()
	await _wire_correlated_error()
	await _drain()
	_state("first_NOT_IN_ROOM_no_receipt")
	await _plan()
	_error(origin)
	await _drain()
	_state("duplicate_NOT_IN_ROOM_no_receipt")
	checks.duplicate_preserves_M = game.room.is_empty() and game._settlement_recovery_match_id == M
	await _plan(false, true, "/api/v1/bootstrap?settlementMatchId=" + M)
	game.retry_settlement()
	await _drain()
	_state("M_receipt_ready")
	checks.receipt_M_recovered = game.settlement.get("settlementId", "") == RECEIPT and game.settlement.get("matchId", "") == M
	_finish("PR13-A03.1-T01", "Duplicate real NOT_IN_ROOM retains M until the matching ready receipt arrives")

	await _begin("PR13-A03.1-T02")
	_snapshot(M)
	origin = _origin()
	await _plan(true)
	_error(origin)
	await _until_started(0)
	_error(origin)
	_state("two_errors_Bootstrap_paused")
	checks.paused_bootstrap_keeps_M = game._settlement_recovery_match_id == M
	await _control({"op": "release", "index": 0})
	await _drain()
	_state("late_Bootstrap_without_receipt")
	checks.late_bootstrap_keeps_M = game._settlement_recovery_match_id == M and game.settlement.is_empty()
	await _plan(false, true, "/api/v1/bootstrap?settlementMatchId=" + M)
	game.retry_settlement()
	await _drain()
	_state("M_ready_after_late_Bootstrap")
	checks.recovery_continues_M = game.settlement.get("matchId", "") == M
	_finish("PR13-A03.1-T02", "Paused late Bootstrap without receipt preserves M and the subsequent M receipt recovers")

	await _begin("PR13-A03.1-T03")
	_snapshot(M)
	await _plan()
	_error({})
	await _drain()
	_state("missing_origin_error")
	checks.no_context_cannot_clear_valid_M = game.room.get("match_id", "") == M
	_wire_unrelated_error()
	_state("uncorrelated_protobuf_Gateway_receive")
	checks.uncorrelated_wire_error_preserves_M = game.room.get("match_id", "") == M and game.gateway.room_id == "room-" + M
	_snapshot(M)
	origin = _origin()
	origin.match_id = ""
	_error(origin)
	await _drain()
	_state("empty_match_origin_error")
	checks.empty_match_cannot_clear_valid_M = game.room.get("match_id", "") == M
	_finish("PR13-A03.1-T03", "An error without a verifiable match cannot clear authoritative M")

	await _begin("PR13-A03.2-T01")
	_snapshot(M)
	origin = _origin()
	_snapshot(N, "", "Exploring", false)
	checks.unannounced_N_snapshot_preserves_M = game.room.get("match_id", "") == M and game.gateway.room_id == "room-" + M
	_snapshot(N)
	_snapshot(M, "", "Exploring", false)
	checks.late_M_snapshot_preserves_N = game.room.get("match_id", "") == N and game.gateway.room_id == "room-" + N
	_error(origin)
	await _drain()
	_state("old_M_error_after_authoritative_N_same_session")
	checks.old_M_error_preserves_N = game.room.get("match_id", "") == N and game.gateway.room_id == "room-" + N
	await _plan()
	_error({})
	await _drain()
	_state("uncorrelated_error_after_N")
	checks.uncorrelated_error_preserves_N = game.room.get("match_id", "") == N
	_snapshot(M)
	origin = _origin()
	_snapshot(N)
	_snapshot(M)
	_error(origin)
	await _drain()
	_state("old_cycle_error_after_M_N_M_same_session")
	checks.same_session_cycle_rejects_old_context = game.room.get("match_id", "") == M and game._settlement_recovery_match_id.is_empty()
	_finish("PR13-A03.2-T01", "M and uncorrelated old errors arriving after N do not clear N in the same session")

	await _begin("PR13-A03.2-T02")
	_snapshot(M)
	origin = _origin()
	await _plan(true, true)
	_error(origin)
	await _until_started(0)
	_snapshot(N)
	_state("N_arrives_while_M_Bootstrap_paused")
	await _control({"op": "release", "index": 0})
	await _drain()
	_state("late_M_Bootstrap_after_N")
	checks.late_Bootstrap_preserves_N = game.room.get("match_id", "") == N and game.settlement.is_empty()
	checks.new_room_releases_M_recovery = game._settlement_recovery_match_id.is_empty()
	_snapshot(M)
	await _plan(true, true, "/api/v1/settlements/" + RECEIPT)
	game._on_event("settlement.ready", {"settlement_id": RECEIPT, "match_id": M})
	await _until_started(1)
	_snapshot(N)
	await _control({"op": "release", "index": 1})
	await _drain()
	_state("late_M_settlement_GET_after_N")
	checks.late_settlement_GET_preserves_N = game.room.get("match_id", "") == N and game.settlement.is_empty() and game._settlement_loading.is_empty()
	_snapshot(M, "", "Dead")
	await _plan(true, true, "/api/v1/bootstrap?settlementMatchId=" + M)
	game.retry_settlement()
	await _until_started(2)
	_snapshot(N)
	_state("N_cancels_paused_M_poll")
	checks.N_cancels_M_poll_ownership = not game._settlement_polling and game._settlement_recovery_match_id.is_empty()
	await _control({"op": "release", "index": 2})
	await _drain()
	_state("late_M_poll_after_N")
	checks.late_M_poll_preserves_N = game.room.get("match_id", "") == N and game.settlement.is_empty() and not game._settlement_polling
	_snapshot(M)
	await _plan(true, true)
	game.refresh_lobby()
	await _until_started(3)
	_snapshot(N)
	_snapshot(M)
	await _control({"op": "release", "index": 3})
	await _drain()
	_state("late_Bootstrap_after_M_N_M_same_session")
	checks.same_session_cycle_rejects_old_Bootstrap = game.room.get("match_id", "") == M and game.settlement.is_empty()
	_finish("PR13-A03.2-T02", "Delayed M Bootstrap and settlement GET cannot overwrite N or retain M recovery ownership")

	await _begin("PR13-A03.2-T03")
	_snapshot(M)
	origin = _origin()
	await _plan(true, true)
	_error(origin)
	await _until_started(0)
	game.logout()
	game.gateway.begin_sign_in(game.gateway.base_url)
	game.gateway.accept_session("callback-token-B", "2099-01-01T00:00:00Z", "callback-B")
	sequence = 0
	_snapshot(N)
	await _control({"op": "release", "index": 0})
	await _drain()
	_state("old_A_Bootstrap_after_B_N")
	checks.account_switch_discards_A_bootstrap = game.gateway.authenticated_user_id == "callback-B" and game.room.get("match_id", "") == N and game.settlement.is_empty()
	_snapshot(M)
	await _plan(false, false, "/api/v1/bootstrap", "callback-B")
	_error(origin)
	await _drain()
	_state("old_session_error_matching_room_id_in_B")
	checks.old_session_error_cannot_clear_B = game.room.get("match_id", "") == M and game._settlement_recovery_match_id.is_empty()
	_finish("PR13-A03.2-T03", "Changing account cancels old Bootstrap and rejects old-session callbacks even if room/match IDs match")
	game.logout()
	quit(0 if failures.is_empty() else 1)
