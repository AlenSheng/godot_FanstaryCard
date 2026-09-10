extends SceneTree

var game: Node
var checks: Dictionary = {}
var late_response: Dictionary = {}

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	game = root.get_node("Game")
	var base := OS.get_environment("FANTASYCARD_SESSION_TEST_URL")
	if not base.begins_with("http://127.0.0.1:"):
		quit(2)
		return
	game.gateway.persist_session = false
	game.gateway.device_id = "isolated-session-fixture"
	await game.login(base, "Session fixture")
	_stop_socket()
	checks.login = not game.lobby.is_empty() and not game.gateway.token.is_empty()
	game.room = {"room_id": "stale-room"}
	game.selected_cards = ["stale-card"]
	var unauthorized: Dictionary = await game.gateway.request("/unauthorized")
	checks.unauthorized = not unauthorized.ok and game.lobby.is_empty() and game.room.is_empty() and game.selected_cards.is_empty() and not game.gateway.reconnect_enabled
	await game.login(base, "Session fixture")
	_stop_socket()
	checks.relogin = not game.lobby.is_empty() and game.authentication_reason.is_empty()
	var proto = load("res://network/protobuf.gd").new()
	game.gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "session.replaced", "sequence": 1, "payload": proto.encode("SessionReplacedEvent", {"reason": "replacement fixture"})}))
	checks.replaced = game.lobby.is_empty() and game.gateway.token.is_empty() and not game.gateway.reconnect_enabled
	await game.login(base, "Session fixture")
	_stop_socket()
	_delayed_request()
	await create_timer(0.05).timeout
	game.gateway.end_session("fixture expiry")
	await game.login(base, "Session fixture")
	_stop_socket()
	var generation: int = game.gateway.session_generation
	while late_response.is_empty(): await process_frame
	checks.stale_response = not late_response.ok and late_response.get("stale_session", false) and not game.lobby.is_empty() and generation == game.gateway.session_generation
	await game.login(base + "/mismatch", "Session fixture")
	checks.server_mismatch = game.lobby.is_empty() and not game.configuration_error.is_empty() and game.gateway.token.is_empty()
	await game.login(base + "/bootstrap-mismatch", "Session fixture")
	checks.bootstrap_mismatch = game.lobby.is_empty() and not game.configuration_error.is_empty() and game.gateway.token.is_empty()
	await game.login(base, "Session fixture")
	_stop_socket()
	checks.recovered_matching_config = not game.lobby.is_empty() and game.configuration_error.is_empty()
	game.logout()
	checks.logout = game.lobby.is_empty() and game.gateway.token.is_empty() and not game.busy
	var ok := checks.values().all(func(value): return value == true)
	print(JSON.stringify({"session_integration": true, "ok": ok, "checks": checks}))
	quit(0 if ok else 1)

func _stop_socket() -> void:
	game.gateway.reconnect_enabled = false
	game.gateway.socket.close()

func _delayed_request() -> void:
	late_response = await game.gateway.request("/late-unauthorized")
