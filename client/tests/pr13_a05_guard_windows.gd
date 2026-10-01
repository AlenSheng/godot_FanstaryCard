extends SceneTree

var failures: Array = []
var observations: Array = []
var control: String
var ack_done := false
var ack_result := false

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, label: String) -> void:
	observations.append({"check": label, "passed": value, "monotonic_ms": Time.get_ticks_msec()})
	if not value: failures.append(label)

func phase(name: String, game) -> void:
	var path := control + "/" + name + ".json"
	var file := FileAccess.open(path + ".tmp", FileAccess.WRITE)
	file.store_string(JSON.stringify({"monotonic_ms": Time.get_ticks_msec(), "match_id": game._settlement_match_id(),
		"recovery_match_id": game._settlement_recovery_match_id, "settlement": game.settlement.duplicate(true),
		"busy": game.busy, "pending_ack": game._settlement_ack_pending_id, "polling": game._settlement_polling,
		"context_epoch": game._room_context_epoch, "generation": game.gateway.session_generation,
		"lobby_unfinished_settlement": game.lobby.get("unfinishedSettlement")}, "\t"))
	file.close()
	check(DirAccess.rename_absolute(path + ".tmp", path) == OK, "atomic phase " + name)

func wait_control(name: String) -> Dictionary:
	var end := Time.get_ticks_msec() + 30000
	while not FileAccess.file_exists(control + "/" + name + ".json") and Time.get_ticks_msec() < end: await process_frame
	check(FileAccess.file_exists(control + "/" + name + ".json"), "owned control " + name)
	return JSON.parse_string(FileAccess.get_file_as_string(control + "/" + name + ".json")) if FileAccess.file_exists(control + "/" + name + ".json") else {}

func acknowledge(game) -> void:
	ack_result = await game.acknowledge_settlement()
	ack_done = true
	phase("ack-returned", game)

func run() -> void:
	control = OS.get_environment("PR13_A05_CONTROL")
	var game = root.get_node("Game")
	var match_id := OS.get_environment("PR13_A05_MATCH_ID")
	game.gateway.persist_session = false
	game.gateway.device_id = OS.get_environment("PR13_A05_DEVICE_ID")
	await game.login(OS.get_environment("FANTASYCARD_SERVER_URL"), "A05Runtime")
	var end := Time.get_ticks_msec() + 10000
	while (not game.gateway.online or not game.allowed("action.extract")) and Time.get_ticks_msec() < end: await process_frame
	check(game.gateway.online and game._settlement_match_id() == match_id, "actual Running M entry")
	phase("running", game)
	var scenario := await wait_control("extract")
	var context := str(scenario.get("context", ""))
	var outcome := str(scenario.get("outcome", ""))
	check(game.command("action.extract"), "actual legal extraction")
	if context == "recovered":
		await wait_control("restarted")
		end = Time.get_ticks_msec() + 10000
		while (not game.gateway.online or game._settlement_recovery_match_id != match_id) and Time.get_ticks_msec() < end: await process_frame
		check(game.gateway.online and game._settlement_recovery_match_id == match_id, "actual OS restart establishes recovery M")
	else:
		await wait_control("ordinary-pending")
		end = Time.get_ticks_msec() + 10000
		while str(game.room.get("player", {}).get("phase", "")) != "Extracted" and Time.get_ticks_msec() < end: await process_frame
		check(game.gateway.online and game._settlement_recovery_match_id.is_empty() and game._settlement_match_id() == match_id,
			"ordinary terminal M has no recovery M")
	check(game.settlement.is_empty(), "Pending holds expose no completed receipt")
	phase("context-ready", game)
	await wait_control("get-released")
	end = Time.get_ticks_msec() + 10000
	while game.settlement.is_empty() and Time.get_ticks_msec() < end: await process_frame
	check(not game.settlement.is_empty() and game._settlement_polling, "actual GET loads M with actual ready poll still awaited")
	check(game._settlement_recovery_match_id == (match_id if context == "recovered" else ""), "distinct ordinary/recovery context retained")
	var receipt: Dictionary = game.settlement.duplicate(true)
	acknowledge(game)
	await wait_control("ack-held")
	check(game.busy and game.settlement.is_empty() and game._settlement_ack_pending_id == str(receipt.get("settlementId", "")), "actual ACK optimistic clear pending")
	phase("ack-cleared", game)
	await wait_control("poll-released")
	end = Time.get_ticks_msec() + 10000
	while game._settlement_polling and Time.get_ticks_msec() < end: await process_frame
	check(not game._settlement_polling and game.busy and game.settlement.is_empty(), "old ready poll cannot refill receipt during ACK")
	phase("poll-returned-during-ack", game)
	await wait_control("ack-released")
	while not ack_done: await process_frame
	if outcome == "uncommitted-loss":
		check(not ack_result and not game.busy and game.settlement == receipt, "uncommitted ACK loss restores exact retryable receipt")
		phase("ack-failed-restored", game)
		await wait_control("ack-retry")
		check(await game.acknowledge_settlement(), "production retry ACK succeeds after releasing transport fault")
	else:
		check(ack_result, "ACK success or committed loss confirmed by authoritative Bootstrap")
	check(game.settlement.is_empty() and not game.busy and game._settlement_ack_pending_id.is_empty(), "confirmed receipt remains cleared")
	check(game.lobby.get("unfinishedSettlement") == null and game._settlement_recovery_match_id.is_empty(), "actual post-ACK Bootstrap completed state")
	phase("confirmed", game)
	await game.prepare("Free", 0)
	check(not game.preparation.is_empty(), "actual next preparation succeeds")
	await game.cancel_preparation()
	check(game.preparation.is_empty(), "actual next preparation cancellation clears")
	game.gateway.end_session("", false)
	var report := {"ok": failures.is_empty(), "context": context, "outcome": outcome, "failures": failures,
		"observations": observations, "first_ack_result": ack_result, "final_settlement_empty": game.settlement.is_empty()}
	FileAccess.open(control + "/result.json", FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	print("PR13_A05_GUARD " + JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
