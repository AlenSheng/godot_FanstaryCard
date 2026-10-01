extends SceneTree

# Only production Game methods and genuine HTTP/WS responses establish state.
# Files synchronize the owned PostgreSQL gate and actual OS host lifecycle.
var failures: Array = []
var observations: Array = []
var http_observations: Array = []
var control: String

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, label: String) -> void:
	observations.append({"check": label, "passed": value})
	if not value: failures.append(label)

func signal_phase(name: String, game) -> void:
	var state := {"phase": name, "match_id": game._settlement_match_id(), "recovery_match_id": game._settlement_recovery_match_id,
		"room": game.room.duplicate(true), "settlement": game.settlement.duplicate(true), "busy": game.busy,
		"gateway_room_id": game.gateway.room_id, "generation": game.gateway.session_generation,
		"preparation": game.preparation.duplicate(true), "lobby_unfinished_match": game.lobby.get("unfinishedMatch"),
		"lobby_unfinished_settlement": game.lobby.get("unfinishedSettlement")}
	FileAccess.open(control + "/" + name + ".json", FileAccess.WRITE).store_string(JSON.stringify(state, "\t"))

func wait_control(name: String) -> Dictionary:
	var end := Time.get_ticks_msec() + 60000
	while not FileAccess.file_exists(control + "/" + name + ".json") and Time.get_ticks_msec() < end:
		await process_frame
	check(FileAccess.file_exists(control + "/" + name + ".json"), "owned control " + name)
	return JSON.parse_string(FileAccess.get_file_as_string(control + "/" + name + ".json")) if FileAccess.file_exists(control + "/" + name + ".json") else {}

func pending_checks(game, receipt_id: String, match_id: String, phase: String) -> void:
	await game.refresh_lobby()
	check(game.settlement.is_empty() and game.lobby.get("unfinishedSettlement") == null, phase + " Pending not displayed as ready")
	check(game._settlement_match_id() == match_id, phase + " original recovery match retained")
	check(not await game.acknowledge_settlement(), phase + " no premature client completion")
	var rejected: Dictionary = await game.gateway.request("/api/v1/settlements/" + receipt_id + "/acknowledge", HTTPClient.METHOD_POST, {})
	check(not rejected.ok and int(rejected.get("status", 0)) == 409, phase + " actual pending ACK rejected 409")
	await game.prepare("Free", 0)
	check(game.preparation.is_empty(), phase + " actual next preparation rejected")
	signal_phase(phase, game)

func run() -> void:
	var game = root.get_node("Game")
	control = OS.get_environment("PR13_A05_CONTROL")
	var match_id := OS.get_environment("PR13_A05_MATCH_ID")
	game.network_telemetry.connect(func(sample: Dictionary):
		if sample.get("type", "") in ["http", "http_attempt"]: http_observations.append(sample.duplicate(true)))
	game.gateway.persist_session = false
	game.gateway.device_id = OS.get_environment("PR13_A05_DEVICE_ID")
	await game.login(OS.get_environment("FANTASYCARD_SERVER_URL"), "A05Runtime")
	var end := Time.get_ticks_msec() + 10000
	while (not game.gateway.online or str(game.room.get("player", {}).get("phase", "")) != "ActionBar") and Time.get_ticks_msec() < end: await process_frame
	check(game.gateway.online and game._settlement_match_id() == match_id, "actual PB login/bootstrap/WS recovered Running M")
	signal_phase("running", game)
	await wait_control("extract")
	check(game.command("action.extract"), "legal production extract command sent")
	var pending := await wait_control("pending")
	end = Time.get_ticks_msec() + 5000
	while str(game.room.get("player", {}).get("phase", "")) != "Extracted" and game._settlement_recovery_match_id != match_id and Time.get_ticks_msec() < end: await process_frame
	await pending_checks(game, str(pending.get("receipt_id", "")), match_id, "pending-before-restart")
	await wait_control("restarted")
	end = Time.get_ticks_msec() + 10000
	while not game.gateway.online and Time.get_ticks_msec() < end: await process_frame
	check(game.gateway.online, "production Gateway automatically reconnects after OS restart")
	await pending_checks(game, str(pending.get("receipt_id", "")), match_id, "pending-after-restart")
	await wait_control("released")
	end = Time.get_ticks_msec() + 10000
	while game.settlement.is_empty() and Time.get_ticks_msec() < end:
		await process_frame
	check(str(game.settlement.get("settlementId", "")) == str(pending.get("receipt_id", "")), "release exposes same durable receipt")
	check(str(game.settlement.get("matchId", "")) == match_id, "release preserves M ownership")
	signal_phase("ready", game)
	check(await game.acknowledge_settlement(), "actual production ACK completes")
	check(game.settlement.is_empty() and game._settlement_match_id().is_empty() and not game.busy, "confirmed M cleared")
	await game.prepare("Free", 0)
	check(not game.preparation.is_empty(), "next preparation permitted only after completion")
	await game.cancel_preparation()
	check(game.preparation.is_empty(), "next preparation cleanup via actual API")
	signal_phase("completed", game)
	game.gateway.end_session("", false)
	var report := {"ok": failures.is_empty(), "failures": failures, "observations": observations, "http_observations": http_observations}
	FileAccess.open(control + "/result.json", FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	print("PR13_A05_RESULT " + JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
