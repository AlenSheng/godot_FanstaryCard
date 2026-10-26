extends SceneTree

const ProductionLoad = preload("res://tests/gameplay_load_client.gd")
var cases: Array = []

class ReadyStore extends Node:
	var lobby := {"configVersion":"controlled-ready"}
	var preparation: Dictionary = {}
	var ticket: Dictionary = {}
	var room: Dictionary = {}
	var settlement: Dictionary = {}
	var ready_prompt: Dictionary = {}
	var gateway: Node
	func prepare(_tier: String, _potions: int) -> void: preparation={"preparationId":"controlled-preparation"}
	func enqueue() -> void: ticket={"ticketId":"controlled-ticket"}

class ReadyGateway extends Node:
	# The producer now binds a pending READY to this transport instance.
	# This declared dispatch stub needs the same peer identity as the real API.
	var socket := WebSocketPeer.new()
	var store: Node
	var probe: Node
	var scenario := ""
	var telemetry_context: Dictionary = {}
	var sends: Array = []
	var reads := 0
	func request(_path: String) -> Dictionary:
		reads+=1
		var status := "Matched"
		if scenario=="expired" and reads>=2: status="Expired"
		if scenario=="temporarily-queued": status="Queued" if reads<3 else "Expired"
		return {"ok":true,"data":{"status":status,"matchId":"controlled-match" if status=="Matched" else ""}}
	func send(kind: String) -> bool:
		var sent := scenario=="third-success" and sends.size()==2
		sends.append({"kind":kind,"result":sent,"monotonic_ms":Time.get_ticks_msec()})
		if sent:
			probe.ready_accepted=true
			# End the component run at actual successful READY dispatch. This
			# is not an invented gameplay cycle or a server-confirmed room.
			probe.stop_requested=true
		return sent

class ReadyProbe extends ProductionLoad:
	func _ready() -> void: set_process(false)
	func _wait(seconds: float) -> void:
		# Preserve the production's one-second retry/two-second query clocks;
		# only polling sleep is shorter in this declared component fixture.
		await get_tree().create_timer(minf(seconds,.01)).timeout

func _initialize() -> void: call_deferred("run_cases")

func run_cases() -> void:
	for scenario in ["all-false","third-success","expired","temporarily-queued"]:
		var store := ReadyStore.new()
		var gateway := ReadyGateway.new()
		var probe := ReadyProbe.new()
		root.add_child(probe)
		probe.Game=store
		store.gateway=gateway;gateway.store=store;gateway.probe=probe;gateway.scenario=scenario
		store.ready_prompt={"match_id":"controlled-match","deadline_unix_ms":int(Time.get_unix_time_from_system()*1000.0)+15000 if scenario!="expired" else 1}
		var started := Time.get_ticks_msec()
		await probe._run_expedition()
		var duration := Time.get_ticks_msec()-started
		var id: String
		var passed := false
		if scenario=="all-false":
			id="LOAD-04.2-T01"
			passed=gateway.sends.size()==3 and probe.ready_successful_sends==0 and probe.checks.any(func(c):return c.name=="ready_send_exhausted" and not c.passed) and duration<10000
		elif scenario=="third-success":
			id="PR13-A04.2-T01"
			passed=gateway.sends.size()==3 and probe.ready_successful_sends==1 and not probe.checks.any(func(c):return not c.passed)
		elif scenario=="expired":
			id="LOAD-04.2-T03"
			passed=gateway.sends.is_empty() and gateway.reads==1 and probe.ready_attempts==0 and probe.ready_successful_sends==0 and probe.checks.any(func(c):return c.name=="ready_deadline_expired" and not c.passed) and duration<10000
		else:
			id="PR13-A04.1-T02"
			passed=gateway.sends.is_empty() and gateway.reads==3 and probe.checks.any(func(c):return c.name=="ready_ticket_terminal" and not c.passed)
		cases.append({"case_id":id,"executed":true,"status":"Passed" if passed else "Failed","profiles_executed":["OFFLINE"],"actual":{"scenario":scenario,"sends":gateway.sends,"successful_sends":probe.ready_successful_sends,"ticket_reads":gateway.reads,"checks":probe.checks,"elapsed_ms":duration},"scope":"Actual production READY loop; declared controlled ticket/dispatch boundary. Expired prompt verifies pre-dispatch deadline refusal; authoritative cancellation is covered separately by the real Game cleanup fixture. Poll sleep shortened but retry/query clocks unchanged. No server room, PG asset or natural cycle claimed."})
		gateway.socket.close()
		probe.free();store.free();gateway.free()
	FileAccess.open(OS.get_environment("PR13_READY_EDGES"),FileAccess.WRITE).store_string(JSON.stringify({"cases":cases}))
	print(JSON.stringify({"executed":cases.size(),"passed":cases.filter(func(c):return c.status=="Passed").size()}))
	quit(0 if cases.all(func(c):return c.status=="Passed") else 1)
