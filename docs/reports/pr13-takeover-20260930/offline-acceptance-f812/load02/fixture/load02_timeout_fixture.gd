extends SceneTree

# A real HTTP timeout at the production transport's unchanged 10s/30s limits.
# This fixture has no account, preparation or server business claim.
class ReportProbe:
	extends "res://tests/gameplay_load_client.gd"
	func _ready() -> void:
		pass
	func _process(_delta: float) -> void:
		pass

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var probe := ReportProbe.new()
	root.add_child(probe)
	probe.Game = root.get_node("Game")
	probe.client_id = "real-timeout-before-stop"
	probe.run_id = "load02-owned-loopback-timeout"
	probe.process_epoch = "1"
	probe.stage = "playing"
	probe.report_path = OS.get_environment("FANTASYCARD_LOAD_REPORT")
	probe.stop_file = OS.get_environment("FANTASYCARD_LOAD_STOP_FILE")
	probe.started_at_ms = Time.get_ticks_msec()
	var gateway: Node = load("res://network/gateway.gd").new()
	root.add_child(gateway)
	gateway.persist_session = false
	gateway.reconnect_enabled = false
	gateway.base_url = OS.get_environment("FANTASYCARD_SERVER_URL")
	gateway.telemetry_context = {"run_id": probe.run_id, "client_id": probe.client_id,
		"process_epoch": probe.process_epoch, "cycle_id": probe.client_id + ":1", "phase": "playing"}
	gateway.telemetry.connect(probe._on_telemetry)
	gateway.failed.connect(probe._on_notice)
	var result: Dictionary = await gateway.request("/api/v1/client-info", HTTPClient.METHOD_GET)
	var timeout_finished := Time.get_ticks_msec()
	var timeout_wall := int(Time.get_unix_time_from_system() * 1000.0)
	await create_timer(0.05).timeout
	var stop_mono := Time.get_ticks_msec()
	FileAccess.open(probe.stop_file, FileAccess.WRITE).store_string("STOP after real terminal timeout")
	probe.stop_requested = true
	probe.cleanup_result = {"state": "Unknown", "reason": "no_account_or_server_business_in_this_transport_fixture"}
	FileAccess.open(probe.report_path + ".boundary.json", FileAccess.WRITE).store_string(JSON.stringify({
		"request_result": result, "timeout_finished_monotonic_ms": timeout_finished,
		"timeout_finished_wall_ms": timeout_wall, "stop_monotonic_ms": stop_mono,
		"real_transport": true, "production_attempt_timeout_ms": 10000,
		"production_logical_deadline_ms": 30000, "business_scope": "no PG account in transport fixture"}))
	await probe._finish(false, "Coordinator cancelled after prior real timeout", 0)
