extends SceneTree

# Calls the production autoload against an owned full host. The test proxy only
# removes HTTP responses; it never fabricates login, Bootstrap or ACK payloads.
var failures: Array = []
var observations: Array = []
var http_observations: Array = []

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, label: String) -> void:
	observations.append({"check": label, "passed": value})
	if not value: failures.append(label)

func run() -> void:
	var game = root.get_node("Game")
	var address := OS.get_environment("FANTASYCARD_SERVER_URL")
	var mode := OS.get_environment("PR13_ACK_FAULT_MODE")
	game.network_telemetry.connect(func(sample: Dictionary):
		if sample.get("type", "") in ["http", "http_attempt"]:
			http_observations.append(sample.duplicate(true)))
	game.gateway.persist_session = false
	game.gateway.device_id = OS.get_environment("PR13_ACK_DEVICE_ID")
	await game.login(address, "AckFault")
	check(not game.lobby.is_empty() and not game.gateway.token.is_empty(), "actual PB login/bootstrap")
	var receipt: Dictionary = game.settlement.duplicate(true)
	check(str(receipt.get("settlementId", "")) == OS.get_environment("PR13_ACK_RECEIPT_ID"), "actual durable receipt loaded")
	check(str(receipt.get("matchId", "")) == OS.get_environment("PR13_ACK_MATCH_ID"), "receipt match ownership")
	observations.append({"before_ack_busy": game.busy, "session_generation": game.gateway.session_generation})
	var first: bool = await game.acknowledge_settlement()
	if mode == "drop-all-uncommitted":
		check(not first, "uncommitted timeout cannot report completion")
		check(game.settlement == receipt and not game.busy, "uncommitted timeout restores exact retryable receipt")
		var control := HTTPRequest.new()
		root.add_child(control)
		check(control.request(address + "/__faults/release", [], HTTPClient.METHOD_POST) == OK, "release owned fault controller")
		var released: Array = await control.request_completed
		check(int(released[1]) == 204, "fault released without backend data mutation")
		control.queue_free()
		var retried: bool = await game.acknowledge_settlement()
		check(retried, "actual retry ACK succeeds")
	else:
		check(first, "committed ACK recovered after response loss")
	check(game.settlement.is_empty() and not game.busy, "confirmed receipt cleared")
	check(game.lobby.get("unfinishedSettlement") == null, "authoritative Bootstrap excludes acknowledged receipt")
	check(not await game.acknowledge_settlement(), "duplicate client completion suppressed")
	game.gateway.end_session("", false)
	var report := {"ok": failures.is_empty(), "mode": mode, "failures": failures, "observations": observations, "http_observations": http_observations,
		"source": "production GameStore/Gateway/HttpProtocol with full Program and isolated PostgreSQL",
		"limitations": ["seeded terminal route; not full exploration", "OFFLINE+POSTGRES; LIVE/RENDER not exercised", "load-runner cycle accounting belongs to separate matrix"]}
	FileAccess.open(OS.get_environment("PR13_ACK_RESULT"), FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	print("PR13_ACK_RESULT " + JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
