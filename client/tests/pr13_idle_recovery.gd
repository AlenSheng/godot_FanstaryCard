extends SceneTree
const Production = preload("res://network/gateway.gd")
const Proto = preload("res://network/protobuf.gd")

class TicketFixture extends "res://network/gateway.gd":
	var fixture_url: String
	var attempts := 0
	func connect_realtime() -> void:
		# Authentication/ticket issuance is a declared fixture here. Socket,
		# decoder, actual elapsed time, ping and retry scheduling are native.
		attempts += 1
		reconnect_enabled = true
		online = false
		socket = WebSocketPeer.new()
		socket.connect_to_url(fixture_url)
		_connecting_at = Time.get_ticks_msec()

func _initialize() -> void: call_deferred("run")

func run() -> void:
	var server := TCPServer.new()
	var listening := server.listen(0,"127.0.0.1")
	var gateway := TicketFixture.new()
	gateway.persist_session=false
	gateway.token="declared-local-fixture"
	gateway.token_expires_at=Time.get_unix_time_from_system()+3600
	gateway.authenticated_user_id="controlled-logical-player"
	gateway.session_generation=7
	gateway.telemetry_context={"run_id":"idle-contract","client_id":"logical-client","process_epoch":"same-process","cycle_id":"logical-client:2"}
	var before: Dictionary=gateway.telemetry_context.duplicate(true)
	root.add_child(gateway)
	gateway.fixture_url="ws://127.0.0.1:%d" % server.get_local_port()
	gateway.connect_realtime()
	var peers: Array=[]
	var sent_connected: Dictionary={}
	var pings:=0
	var old_remained_open:=false
	var started:=Time.get_ticks_msec()
	while Time.get_ticks_msec()-started<40000:
		if server.is_connection_available():
			var peer:=WebSocketPeer.new()
			peer.accept_stream(server.take_connection())
			peers.append(peer)
		for index in peers.size():
			var peer: WebSocketPeer=peers[index]
			peer.poll()
			if peer.get_ready_state()!=WebSocketPeer.STATE_OPEN: continue
			if not sent_connected.has(index):
				var codec:=Proto.new()
				peer.put_packet(codec.encode("ServerEnvelope",{"protocol_version":1,"type":"session.connected","sequence":index+1,
					"payload":codec.encode("SessionConnectedEvent",{"player_id":"controlled-logical-player"})}))
				sent_connected[index]=true
			while peer.get_available_packet_count()>0:
				var codec:=Proto.new()
				var command: Dictionary=codec.decode("ClientEnvelope",peer.get_packet())
				if command.get("type")=="ping":
					pings+=1
					old_remained_open=index==0 and peer.get_ready_state()==WebSocketPeer.STATE_OPEN
				# Intentionally withhold pong on the first open connection.
		if peers.size()>=2 and gateway.online: break
		await process_frame
	var passed:=listening==OK and old_remained_open and pings>=1 and gateway.attempts==2 and peers.size()==2 and gateway.online and gateway.session_generation==7 and gateway.telemetry_context==before
	var row={"case_id":"PR13-A06.2-T01","executed":true,"status":"Passed" if passed else "Failed","profiles_executed":["OFFLINE"],
		"actual":{"actual_elapsed_ms":Time.get_ticks_msec()-started,"native_open_connections":peers.size(),"reconnect_attempts":gateway.attempts,"binary_pings_observed":pings,
			"unanswered_peer_was_open":old_remained_open,"session_generation":gateway.session_generation,"logical_context_preserved":gateway.telemetry_context==before,"completed_cycles":0},
		"scope":"Actual loopback TCP/WebSocket and production ping/decoder/retry timer, actual wall duration; declared ticket/auth fixture; no Program/PG/LIVE or new cycle completion claim"}
	gateway.reconnect_enabled=false;gateway.socket.close()
	for peer in peers: peer.close()
	server.stop();gateway.queue_free()
	FileAccess.open(OS.get_environment("PR13_READY_EDGES"),FileAccess.WRITE).store_string(JSON.stringify({"cases":[row]}))
	print(JSON.stringify(row));quit(0 if passed else 1)
