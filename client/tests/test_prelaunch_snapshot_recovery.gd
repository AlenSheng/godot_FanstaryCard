extends RefCounted

const Gateway = preload("res://network/gateway.gd")
const Proto = preload("res://network/protobuf.gd")

func _event(kind: String, sequence: int, payload: Dictionary, request_id: String = "") -> PackedByteArray:
	var codec := Proto.new()
	return codec.encode("ServerEnvelope", {"protocol_version":1,"type":kind,"sequence":sequence,"request_id":request_id,"payload":codec.encode(Gateway.EVENTS[kind],payload)})

func _drain(gateway, peer: WebSocketPeer) -> Array:
	var packets: Array = []
	var until_ms := Time.get_ticks_msec() + 70
	while Time.get_ticks_msec() < until_ms:
		gateway.socket.poll()
		peer.poll()
		while peer.get_available_packet_count() > 0:
			packets.append(Proto.new().decode("ClientEnvelope", peer.get_packet()))
		await Engine.get_main_loop().process_frame
	return packets

func run_test() -> Dictionary:
	var checks := {}
	var gateway := Gateway.new()
	gateway.persist_session = false
	var listener := TCPServer.new()
	if listener.listen(0,"127.0.0.1") != OK:
		gateway.free()
		return {"ok":false,"checks":{"owned_loopback_listener":false}}
	var peer := WebSocketPeer.new()
	gateway.socket.connect_to_url("ws://127.0.0.1:" + str(listener.get_local_port()))
	var accepted := false
	var until_ms := Time.get_ticks_msec() + 3000
	while Time.get_ticks_msec() < until_ms:
		gateway.socket.poll()
		if not accepted and listener.is_connection_available():
			peer.accept_stream(listener.take_connection())
			accepted = true
		if accepted: peer.poll()
		if gateway.socket.get_ready_state() == WebSocketPeer.STATE_OPEN and peer.get_ready_state() == WebSocketPeer.STATE_OPEN: break
		await Engine.get_main_loop().process_frame
	checks["owned binary WebSocket opens"] = gateway.socket.get_ready_state() == WebSocketPeer.STATE_OPEN
	var deadline := int(Time.get_unix_time_from_system()*1000) + 15000
	gateway.bind_prelaunch_ticket("current-match","current-room",deadline,0)
	gateway.last_sequence = 1
	# Sequence 2 (required) was permanently lost. READY acceptance can still
	# trigger reads, but none of its payloads may bridge the missing cursor.
	gateway._receive(_event("room.ready_accepted",3,{"match_id":"current-match","room_id":"current-room","deadline_unix_ms":deadline,"ready_players":1,"required_players":1}))
	await _drain(gateway,peer)
	var reads: Array = []
	for index in range(3):
		await Engine.get_main_loop().create_timer(1.02 if index > 0 else .27).timeout
		gateway._read_prelaunch_snapshot()
		var packets: Array = await _drain(gateway,peer)
		for packet in packets:
			if packet.get("type") == "room.snapshot.read":
				reads.append(packet)
				gateway._receive(_event("error.command_rejected",4+index,{"code":"NOT_IN_ROOM","detail":"Room registration still pending"},str(packet.request_id)))
	checks["three actual speculative reads preserve the unresolved cursor"] = reads.size() == 3 and gateway._prelaunch_snapshot_attempts == 3 and gateway.last_sequence == 1 and gateway.room_id.is_empty() and gateway.recovering
	await Engine.get_main_loop().create_timer(1.02).timeout
	gateway._read_prelaunch_snapshot()
	checks["ordinary retries cannot exceed three reads"] = (await _drain(gateway,peer)).is_empty() and gateway._prelaunch_snapshot_attempts == 3
	gateway._receive(_event("room.started",7,{"match_id":"old-match","room_id":"old-room"}))
	checks["foreign start cannot grant another read"] = (await _drain(gateway,peer)).is_empty() and gateway._prelaunch_snapshot_attempts == 3
	var start := _event("room.started",8,{"match_id":"current-match","room_id":"current-room"})
	gateway._receive(start)
	var after_start: Array = await _drain(gateway,peer)
	var authority: Array = after_start.filter(func(packet): return packet.get("type") == "room.snapshot.read")
	checks["matching real start grants one authority read after exhausted speculation"] = authority.size() == 1 and gateway._prelaunch_snapshot_attempts == 4
	checks["start hint cannot apply route or advance across the sequence gap"] = gateway.room_id.is_empty() and gateway.current_match_id.is_empty() and gateway.last_sequence == 1 and gateway.recovering
	await Engine.get_main_loop().create_timer(1.02).timeout
	for _index in range(5): gateway._receive(start)
	gateway._read_prelaunch_snapshot()
	checks["duplicate start hints cannot rearm the fourth read"] = (await _drain(gateway,peer)).is_empty() and gateway._prelaunch_snapshot_attempts <= 4
	if authority.size() == 1:
		var request: Dictionary = authority[0]
		var origin: Dictionary = gateway._pending_request_started[str(request.request_id)].context
		checks["authority read keeps verified identity and an empty wire command"] = request.room_id == "current-room" and request.match_id == "current-match" and Proto.new().decode("RoomSnapshotCommand",request.payload).is_empty() and origin.match_id == "current-match" and origin.room_context_epoch == 0
		gateway._receive(_event("room.snapshot",9,{"match_id":"old-match","room_id":"old-room","room_revision":99},str(request.request_id)))
		checks["late foreign snapshot cannot replace the verified room"] = gateway.room_id.is_empty() and gateway.recovering
		gateway._receive(_event("room.snapshot",10,{"match_id":"current-match","room_id":"current-room","room_revision":2},str(request.request_id)))
	else:
		checks["authority read keeps verified identity and an empty wire command"] = false
		checks["late foreign snapshot cannot replace the verified room"] = false
	checks["only the current correlated snapshot releases recovery"] = gateway.room_id == "current-room" and gateway.current_match_id == "current-match" and gateway.last_sequence == 10 and gateway.room_revision == 2 and not gateway.recovering
	checks["original deadline remains unchanged"] = gateway._prelaunch_ticket.is_empty() or int(gateway._prelaunch_ticket.deadline_unix_ms) == deadline
	gateway.socket.close()
	peer.close()
	listener.stop()
	gateway.free()
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual binary WebSocket and production Gateway, elapsed throttling, permanent sequence gap and delayed registration; no real worlds or deadline relaxation"}
