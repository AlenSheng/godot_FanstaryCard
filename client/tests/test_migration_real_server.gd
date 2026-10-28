extends SceneTree

const Gateway = preload("res://network/gateway.gd")
var checks := []
var received := []
var failures := []
var gateway: Node
var replacement: Node

func _initialize() -> void: call_deferred("run")
func check(value: bool, name: String) -> bool:
	checks.append({"name":name,"passed":value})
	if not value: failures.append(name)
	return value
func wait_until(predicate: Callable, seconds: float = 8.0) -> bool:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000)
	while not predicate.call() and Time.get_ticks_msec() < deadline:
		await process_frame
	return predicate.call()
func on_event(kind: String, payload: Dictionary) -> void:
	# Capture only noncredential fields needed for assertions.
	received.append({"kind":kind,"request":str(payload.get("_request_id", "")),"replayed":bool(payload.get("_replayed", false))})
func has_pong(id: String, replayed: bool = false) -> bool:
	return received.any(func(event): return event.kind == "pong" and event.request == id and event.replayed == replayed)
func close_socket(peer: WebSocketPeer) -> void:
	peer.close()
	var deadline := Time.get_ticks_msec() + 2000
	while peer.get_ready_state() != WebSocketPeer.STATE_CLOSED and Time.get_ticks_msec() < deadline:
		peer.poll()
		await process_frame
func finish() -> void:
	for client in [gateway, replacement]:
		if is_instance_valid(client):
			client.reconnect_enabled = false
			await close_socket(client.socket)
			client.end_session("", false)
			client.queue_free()
	await process_frame
	print(JSON.stringify({"checks":checks,"failures":failures}))
	quit(0 if failures.is_empty() else 1)
func run() -> void:
	var address := OS.get_environment("FANTASYCARD_SERVER_URL")
	if not check(address.begins_with("http://127.0.0.1:"), "loopback only"):
		await finish(); return
	gateway = Gateway.new()
	gateway.persist_session = false
	root.add_child(gateway)
	gateway.clear_replay()
	gateway.base_url = address
	gateway.event_received.connect(on_event)
	var name: String = "PB-" + gateway.new_id().left(10)
	var login: Dictionary = await gateway.request("/api/v1/auth/local", HTTPClient.METHOD_POST, {"displayName":name,"deviceId":"protobuf-real-godot"})
	if not check(login.ok and login.get("data") is Dictionary, "real .NET binary local login"):
		await finish(); return
	if not check(gateway.accept_session(login.data.accessToken,login.data.expiresAt,login.data.player.userId), "accept real credential"):
		await finish(); return
	var lobby: Dictionary = await gateway.request("/api/v1/bootstrap")
	if not check(lobby.ok and lobby.get("data") is Dictionary, "real .NET binary bootstrap"):
		await finish(); return
	check(lobby.data.player.userId == login.data.player.userId and typeof(lobby.data.player.version) == TYPE_INT, "bootstrap player and integer version")
	check(lobby.data.unfinishedMatch == null and lobby.data.unfinishedSettlement == null, "real null message presence")
	check(lobby.data.decks.size() == 3 and lobby.data.cards.size() > 0, "bootstrap nested collections")
	# Preserve one real, noncredential gameplay sample for the scheduling benchmark.
	var sample_request := HTTPRequest.new()
	root.add_child(sample_request)
	var sample_start := sample_request.request_raw(address + "/api/v1/bootstrap", PackedStringArray(["Accept: application/protobuf", "Authorization: Bearer " + login.data.accessToken]))
	if sample_start == OK:
		var sample: Array = await sample_request.request_completed
		if sample[1] == 200:
			var sample_file := FileAccess.open("res://data/bootstrap-real.pb",FileAccess.WRITE)
			sample_file.store_buffer(sample[3])
			sample_file.close()
	sample_request.queue_free()
	var profile: Dictionary = await gateway.request("/api/v1/players/me")
	if not check(profile.ok, "real profile read"):
		await finish(); return
	var updated: Dictionary = await gateway.request("/api/v1/players/me",HTTPClient.METHOD_PUT,{"displayName":name,"selectedClass":"Mage","expectedVersion":profile.data.version})
	check(updated.ok and updated.data.selectedClass == "Mage", "real profile protobuf write")
	var decks: Dictionary = await gateway.request("/api/v1/decks")
	if not check(decks.ok and decks.data is Array and decks.data.size()==3, "real deck list unwrap"):
		await finish(); return
	var deck: Dictionary = decks.data.filter(func(item): return item.heroClass == "Mage")[0]
	var saved: Dictionary = await gateway.request("/api/v1/decks/Mage",HTTPClient.METHOD_PUT,{"cardIds":deck.cardIds,"expectedVersion":deck.version})
	check(saved.ok and saved.data.cardIds == deck.cardIds, "real deck protobuf write")
	gateway.connect_realtime()
	if not check(await wait_until(func(): return gateway.online), "ticket to real websocket session.connected"):
		await finish(); return
	check(gateway.send("ping", {}, "real-first-ping"), "real binary ping send")
	if not check(await wait_until(func(): return has_pong("real-first-ping")), "real binary pong receive"):
		await finish(); return
	var sequence: int = gateway.last_sequence
	# Stop delivery, let the real server persist a pong in its event stream, then disconnect.
	gateway.set_process(false)
	check(gateway.send("ping", {}, "real-missed-ping"), "send pending pong before disconnect")
	await create_timer(.25).timeout
	gateway.reconnect_enabled = false
	await close_socket(gateway.socket)
	check(gateway.last_sequence == sequence, "undelivered pong did not advance cursor")
	gateway.set_process(true)
	gateway.connect_realtime()
	check(await wait_until(func(): return has_pong("real-missed-ping", true) and gateway.online and not gateway.recovering), "real disconnect resume replays missed pong")
	check(gateway.last_sequence > sequence, "resume advances cursor")
	# Same valid server credential, new independently constructed client, new single-use ticket.
	replacement = Gateway.new()
	replacement.persist_session = false
	root.add_child(replacement)
	replacement.clear_replay()
	replacement.base_url = address
	replacement.accept_session(login.data.accessToken,login.data.expiresAt,login.data.player.userId)
	replacement.connect_realtime()
	check(await wait_until(func(): return replacement.online and gateway.token.is_empty()), "same account replaces old connection and clears old client")
	check(not gateway.reconnect_enabled and not gateway.online, "replaced client does not reconnect")
	await finish()
