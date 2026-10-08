extends SceneTree

const Gateway = preload("res://network/gateway.gd")
const Proto = preload("res://network/protobuf.gd")
var cases: Array = []

func packet(kind: String, sequence: int, payload: Dictionary, request_id: String = "") -> PackedByteArray:
	var codec := Proto.new()
	return codec.encode("ServerEnvelope",{"protocol_version":1,"type":kind,"sequence":sequence,"request_id":request_id,"payload":codec.encode(Gateway.EVENTS[kind],payload)})

func record(id: String, passed: bool, actual: Dictionary) -> void:
	cases.append({"case_id":id,"executed":true,"status":"Passed" if passed else "Failed","profiles_executed":["OFFLINE"],"actual":actual,"scope":"Actual production binary sender/decoder on an owned native loopback peer; ticket and server payload inputs explicitly controlled. PG authority and LIVE layers separate."})

func _initialize() -> void: call_deferred("run_cases")

func run_cases() -> void:
	var server := TCPServer.new()
	var listening := server.listen(0,"127.0.0.1")
	if listening!=OK: quit(1);return
	var gateway := Gateway.new()
	gateway.persist_session=false
	gateway.token="controlled-native-session"
	gateway.token_expires_at=Time.get_unix_time_from_system()+600
	gateway.socket=WebSocketPeer.new()
	var peer := WebSocketPeer.new()
	gateway.socket.connect_to_url("ws://127.0.0.1:"+str(server.get_local_port()))
	var accepted := false
	var end := Time.get_ticks_msec()+5000
	while Time.get_ticks_msec()<end:
		gateway.socket.poll()
		if not accepted and server.is_connection_available():
			peer.accept_stream(server.take_connection());accepted=true
		if accepted: peer.poll()
		if gateway.socket.get_ready_state()==WebSocketPeer.STATE_OPEN and peer.get_ready_state()==WebSocketPeer.STATE_OPEN: break
		await process_frame
	if gateway.socket.get_ready_state()!=WebSocketPeer.STATE_OPEN: quit(1);return
	gateway.recovering=true
	gateway.room_context_epoch=1
	var blocked_unbound := not gateway.send("room.ready")
	gateway.bind_prelaunch_ticket("match-expired","room-expired",1,1)
	var blocked_expired := not gateway.send("room.ready")
	record("PR13-A04.1-T03",blocked_unbound and blocked_expired and gateway._prelaunch_ticket.is_empty(),{"unverified_ticket_blocked":blocked_unbound,"expired_ticket_blocked":blocked_expired,"dispatch_attempts":0})
	gateway.bind_prelaunch_ticket("match-A","room-A",int(Time.get_unix_time_from_system()*1000)+15000,1)
	var old_origin := gateway.capture_context()
	gateway.room_context_epoch=2
	gateway.bind_prelaunch_ticket("match-B","room-B",int(Time.get_unix_time_from_system()*1000)+15000,2)
	gateway.last_sequence=10
	gateway._receive(packet("room.started",11,{"match_id":"match-A","room_id":"room-A","snapshot":{"match_id":"match-A","room_id":"room-A"}}))
	var old_start_safe := gateway.last_sequence==11 and gateway.room_id.is_empty() and gateway.recovering and gateway._prelaunch_snapshot_attempts==0
	record("PR13-A04.4-T03",old_start_safe,{"old_start_consumed_without_route":old_start_safe,"current_verified_match":gateway._prelaunch_ticket.get("match_id"),"snapshot_attempts":gateway._prelaunch_snapshot_attempts,"scope":"Prior-cycle decode callback, no natural gameplay completion counted"})
	gateway._pending_request_started["old-read"]={"action":"room.snapshot.read","started_at":Time.get_ticks_msec(),"context":old_origin}
	gateway._receive(packet("room.snapshot",12,{"match_id":"match-A","room_id":"room-A","room_revision":7},"old-read"))
	var old_snapshot_safe := gateway.last_sequence==12 and gateway.room_id.is_empty() and gateway.recovering
	gateway._receive(packet("room.started",15,{"match_id":"match-B","room_id":"room-B","snapshot":{"match_id":"match-B","room_id":"room-B"}}))
	var hint_not_applied := gateway.last_sequence==12 and gateway.room_id.is_empty() and gateway._prelaunch_snapshot_attempts==1
	end=Time.get_ticks_msec()+3000
	while peer.get_available_packet_count()==0 and Time.get_ticks_msec()<end:
		gateway.socket.poll();peer.poll();await process_frame
	var codec := Proto.new()
	var read: Dictionary = codec.decode("ClientEnvelope",peer.get_packet()) if peer.get_available_packet_count()>0 else {}
	var body: Dictionary = codec.decode("RoomSnapshotCommand",read.get("payload",PackedByteArray()))
	var allowed_read := read.get("type")=="room.snapshot.read" and body.get("room_id")=="room-B"
	gateway._receive(packet("room.snapshot",16,{"match_id":"match-B","room_id":"room-B","room_revision":8},str(read.get("request_id",""))))
	var authority_applied := gateway.room_id=="room-B" and gateway.current_match_id=="match-B" and not gateway.recovering and gateway.last_sequence==16
	record("LOAD-04.3-T03",old_snapshot_safe and hint_not_applied and allowed_read and authority_applied,{"old_snapshot_keeps_current_recovery":old_snapshot_safe,"future_hint_not_applied":hint_not_applied,"actual_binary_snapshot_read":allowed_read,"authoritative_snapshot_applied":authority_applied})
	gateway.socket.close();peer.close();server.stop();gateway.free()
	FileAccess.open(OS.get_environment("PR13_READY_EDGES"),FileAccess.WRITE).store_string(JSON.stringify({"cases":cases}))
	print(JSON.stringify({"executed":cases.size(),"passed":cases.filter(func(c):return c.status=="Passed").size()}))
	quit(0 if cases.all(func(c):return c.status=="Passed") else 1)
