extends RefCounted

class SocketStub extends RefCounted:
	var closed := false
	func close() -> void: closed = true

class GatewayStub extends Node:
	var session_generation := 1
	var telemetry_context: Dictionary = {}
	var reconnect_enabled := true
	var socket = SocketStub.new()
	var responses: Array = []
	var calls := 0
	var mode := ""
	var game: Node
	var probe: Node
	func request(path: String, method: int, data: Variant, _quiet: Array) -> Dictionary:
		assert(path == "/api/v1/bootstrap" and method == HTTPClient.METHOD_GET and data == null)
		calls += 1
		if mode == "deadline": await Engine.get_main_loop().create_timer(22.05).timeout
		else: await Engine.get_main_loop().process_frame
		if calls == 1:
			match mode:
				"session": session_generation += 1
				"match": probe.active_match_id = "new-match"
				"preparation": game.preparation = {"preparationId":"new-preparation"}
				"ticket": game.ticket = {"ticketId":"new-ticket"}
				"backoff_session": Engine.get_main_loop().create_timer(.05).timeout.connect(func(): session_generation += 1)
		return responses[mini(calls - 1, responses.size() - 1)].duplicate(true)

class CatalogStub extends RefCounted:
	var data := {"version":"cleanup-fixture"}

class GameStub extends Node:
	signal changed
	var gateway: Node
	var CATALOG = CatalogStub.new()
	var room: Dictionary = {}
	var settlement: Dictionary = {}
	var preparation := {"preparationId":"preparation"}
	var ticket := {"ticketId":"ticket"}
	var ready_prompt := {"keep":true}
	var lobby := {"activePreparation":{"preparationId":"preparation"},"configVersion":"cleanup-fixture"}
	var ack_ok := true
	var ack_receipts: Array = []
	var cache_updates: Array = []
	func allowed(_action: String) -> bool: return false
	func update_cache(kind: String, value: Variant) -> void: cache_updates.append({"kind":kind,"value":value})
	func acknowledge_settlement() -> bool:
		ack_receipts.append(settlement.duplicate(true))
		await Engine.get_main_loop().process_frame
		if ack_ok: settlement = {}; room = {}
		return ack_ok

class Probe extends "res://tests/gameplay_load_client.gd":
	var cancel_calls := 0
	func _ready() -> void: set_process(false)
	func _cancel_waiting_preparation(_generation: int, _match_id: String, _preparation_id: String, _ticket_id: String) -> void:
		# The queued-cancellation contract is separate. Preserve these values
		# to exercise the actual verification loop and its context guards.
		cancel_calls += 1

func _clear() -> Dictionary:
	return {"ok":true,"status":200,"data":{"configVersion":"cleanup-fixture","activePreparation":null,"unfinishedMatch":null,"unfinishedSettlement":null,"inventory":{"items":[]}}}

func _failure(status: int = 500) -> Dictionary:
	return {"ok":false,"status":status,"data":{"title":"Synthetic unavailable","status":status,"detail":"Synthetic transient read failure"}}

func _receipt() -> Dictionary:
	var value := _clear()
	value.data.unfinishedSettlement = {"matchId":"match","settlementId":"receipt","result":"Defeat"}
	return value

func _case(responses: Array, mode: String = "", ack_ok: bool = true) -> Dictionary:
	var game := GameStub.new(); var gateway := GatewayStub.new(); var probe := Probe.new()
	game.gateway = gateway; gateway.game = game; gateway.probe = probe
	gateway.responses = responses; gateway.mode = mode; game.ack_ok = ack_ok
	Engine.get_main_loop().root.add_child(probe)
	probe.Game = game; probe.run_id = "cleanup-fixture"; probe.client_id = "client"; probe.process_epoch = "process"
	probe.active_match_id = "match"; probe.stop_requested = true; probe.last_progress_ms = 123
	probe._config_package_checked = true; probe._config_package_digest = "synthetic-config"
	return {"game":game,"gateway":gateway,"probe":probe}

func _free(c: Dictionary) -> void:
	c.gateway.game = null; c.gateway.probe = null; c.game.gateway = null
	c.probe.free(); c.game.free(); c.gateway.free()

func _retries(c: Dictionary) -> Array:
	return c.probe.telemetry.filter(func(v): return v.get("event_type") == "cleanup.bootstrap_retry")

func _preserved(c: Dictionary) -> bool:
	return not c.game.preparation.is_empty() and not c.game.ticket.is_empty() and not c.game.ready_prompt.is_empty() and c.game.lobby.activePreparation is Dictionary and c.game.cache_updates.is_empty()

