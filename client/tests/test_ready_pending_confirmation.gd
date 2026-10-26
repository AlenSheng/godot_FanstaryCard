extends RefCounted

class Probe extends "res://tests/gameplay_load_client.gd":
	var ready_trace: Array = []
	func _ready() -> void: set_process(false)
	func _on_telemetry(sample: Dictionary) -> void: ready_trace.append(sample.duplicate(true))
class Store extends Node:
	var room: Dictionary = {}
	var ready_prompt: Dictionary = {}
	var gateway: Node

func _open(gateway: Node, listener: TCPServer) -> WebSocketPeer:
	var peer := WebSocketPeer.new()
	var accepted := false
	gateway.socket.connect_to_url("ws://127.0.0.1:" + str(listener.get_local_port()))
	var deadline := Time.get_ticks_msec() + 3000
	while Time.get_ticks_msec() < deadline:
		gateway.socket.poll()
		if not accepted and listener.is_connection_available():
			peer.accept_stream(listener.take_connection())
			accepted = true
		if accepted: peer.poll()
		if gateway.socket.get_ready_state() == WebSocketPeer.STATE_OPEN and peer.get_ready_state() == WebSocketPeer.STATE_OPEN: break
		await Engine.get_main_loop().process_frame
	return peer

func _packets(gateway: Node, peer: WebSocketPeer) -> Array:
	var result: Array = []
	var end_ms := Time.get_ticks_msec() + 100
	while Time.get_ticks_msec() < end_ms:
		gateway.socket.poll()
		peer.poll()
		while peer.get_available_packet_count() > 0:
			result.append(load("res://network/protobuf.gd").new().decode("ClientEnvelope", peer.get_packet()))
		await Engine.get_main_loop().process_frame
	return result

func run_test() -> Dictionary:
	var checks: Dictionary = {}
	var gateway = load("res://network/gateway.gd").new()
	gateway.persist_session = false
	var store := Store.new()
	store.gateway = gateway
	var probe := Probe.new()
	probe.Game = store
	var listener := TCPServer.new()
	if listener.listen(0, "127.0.0.1") != OK:
		probe.free(); store.free(); gateway.free()
		return {"ok": false, "checks": {"owned_loopback_listener": false}}
	var peer: WebSocketPeer = await _open(gateway, listener)
	checks["owned WebSocket opens"] = gateway.socket.get_ready_state() == WebSocketPeer.STATE_OPEN
	var deadline: int = int(Time.get_unix_time_from_system() * 1000.0) + 15000
	gateway.bind_prelaunch_ticket("match", "room", deadline, 0)
	probe.active_match_id = "match"
	probe.verified_ready_match_id = "match"
	probe.ready_required = true
	probe.ready_deadline_unix_ms = deadline
	var next_send: int = probe._try_ready_confirmation("match", 0)
	var first: Array = await _packets(gateway, peer)
	checks["actual producer writes its first empty READY"] = next_send > 0 and first.size() == 1 and first[0].type == "room.ready" and probe.ready_attempts == 1 and probe.ready_successful_sends == 1
	await Engine.get_main_loop().create_timer(1.1).timeout
	probe._try_ready_confirmation("match", next_send)
	var repeated: Array = await _packets(gateway, peer)
	checks["same peer cannot repeat pending READY after original retry interval"] = repeated.is_empty() and probe.ready_attempts == 1 and probe.ready_successful_sends == 1 and probe.ready_trace.size() == 1
	var retired_socket: WebSocketPeer = gateway.socket
	retired_socket.close()
	peer.close()
	gateway.socket = WebSocketPeer.new()
	peer = await _open(gateway, listener)
	next_send = probe._try_ready_confirmation("match", next_send)
	var recovered: Array = await _packets(gateway, peer)
	checks["a replaced real peer retains bounded recovery before original deadline"] = first.size() == 1 and recovered.size() == 1 and recovered[0].type == "room.ready" and recovered[0].request_id != first[0].request_id and probe.ready_attempts == 2 and probe.ready_successful_sends == 2 and probe.ready_deadline_unix_ms == deadline
	probe._on_event("room.ready_accepted", {"match_id": "match", "room_id": "room", "deadline_unix_ms": deadline})
	probe._try_ready_confirmation("match", 0)
	var after_ack: Array = await _packets(gateway, peer)
	checks["actual acceptance latch suppresses further confirmations"] = probe.ready_accepted and after_ack.is_empty() and probe.ready_attempts == 2
	probe.ready_accepted = false
	probe.ready_successful_sends = 0
	probe.ready_deadline_unix_ms = int(Time.get_unix_time_from_system() * 1000.0) - 1
	probe._try_ready_confirmation("match", 0)
	var expired: Array = await _packets(gateway, peer)
	checks["expired authority deadline still prohibits another write"] = expired.is_empty() and probe.ready_attempts == 2
	probe.ready_deadline_unix_ms = deadline
	probe._try_ready_confirmation("other-match", 0)
	var foreign: Array = await _packets(gateway, peer)
	checks["unverified match cannot use a new attempt"] = foreign.is_empty() and probe.ready_attempts == 2
	gateway.socket.close(); peer.close(); retired_socket.close(); listener.stop()
	probe.free(); store.free(); gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks, "scope": "OFFLINE actual producer and real owned WebSocket packets, delayed confirmation and replaced peer; no external server/world or capacity verdict"}
