extends SceneTree
const Gateway = preload("res://network/gateway.gd")
var gateway: Node
var events: Array = []
var finished := false
var result: Dictionary = {}
var logical_received_mono_ms := -1
var phases := ["login", "initial", "matchmaking", "playing", "settlement", "cleanup"]
func _initialize() -> void: run.call_deferred()
func collect(sample: Dictionary) -> void:
	events.append(sample.duplicate(true))
	if sample.get("type") == "http": logical_received_mono_ms = Time.get_ticks_msec()
func request(path: String) -> void:
	result = await gateway.request(path)
	finished = true
func run() -> void:
	gateway = Gateway.new();gateway.persist_session = false;gateway.reconnect_enabled = false
	root.add_child(gateway);gateway.telemetry.connect(collect)
	var mode := OS.get_environment("PHASE_MODE")
	var initial := mode if mode in phases else ""
	var path := "/api/v1/matches/00000000-0000-0000-0000-000000000003/settlement" if mode == "settlement" else "/api/v1/bootstrap"
	gateway.telemetry_context = {"cycle_id":"M-cycle", "run_id":"owned-phase", "client_id":mode, "process_epoch":"1"}
	if not initial.is_empty(): gateway.telemetry_context["phase"] = initial
	var requested_mono_ms := Time.get_ticks_msec()
	request(path)
	await create_timer(.2).timeout
	var pending_before_release: int = gateway._pending_http.size()
	var changed_mono_ms := Time.get_ticks_msec()
	gateway.telemetry_context = {"phase":"cleanup", "cycle_id":"N-cycle", "run_id":"owned-phase", "client_id":mode, "process_epoch":"1"}
	var http := HTTPRequest.new();root.add_child(http)
	http.request(OS.get_environment("FANTASYCARD_SERVER_URL") + "/fixture/release")
	await http.request_completed;http.queue_free()
	var deadline := Time.get_ticks_msec() + 5000
	while not finished and Time.get_ticks_msec() < deadline: await process_frame
	var raw := {"mode":mode,"pid":OS.get_process_id(),"requested_monotonic_ms":requested_mono_ms,"context_changed_monotonic_ms":changed_mono_ms,"logical_received_monotonic_ms":logical_received_mono_ms,"initial_phase":initial,"current_phase":gateway.telemetry_context.phase,"initial_cycle":"M-cycle","current_cycle":"N-cycle","pending_before_release":pending_before_release,"finished":finished,"result":result,"events":events,"phase_vocabulary":phases,"protocol_body":"production HTTP_SCHEMA encoded fixture; no account/business/PG claim"}
	FileAccess.open(OS.get_environment("PHASE_RESULT"),FileAccess.WRITE).store_string(JSON.stringify(raw))
	gateway._reusable_http.close();gateway.queue_free();await process_frame
	quit(0 if finished and result.ok else 1)
