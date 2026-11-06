extends SceneTree

const Gateway = preload("res://network/gateway.gd")
const Platform = preload("res://platform/platform_service.gd")
const P = preload("res://ui/palette.gd")

class LoginPlatform extends "res://platform/platform_service.gd":
	# The wire fixture exercises local loopback auth independently of the
	# release build's disabled local-account entry and real Steam SDK.
	func local_login_enabled() -> bool: return true

class LoginStore extends "res://state/game_store.gd":
	func _ready() -> void: pass
	func _process_client_info() -> void: pass

class DelayedGateway extends "res://network/gateway.gd":
	var release := false
	var calls: Array = []
	func request(path: String, _method: int = HTTPClient.METHOD_GET, _data: Variant = null, _quiet: Array = []) -> Dictionary:
		calls.append(path)
		while not release: await get_tree().process_frame
		# Deliberately return success after cancellation, to exercise the store's
		# ownership checks independently of the real gateway's stale-session result.
		if path == "/api/v1/client-info":
			return {"ok": true, "data": {"configVersion": str(LoginStore.CATALOG.data.version), "capabilities": ["identity.local"]}}
		if path == "/api/v1/bootstrap":
			return {"ok": true, "data": {"configVersion": str(LoginStore.CATALOG.data.version), "player": {"userId": "late-user"}, "wallet": {}, "materials": {}, "mail": {}, "shop": {}, "market": [], "inventory": {}, "activePreparation": null}}
		return {"ok": true, "data": {"accessToken": "late-token", "expiresAt": "2099-01-01T00:00:00Z", "player": {"userId": "late-user"}}}
	func connect_realtime() -> void:
		online = true

var checks := {}
var completed := 0

func _initialize() -> void: _run.call_deferred()

func _store(gateway: Node) -> Node:
	var store := LoginStore.new()
	root.add_child(store)
	gateway.persist_session = false
	store.gateway = gateway
	store.add_child(gateway)
	store.platform = LoginPlatform.new()
	store.add_child(store.platform)
	gateway.connection_changed.connect(store._on_connection_changed)
	gateway.authentication_required.connect(store._on_authentication_required)
	return store

func _login(store: Node, address: String) -> void:
	await store.login(address, "Timeout1234")
	completed += 1

