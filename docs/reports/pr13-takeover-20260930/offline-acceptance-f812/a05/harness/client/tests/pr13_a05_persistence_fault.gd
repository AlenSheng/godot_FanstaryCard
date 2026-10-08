extends SceneTree

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
	FileAccess.open(control + "/" + name + ".json", FileAccess.WRITE).store_string(JSON.stringify({"match_id": game._settlement_match_id(),
		"recovery_match_id": game._settlement_recovery_match_id, "settlement": game.settlement.duplicate(true), "busy": game.busy,
		"room": game.room.duplicate(true), "gateway_room_id": game.gateway.room_id}, "\t"))

func wait_control(name: String) -> Dictionary:
	var end := Time.get_ticks_msec() + 60000
	while not FileAccess.file_exists(control + "/" + name + ".json") and Time.get_ticks_msec() < end: await process_frame
	check(FileAccess.file_exists(control + "/" + name + ".json"), "owned control " + name)
	return JSON.parse_string(FileAccess.get_file_as_string(control + "/" + name + ".json")) if FileAccess.file_exists(control + "/" + name + ".json") else {}

func run() -> void:
	control = OS.get_environment("PR13_A05_CONTROL")
	var game = root.get_node("Game")
	var match_id := OS.get_environment("PR13_A05_MATCH_ID")
	game.network_telemetry.connect(func(sample: Dictionary):
		if sample.get("type", "") in ["http", "http_attempt"]: http_observations.append(sample.duplicate(true)))
	game.gateway.persist_session = false
	game.gateway.device_id = OS.get_environment("PR13_A05_DEVICE_ID")
	await game.login(OS.get_environment("FANTASYCARD_SERVER_URL"), "A05Runtime")
	var end := Time.get_ticks_msec() + 10000
	while (not game.gateway.online or not game.allowed("action.extract")) and Time.get_ticks_msec() < end: await process_frame
	check(game.gateway.online and game._settlement_match_id() == match_id, "actual Running M recovered")
	signal_phase("running", game)
	await wait_control("extract")
	check(game.command("action.extract"), "actual legal extraction")
	var fault := await wait_control("fault")
	if str(fault.get("mode", "")) == "precommit":
		end = Time.get_ticks_msec() + 5000
		while str(game.room.get("player", {}).get("phase", "")) != "Extracted" and Time.get_ticks_msec() < end: await process_frame
		await game.refresh_lobby()
		check(game.settlement.is_empty() and game.lobby.get("unfinishedSettlement") == null, "failed settlement transaction cannot expose completed receipt")
		check(game._settlement_match_id() == match_id, "precommit failure retains retryable M")
		check(not await game.acknowledge_settlement(), "precommit failure cannot complete client ACK")
	signal_phase("fault-observed", game)
	var released := await wait_control("released")
	end = Time.get_ticks_msec() + 10000
	while str(game.settlement.get("settlementId", "")) != str(released.get("receipt_id", "")) and Time.get_ticks_msec() < end:
		await process_frame
	observations.append({"expected_receipt_id": released.get("receipt_id"), "actual_receipt_id": game.settlement.get("settlementId"), "loading": game._settlement_loading})
	check(str(game.settlement.get("settlementId", "")) == str(released.get("receipt_id", "")), "same actual durable receipt recovered")
	check(str(game.settlement.get("matchId", "")) == match_id, "recovered receipt owns M")
	signal_phase("ready", game)
	await wait_control("ack")
	check(await game.acknowledge_settlement(), "production completion succeeds after confirmed persistence")
	check(game.settlement.is_empty() and not game.busy, "only confirmed completion clears receipt")
	signal_phase("completed", game)
	game.gateway.end_session("", false)
	var report := {"ok": failures.is_empty(), "failures": failures, "observations": observations, "http_observations": http_observations}
	FileAccess.open(control + "/result.json", FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	print("PR13_A05_RESULT " + JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