func run_test() -> Dictionary:
	var checks: Dictionary = {}; var c := _case([_clear()])
	await c.probe._graceful_cleanup()
	checks["single authoritative clear remains Passed"] = c.probe.cleanup_result.state == "Passed" and c.gateway.calls == 1 and c.game.preparation.is_empty() and c.game.ticket.is_empty()
	checks["socket and reconnect stop independently of verification"] = c.gateway.socket.closed and not c.gateway.reconnect_enabled
	checks["verification cannot credit a completed gameplay cycle"] = c.probe.cycles_completed == 0 and c.probe.last_progress_ms == 123 and not c.probe.telemetry.any(func(v): return v.get("event_type") == "cycle.completed")
	_free(c)
	for status in [500,503]:
		c = _case([_failure(status),_clear()]); await c.probe._graceful_cleanup()
		checks[str(status)+" read failure then authoritative clear recovers"] = c.probe.cleanup_result.state == "Passed" and c.gateway.calls == 2
		checks[str(status)+" failure and retry remain observable"] = c.probe.cleanup_result.get("bootstrap_read_failures") == 1 and c.probe.cleanup_result.get("bootstrap_read_retries") == 1 and _retries(c).size() == 1 and _retries(c)[0].status == status
		checks[str(status)+" recovery only clears after authority and never ACKs absent receipt"] = c.game.preparation.is_empty() and c.game.ack_receipts.is_empty() and c.game.cache_updates.size() == 1
		_free(c)
	c = _case([_failure()]); await c.probe._graceful_cleanup()
	checks["three persistent failures remain Unknown and bounded"] = c.probe.cleanup_result.state == "Unknown" and c.probe.cleanup_result.reason == "verification_retry_exhausted" and c.gateway.calls == 3 and _retries(c).size() == 2
	checks["persistent failure retains preparation ticket and pending state"] = _preserved(c) and c.game.ack_receipts.is_empty() and c.probe.cleanup_result.get("bootstrap_read_failures") == 3
	_free(c)
	for response in [_failure(401),{"ok":false,"status":500,"data":null}, {"ok":true,"status":200,"data":{"configVersion":"cleanup-fixture"}}]:
		c = _case([response]); await c.probe._graceful_cleanup()
		var name := "terminal_"+str(response.status)+"_"+str(response.data == null)
		checks[name+" is not retried or treated clear"] = c.gateway.calls == 1 and c.probe.cleanup_result.state == "Unknown" and _retries(c).is_empty() and _preserved(c)
		_free(c)
	for response in [{"ok":false,"status":0,"error":"Synthetic pagination failure"},{"ok":false,"status":500,"error":"Missing decoded error body"},{"ok":true,"status":200}]:
		c = _case([response]); await c.probe._graceful_cleanup()
		checks["partial_gateway_"+str(response.status)+"_"+str(response.ok)+" remains Unknown without unsafe dictionary access"] = c.gateway.calls == 1 and c.probe.cleanup_result.state == "Unknown" and c.probe.cleanup_result.get("bootstrap_read_failures") == 1 and _retries(c).is_empty() and _preserved(c)
		_free(c)
	for mode in ["session","match","preparation","ticket","backoff_session"]:
		c = _case([_failure(),_clear()],mode); await c.probe._graceful_cleanup()
		checks[mode+" change blocks a new request and clear"] = c.gateway.calls == 1 and c.probe.cleanup_result.state == "Unknown" and c.probe.cleanup_result.reason == "cleanup_context_changed" and _preserved(c) and c.game.ack_receipts.is_empty()
		checks[mode+" failed verification call is counted despite context cancellation"] = c.probe.cleanup_result.get("bootstrap_read_attempts") == 1 and c.probe.cleanup_result.get("bootstrap_read_failures") == 1 and c.probe.cleanup_result.get("bootstrap_read_retries") == 0 and c.probe.cleanup_result.get("bootstrap_last_http_status") == 500
		_free(c)
	c = _case([_clear()],"session"); await c.probe._graceful_cleanup()
	checks["successful read from cancelled context cannot clear or become a read failure"] = c.probe.cleanup_result.state == "Unknown" and c.probe.cleanup_result.reason == "cleanup_context_changed" and _preserved(c) and c.probe.cleanup_result.get("bootstrap_read_failures") == 0 and c.probe.cleanup_result.get("bootstrap_last_http_status") == 200 and c.gateway.calls == 1
	_free(c)
	c = _case([_failure(),_receipt(),_clear()]); await c.probe._graceful_cleanup()
	checks["same-match receipt after read recovery reaches existing ACK path"] = c.gateway.calls == 3 and c.probe.cleanup_result.state == "Passed" and c.game.ack_receipts.size() == 1 and c.game.ack_receipts[0].settlementId == "receipt" and c.game.ack_receipts[0].matchId == "match"
	checks["recovered drain ACK is separate from natural cycle credit"] = c.probe.cycles_completed == 0 and c.probe.telemetry.any(func(v): return v.get("event_type") == "settlement.acknowledged" and v.get("completion_stage") == "drain_ack_only")
	_free(c)
	c = _case([_receipt()],"",false); await c.probe._graceful_cleanup()
	checks["three unsuccessful ACKs remain Unknown with receipt retained"] = c.probe.cleanup_result.state == "Unknown" and c.probe.cleanup_result.reason == "settlement_ack_unresolved" and c.game.ack_receipts.size() == 3 and not c.game.settlement.is_empty() and _preserved(c)
	_free(c)
	c = _case([_failure()],"deadline"); var started := Time.get_ticks_msec(); await c.probe._graceful_cleanup(); var elapsed := Time.get_ticks_msec()-started
	checks["late read cannot start a retry beyond original22second window"] = elapsed >= 22000 and c.gateway.calls == 1 and c.probe.cleanup_result.state == "Unknown" and _retries(c).is_empty() and _preserved(c)
	_free(c)
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual Native cleanup coroutine and recorder;explicit synthetic Gateway/ACK backend;original22second window,zero real accounts/worlds;not real PostgreSQL ACK or capacity acceptance"}
