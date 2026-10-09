extends SceneTree

# OFFLINE transport/state race checks only. Real cloud READY/STOP coverage is
# executed separately; these controlled replies are never labelled LIVE.
const ProductionGateway = preload("res://network/gateway.gd")

class ControlledGateway extends ProductionGateway:
	var reply: Dictionary = {}
	var calls: Array = []
	var after_read := Callable()
	func request(path: String, method: int = HTTPClient.METHOD_GET, _data: Variant = null, _quiet_statuses: Array = []) -> Dictionary:
		if path == "/api/v1/client-info":
			# Game's deferred startup read may overlap the first fixture. Supply
			# its unchanged real catalog version instead of a ticket-shaped reply.
			return {"ok": true, "status": 200, "data": {"configVersion": str(get_node("/root/Game").CATALOG.data.version)}}
		calls.append({"path": path, "method": method})
		await get_tree().process_frame
		if method == HTTPClient.METHOD_GET:
			if after_read.is_valid(): after_read.call()
			return reply.duplicate(true)
		return {"ok": true, "status": 200, "data": {}}

var failures: Array = []
var checks: Array = []
var game: Node

func check(value: bool, name: String) -> void:
	checks.append({"name": name, "passed": value})
	if not value: failures.append(name)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	game = root.get_node("Game")
	game.set_process(false)
	game.gateway.set_process(false)
	game.gateway.reconnect_enabled = false
	# Attach the production cleanup harness to the actual Game store while the
	# fixture keeps its login/expedition loop stopped.
	var fixture: Script = load("res://tests/fixtures/cleanup_load_probe.gd")
	check(fixture != null and fixture.can_instantiate(), "production probe loads after autoload construction")
	if fixture == null or not fixture.can_instantiate():
		quit(1)
		return
	var cases := [
		{"name": "Queued", "status": "Queued", "delete": true},
		{"name": "Cancelled", "status": "Cancelled", "delete": true},
		{"name": "QueuedNullMatch", "status": "Queued", "match": null, "delete": true},
		{"name": "QueuedMalformedMatch", "status": "Queued", "match": 7, "delete": false},
		{"name": "Matched", "status": "Matched", "delete": false},
		{"name": "Expired", "status": "Expired", "delete": false},
		{"name": "Unknown", "status": "Other", "delete": false},
		{"name": "ReadFailure", "status": "Queued", "ok": false, "delete": false},
		{"name": "DifferentTicket", "status": "Queued", "ticket": "ticket-other", "delete": false},
		{"name": "DifferentPreparation", "status": "Queued", "preparation": "prep-other", "delete": false},
		{"name": "QueuedWithMatch", "status": "Queued", "match": "match-other", "delete": false},
		{"name": "MatchedWithoutMatch", "status": "Matched", "match": "", "delete": false},
		{"name": "NewSession", "status": "Queued", "change": "session", "delete": false},
		{"name": "NewTicket", "status": "Queued", "change": "ticket", "delete": false},
		{"name": "NewPreparation", "status": "Queued", "change": "preparation", "delete": false},
		{"name": "NewRoomEpoch", "status": "Queued", "change": "epoch", "delete": false},
		{"name": "RoomStarted", "status": "Queued", "change": "room", "delete": false},
		{"name": "SettlementArrived", "status": "Queued", "change": "settlement", "delete": false},
		{"name": "NewCycle", "status": "Queued", "change": "cycle", "delete": false}
	]
	for item in cases:
		var gateway := ControlledGateway.new()
		game.gateway = gateway
		game.add_child(gateway)
		gateway.set_process(false)
		gateway.persist_session = false
		gateway.token = ""
		gateway.session_generation = 7
		game._room_context_epoch = 9
		game.preparation = {"preparationId": "prep-M"}
		game.ticket = {"ticketId": "ticket-M", "preparationId": "prep-M", "status": "Queued"}
		game.room = {}
		game.settlement = {}
		game.lobby = {"activePreparation": game.preparation.duplicate(true)}
		game.busy = false
		var probe: Node = fixture.new()
		root.add_child(probe)
		probe.set_process(false)
		probe.active_match_id = "match-M"
		var match_id: Variant = item.get("match", "match-M" if item.status == "Matched" else "")
		gateway.reply = {"ok": item.get("ok", true), "status": 200 if item.get("ok", true) else 503,
			"data": {"ticketId": item.get("ticket", "ticket-M"), "preparationId": item.get("preparation", "prep-M"),
				"status": item.status, "matchId": match_id}}
		gateway.after_read = func():
			match str(item.get("change", "")):
				"session": gateway.session_generation += 1
				"ticket": game.ticket = {"ticketId": "ticket-N", "preparationId": "prep-N"}
				"preparation": game.preparation = {"preparationId": "prep-N"}
				"epoch": game._room_context_epoch += 1
				"room": game.room = {"match_id": "match-M", "room_id": "room-M"}
				"settlement": game.settlement = {"matchId": "match-M", "settlementId": "receipt-M"}
				"cycle": probe.active_match_id = "match-N"
		await probe._cancel_waiting_preparation(7, "match-M", "prep-M", "ticket-M")
		var deletes: Array = gateway.calls.filter(func(call): return call.method == HTTPClient.METHOD_DELETE)
		check(deletes.size() == (1 if item.delete else 0), item.name + ": queued-only DELETE")
		check(not gateway.calls.is_empty() and gateway.calls[0].path == "/api/v1/matches/tickets/ticket-M" and gateway.calls[0].method == HTTPClient.METHOD_GET,
			item.name + ": authority read precedes cancellation")
		if item.delete:
			check(game.ticket.is_empty() and game.preparation.is_empty(), item.name + ": real Game cancellation entry clears confirmed state")
		else:
			check(not game.ticket.is_empty() and not game.preparation.is_empty(), item.name + ": unconfirmed business state retained")
		var decisions: Array = probe.telemetry.filter(func(event): return event.event_type == "cleanup.ticket_authority")
		check(decisions.size() == 1 and decisions[0].ticket_id == "ticket-M", item.name + ": original identity retained in diagnostic event")
		if item.name == "Matched": check(decisions.size() == 1 and decisions[0].decision == "defer_matched", "Matched: wait for real deadline instead of DELETE")
		if item.has("change"): check(decisions.size() == 1 and decisions[0].decision == "context_changed", item.name + ": late reply cannot act on current context")
		probe.free()
		gateway.queue_free()
		await process_frame
	print("CLEANUP_TICKET_AUTHORITY " + JSON.stringify({"ok": failures.is_empty(), "failures": failures, "checks": checks,
		"scope": "OFFLINE controlled transport and actual production cancellation entry; no LIVE or capacity claim"}))
	quit(0 if failures.is_empty() else 1)
