extends SceneTree

var failures: Array = []
var observations: Array = []
var http_observations: Array = []
var control: String
var ack_done := false
var ack_result := false

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, label: String) -> void:
	observations.append({"check": label, "passed": value, "monotonic_ms": Time.get_ticks_msec()})
	if not value: failures.append(label)

func signal_phase(name: String, game) -> void:
	var file := FileAccess.open(control + "/" + name + ".json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"monotonic_ms": Time.get_ticks_msec(), "match_id": game._settlement_match_id(),
		"recovery_match_id": game._settlement_recovery_match_id, "settlement": game.settlement.duplicate(true), "busy": game.busy,
		"pending_ack": game._settlement_ack_pending_id, "polling": game._settlement_polling, "context_epoch": game._room_context_epoch,
		"generation": game.gateway.session_generation, "lobby_unfinished_settlement": game.lobby.get("unfinishedSettlement")}, "\t"))
	file.close()

func wait_control(name: String) -> Dictionary:
	var end := Time.get_ticks_msec() + 30000
	while not FileAccess.file_exists(control + "/" + name + ".json") and Time.get_ticks_msec() < end: await process_frame
	check(FileAccess.file_exists(control + "/" + name + ".json"), "owned control " + name)
	return JSON.parse_string(FileAccess.get_file_as_string(control + "/" + name + ".json")) if FileAccess.file_exists(control + "/" + name + ".json") else {}

func acknowledge(game) -> void:
	ack_result = await game.acknowledge_settlement()
	ack_done = true
	signal_phase("ack-returned", game)

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
	check(game.gateway.online and game._settlement_match_id() == match_id, "actual Running M entry")
	signal_phase("running", game)
	await wait_control("extract")
	check(game.command("action.extract"), "actual legal extraction")
	await wait_control("restarted")
	end = Time.get_ticks_msec() + 10000
	while (not game.gateway.online or game._settlement_recovery_match_id != match_id) and Time.get_ticks_msec() < end: await process_frame
	check(game.gateway.online and game._settlement_recovery_match_id == match_id, "actual Pending OS restart/NOT_IN_ROOM retains recovery M")
	signal_phase("recovery-M", game)
	await wait_control("get-released")
	end = Time.get_ticks_msec() + 5000
	while game.settlement.is_empty() and Time.get_ticks_msec() < end: await process_frame
	check(not game.settlement.is_empty() and game._settlement_polling and game._settlement_recovery_match_id == match_id, "actual GET loaded M with recovery M while production poll remains awaited")
	var receipt: Dictionary = game.settlement.duplicate(true)
	acknowledge(game)
	await wait_control("ack-held")
	check(game.busy and game.settlement.is_empty() and game._settlement_ack_pending_id == str(receipt.get("settlementId", "")), "real ACK await performs optimistic clear")
	signal_phase("ack-cleared", game)
	await wait_control("poll-released")
	end = Time.get_ticks_msec() + 3000
	while game._settlement_polling and Time.get_ticks_msec() < end: await process_frame
	signal_phase("poll-returned-during-ack", game)
	var stale_during_ack: bool = game.busy and game.settlement == receipt
	observations.append({"stale_during_ack": stale_during_ack, "monotonic_ms": Time.get_ticks_msec()})
	await wait_control("ack-released")
	end = Time.get_ticks_msec() + 5000
	while not ack_done and Time.get_ticks_msec() < end: await process_frame
	check(ack_done and ack_result, "actual production ACK returns success")
	check(game.lobby.get("unfinishedSettlement") == null and not game.busy, "actual post-ACK Bootstrap confirms completion")
	var stale_after_ack: bool = game.settlement == receipt
	observations.append({"stale_after_ack": stale_after_ack, "monotonic_ms": Time.get_ticks_msec()})
	signal_phase("stale-final", game)
	await game.prepare("Free", 0)
	check(not game.preparation.is_empty(), "actual next preparation allowed while stale receipt remains")
	await game.cancel_preparation()
	game.gateway.end_session("", false)
	var report := {"ok": failures.is_empty(), "counterexample_confirmed": stale_during_ack and stale_after_ack,
		"stale_during_ack": stale_during_ack, "stale_after_ack": stale_after_ack,
		"failures": failures, "observations": observations, "http_observations": http_observations}
	FileAccess.open(control + "/result.json", FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	print("PR13_A05_CAUSAL " + JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