func _run() -> void:
	# Avoid the normal autoload's public client-info polling during this fixture.
	root.get_node("Game").set_process(false)
	root.get_node("Game").gateway.end_session("", false)
	root.get_node("Sound").persist_settings = false
	var host: Control = load("res://main.tscn").instantiate()
	host.set_script(load("res://tests/steam_ui_main_fixture.gd"))
	host.fixture_ready = true
	root.add_child(host)
	var live_game := root.get_node("Game")
	var original_gateway: Node = live_game.gateway
	var gateway := Gateway.new()
	var store := _store(gateway)
	# Bind the real login UI to this isolated test session.
	live_game.gateway = gateway
	store.changed.connect(func():
		live_game.busy = store.busy
		live_game.lobby = store.lobby
		live_game.authentication_reason = store.authentication_reason
		host._render()
	)
	var listener := TCPServer.new()
	assert(listener.listen(0, "127.0.0.1") == OK)
	var address := "http://127.0.0.1:" + str(listener.get_local_port())
	var started := Time.get_ticks_msec()
	_login(store, address)
	checks["login disables buttons while waiting"] = store.busy and _login_buttons_disabled(host, true)
	var peer: StreamPeerTCP
	while store.busy and Time.get_ticks_msec() - started < 12000:
		if listener.is_connection_available(): peer = listener.take_connection()
		await process_frame
	var elapsed := Time.get_ticks_msec() - started
	checks["silent TCP server is disconnected at the 10 second login deadline"] = peer != null and not store.busy and elapsed >= 10000 and elapsed < 11500
	checks["timeout clears session and stops realtime retries"] = gateway.token.is_empty() and not gateway.online and not gateway.reconnect_enabled and gateway.socket.get_ready_state() == WebSocketPeer.STATE_CLOSED
	checks["timeout is explained and login buttons are clickable again"] = store.authentication_reason == P.localized("login_timeout") and _login_buttons_disabled(host, false)
	await process_frame
	await process_frame
	checks["timeout cancels the native HTTP request without waiting for retries"] = gateway._pending_http.is_empty() and not gateway._reusable_http.busy and gateway._reusable_http._client == null and completed == 1
	if peer != null: peer.disconnect_from_host()
	listener.stop()
	# The same login action can immediately be retried against a stopped server.
	started = Time.get_ticks_msec()
	_login(store, address)
	checks["a new login can start immediately"] = store.busy
	while store.busy and Time.get_ticks_msec() - started < 11000: await process_frame
	checks["a stopped server restores buttons within the deadline"] = not store.busy and _login_buttons_disabled(host, false) and not gateway.reconnect_enabled
	live_game.gateway = original_gateway
	store.queue_free()
	host.queue_free()
	await process_frame
	# Cover a response arriving after the old login has timed out and a new
	# session has already started, at both discovery and authentication awaits.
	for stage in ["discovery", "authentication"]:
		var delayed := DelayedGateway.new()
		var delayed_store := _store(delayed)
		if stage == "authentication":
			delayed_store.server_info = {"configVersion": str(LoginStore.CATALOG.data.version), "capabilities": ["identity.local"]}
			delayed_store._server_info_address = address
		_login(delayed_store, address)
		delayed_store._login_deadline = Time.get_ticks_msec() - 1
		delayed_store._check_login_timeout()
		delayed.begin_sign_in(address)
		delayed.accept_session("new-token", "2099-01-01T00:00:00Z", "new-user")
		delayed_store.busy = true
		delayed_store._login_generation = delayed.session_generation
		delayed_store._login_deadline = Time.get_ticks_msec() + 10000
		delayed.release = true
		await process_frame
		await process_frame
		checks[stage + ": late success cannot replace the next session or reset its buttons"] = delayed.token == "new-token" and delayed_store.busy and delayed_store._login_deadline > 0 and delayed.calls.size() == 1
		checks[stage + ": late discovery cannot replace server metadata"] = stage != "discovery" or delayed_store.server_info.is_empty()
		delayed_store.queue_free()
		await process_frame
	var healthy := DelayedGateway.new()
	healthy.release = true
	var healthy_store := _store(healthy)
	await healthy_store.login(address, "Healthy1234")
	checks["successful login clears the watchdog and enters the lobby"] = not healthy_store.busy and healthy_store._login_deadline == 0 and not healthy_store.lobby.is_empty() and healthy.online
	var healthy_generation: int = healthy.session_generation
	healthy_store._check_login_timeout()
	checks["completed login cannot later be disconnected by its watchdog"] = healthy.session_generation == healthy_generation and healthy.token == "late-token"
	healthy_store.queue_free()
	await process_frame
	# Existing session/retry policy must continue to pass with cancellation enabled.
	for path in ["res://tests/test_session_platform.gd", "res://tests/test_http_terminal_retry.gd"]:
		var result: Dictionary = await load(path).new().run_test()
		checks[path] = result.get("ok", false)
	var report := {"ok": not checks.values().has(false), "checks": checks, "silent_server_elapsed_ms": elapsed, "scope": "Godot login UI and real loopback HTTP; delayed response fixtures"}
	print(JSON.stringify(report))
	P.clear_runtime_fonts()
	quit(0 if report.ok else 1)

func _login_buttons_disabled(host: Node, disabled: bool) -> bool:
	var entry: Button = host.find_child("EnterGameButton", true, false)
	if entry != null: return entry.disabled == disabled
	var count := 0
	for button in host.find_children("*", "Button", true, false):
		if button.text in [P.localized("local_dev_login"), P.localized("cloud_login"), P.localized("random_name")]:
			count += 1
			if button.disabled != disabled: return false
	return count == 3
