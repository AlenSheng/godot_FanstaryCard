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
		"recovery_match_id": game._settlement_recovery_match_id, "room": game.room.duplicate(true), "settlement": game.settlement.duplicate(true),
		"gateway_room_id": game.gateway.room_id, "context_epoch": game._room_context_epoch, "load_epoch": game._settlement_load_epoch,
		"busy": game.busy, "http_observations": http_observations.duplicate(true)}, "\t"))

func wait_control(name: String) -> Dictionary:
	var end := Time.get_ticks_msec() + 60000
	while not FileAccess.file_exists(control + "/" + name + ".json") and Time.get_ticks_msec() < end: await process_frame
	check(FileAccess.file_exists(control + "/" + name + ".json"), "owned control " + name)
	return JSON.parse_string(FileAccess.get_file_as_string(control + "/" + name + ".json")) if FileAccess.file_exists(control + "/" + name + ".json") else {}

func run() -> void:
	control = OS.get_environment("PR13_A05_CONTROL")
	var game = root.get_node("Game")
	var former := OS.get_environment("PR13_A05_MATCH_ID")
	game.network_telemetry.connect(func(sample: Dictionary):
		if sample.get("type", "") in ["http", "http_attempt"]: http_observations.append(sample.duplicate(true)))
	game.gateway.persist_session = false
	game.gateway.device_id = OS.get_environment("PR13_A05_DEVICE_ID")
	await game.login(OS.get_environment("FANTASYCARD_SERVER_URL"), "A05Runtime")
	var end := Time.get_ticks_msec() + 10000
	while (not game.gateway.online or not game.allowed("action.extract")) and Time.get_ticks_msec() < end: await process_frame
	check(game.gateway.online and game._settlement_match_id() == former, "actual recovered healthy M")
	signal_phase("running", game)
	await wait_control("extract")
	check(game.command("action.extract"), "actual A extraction in M")
	end = Time.get_ticks_msec() + 10000
	while game.settlement.is_empty() and Time.get_ticks_msec() < end:
		await process_frame
	check(str(game.settlement.get("matchId", "")) == former, "actual Bootstrap ready M bypasses delayed GET")
	check(await game.acknowledge_settlement(), "A actual M ACK")
	signal_phase("acknowledged-M", game)
	await wait_control("enqueue-N")
	await game.prepare("Free", 0)
	check(not game.preparation.is_empty(), "A actual N preparation")
	await game.enqueue()
	check(not game.ticket.is_empty(), "A actual N enqueue")
	end = Time.get_ticks_msec() + 10000
	var sent_ready := false
	while game.room.is_empty() and Time.get_ticks_msec() < end:
		if not game.ready_prompt.is_empty() and not sent_ready:
			sent_ready = game.gateway.send("room.ready")
		await process_frame
	var next := str(game.room.get("match_id", ""))
	check(not next.is_empty() and next != former, "A actual READY starts new N")
	check(game.settlement.is_empty() and game._settlement_recovery_match_id.is_empty(), "new N retires M recovery ownership")
	signal_phase("running-N", game)
	await wait_control("callbacks-released")
	# The relay sends the exact old response and unchanged duplicated authority
	# frame. Await their real decode/callback, then request a real N snapshot.
	await create_timer(0.5).timeout
	game.gateway.send("room.snapshot.read")
	await create_timer(0.5).timeout
	check(game._settlement_match_id() == next and game.gateway.room_id == str(game.room.get("room_id", "")), "old M response cannot clear actual N route")
	check(game.settlement.is_empty() and game._settlement_recovery_match_id.is_empty(), "old M callback cannot resurrect terminal context")
	check(http_observations.any(func(sample): return sample.get("type", "") == "http" and str(sample.get("path", "")).begins_with("/api/v1/settlements/") and int(sample.get("status", 0)) == 200 and sample.get("match_id", "") == former), "delayed actual M HTTP callback completed 200 after N")
	signal_phase("callbacks-observed", game)
	await wait_control("restart-N")
	end = Time.get_ticks_msec() + 10000
	while not game.gateway.online and Time.get_ticks_msec() < end: await process_frame
	await create_timer(0.5).timeout
	game.gateway.send("room.snapshot.read")
	await create_timer(0.5).timeout
	check(game._settlement_match_id() == next and game.gateway.room_id == str(game.room.get("room_id", "")), "actual OS recovery restores N without resurrecting terminal M")
	signal_phase("recovered-N", game)
	await wait_control("old-B-completed")
	game.gateway.send("room.snapshot.read")
	await create_timer(0.5).timeout
	check(game._settlement_match_id() == next and game.settlement.is_empty(), "healthy B completion/old room removal preserves N")
	signal_phase("old-B-observed", game)
	await wait_control("finish")
	game.gateway.end_session("", false)
	var report := {"ok": failures.is_empty(), "failures": failures, "observations": observations, "http_observations": http_observations}
	FileAccess.open(control + "/result.json", FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	print("PR13_A05_RESULT " + JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
