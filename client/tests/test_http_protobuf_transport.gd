extends SceneTree
const Gateway = preload("res://network/gateway.gd")
class SwitchingGateway extends "res://network/gateway.gd":
	var decoding := false
	var switched_during_decode := false
	func _decode_http_response(contract: Dictionary, status: int, headers: PackedStringArray, body: PackedByteArray) -> Dictionary:
		decoding = true
		call_deferred("_switch_while_decoding")
		var value: Dictionary = await super._decode_http_response(contract, status, headers, body)
		decoding = false
		return value
	func _switch_while_decoding() -> void:
		switched_during_decode = decoding
		end_session("",false)
		accept_session("next-session", "2099-01-01T00:00:00Z", "next-player")
var failures := []
var checks := 0
var late: Dictionary = {}
var flights: Dictionary = {}
var origin_samples: Array = []
func check(condition: bool, label: String) -> void:
	print("HTTP fixture: ", label, " = ", condition)
	checks += 1
	if not condition: failures.append(label)
func _initialize() -> void: call_deferred("run")
func _late_request(gateway: Node) -> void:
	late = await gateway.request("/api/v1/players/me?late=1", HTTPClient.METHOD_GET, null, [401])
func _flight_request(gateway: Node, path: String, name: String) -> void:
	flights[name] = await gateway.request(path)
func run() -> void:
	var gateway := Gateway.new()
	gateway.use_reusable_http = OS.get_environment("FANTASYCARD_LOAD_HTTP_TRANSPORT") != "per-request"
	gateway.persist_session = false
	root.add_child(gateway)
	gateway.base_url = "http://127.0.0.1:38971"
	var login: Dictionary = await gateway.request("/api/v1/auth/local", HTTPClient.METHOD_POST, {"displayName":"fixture", "deviceId":"fixture-device"})
	check(login.ok, "binary login")
	check(gateway.accept_session(login.data.accessToken, login.data.expiresAt, login.data.player.userId), "accept session")
	var bootstrap: Dictionary = await gateway.request("/api/v1/bootstrap")
	check(bootstrap.ok and bootstrap.data.wallet.gold == 9223372036854775807, "binary bootstrap int64")
	check(bootstrap.data.market.size() == 2 and bootstrap.data.mail.items.size() == 2 and bootstrap.data.mail.unreadCount == 3, "embedded market/mail pagination")
	check(bootstrap.data.unfinishedMatch == null and bootstrap.data.unfinishedSettlement == null, "bootstrap absence")
	var market: Dictionary = await gateway.request("/api/v1/market/")
	check(market.ok and market.data.size() == 2, "root market pagination")
	var bad_cursor: Dictionary = await gateway.request("/api/v1/market?loop=1", HTTPClient.METHOD_GET, null, [0])
	check(not bad_cursor.ok and not bad_cursor.has("data"), "invalid pagination cursor rejects partial data")
	var too_many: Dictionary = await gateway.request("/api/v1/market?many=1", HTTPClient.METHOD_GET, null, [0])
	check(not too_many.ok and not too_many.has("data"), "aggregate limit rejects partial data")
	var profile: Dictionary = await gateway.request("/api/v1/players/me")
	check(profile.ok and profile.data.version == 9223372036854775807, "profile int64")
	var purchase: Dictionary = await gateway.request("/api/v1/shop/purchases", HTTPClient.METHOD_POST, {"productId":"p","quantity":1})
	check(purchase.ok and purchase.data.goldAfter == 9223372036854775807, "429 retry")
	var empty: Dictionary = await gateway.request("/api/v1/mail/read-all", HTTPClient.METHOD_POST, {})
	check(empty.ok and empty.data == null, "204 response")
	gateway.telemetry.connect(func(sample): origin_samples.append(sample.duplicate(true)))
	gateway.telemetry_context = {"cycle_id": "first-cycle", "phase": "playing"}
	_flight_request(gateway, "/api/v1/players/me?flight=join", "joined-a")
	_flight_request(gateway, "/api/v1/players/me?flight=join", "joined-b")
	await create_timer(.6).timeout
	check(flights.get("joined-a", {}).get("ok", false) and flights.get("joined-b", {}).get("ok", false) and flights["joined-a"].data == flights["joined-b"].data, "GET join returns the actual result to both callers")
	_flight_request(gateway, "/api/v1/players/me?flight=epoch", "old-read")
	await create_timer(.03).timeout
	await gateway.request("/api/v1/mail/read-all", HTTPClient.METHOD_POST, {})
	gateway.telemetry_context = {"cycle_id": "next-cycle", "phase": "settlement"}
	_flight_request(gateway, "/api/v1/players/me?flight=epoch", "new-read")
	await create_timer(.7).timeout
	check(flights.get("old-read", {}).get("ok", false) and flights.get("new-read", {}).get("ok", false) and flights["old-read"].data.version == 1 and flights["new-read"].data.version == 2, "post-write GET cannot join a pre-write flight")
	check(origin_samples.any(func(sample): return sample.get("type") == "http" and sample.get("path") == "/api/v1/players/me?flight=epoch" and sample.get("cycle_id") == "first-cycle"), "late HTTP completion retains the initiating cycle")
	var malformed: Dictionary = await gateway.request("/api/v1/shop/purchases?malformed=1", HTTPClient.METHOD_POST, {"productId":"p"}, [200])
	check(not malformed.ok, "malformed write fails")
	var proxy: Dictionary = await gateway.request("/api/v1/cards", HTTPClient.METHOD_GET, null, [200])
	check(not proxy.ok, "proxy HTML fails")
	gateway.connect_realtime()
	await create_timer(.4).timeout
	gateway.reconnect_enabled = false
	var stats: Dictionary = await gateway.request("/api/v1/client-info")
	check(stats.ok and stats.data.retryStable, "stable request bytes/key across retry")
	check(stats.data.counts.get("/api/v1/shop/purchases?malformed=1",0) == 1, "no retry on malformed write")
	check(stats.data.counts.get("/api/v1/cards",0) == 1, "no fallback on proxy error")
	check(stats.data.websocketSafe, "ticket URL without bearer")
	check(stats.data.counts.get("/api/v1/players/me?flight=join", 0) == 1, "GET join sends one transport request")
	check(stats.data.counts.get("/api/v1/players/me?flight=epoch", 0) == 2, "write invalidation creates a new transport request")
	var switching := SwitchingGateway.new()
	switching.use_reusable_http = gateway.use_reusable_http
	switching.persist_session = false
	root.add_child(switching)
	switching.base_url = gateway.base_url
	var abandoned: Dictionary = await switching.request("/api/v1/cards?large=1")
	check(switching.switched_during_decode and abandoned.get("stale_session",false) and switching.token == "next-session", "background decode result cannot cross session generation")
	switching.end_session("",false)
	switching.queue_free()
	_late_request(gateway)
	await create_timer(.05).timeout
	gateway.end_session("",false)
	gateway.accept_session("new-token", "2099-01-01T00:00:00Z", "new-user")
	await create_timer(.7).timeout
	check(late.get("stale_session",false) and gateway.token == "new-token", "old 401 callback suppressed")
	gateway.end_session("", false)
	gateway.queue_free()
	await process_frame
	print(JSON.stringify({"checks":checks,"failures":failures}))
	quit(0 if failures.is_empty() else 1)
