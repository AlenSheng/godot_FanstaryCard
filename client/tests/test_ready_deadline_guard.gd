extends RefCounted

class Probe extends "res://tests/gameplay_load_client.gd":
	func _ready() -> void:set_process(false)
class GameStub extends Node:
	var room := {}
	var ready_prompt := {}

func run_test() -> Dictionary:
	var checks := {}
	var trace: Array = []
	var Gateway=load("res://network/gateway.gd")
	var gateway=Gateway.new()
	gateway.persist_session=false
	gateway.telemetry_context={"run_id":"ready-regression","client_id":"ready-client","process_epoch":"ready-process","cycle_id":"ready-client:1","phase":"matchmaking"}
	gateway.telemetry.connect(func(sample):trace.append(sample.duplicate(true)))
	var server := TCPServer.new()
	if server.listen(0,"127.0.0.1")!=OK:
		gateway.free()
		return {"ok":false,"checks":{"owned_loopback_listener":false}}
	var peer := WebSocketPeer.new()
	gateway.socket.connect_to_url("ws://127.0.0.1:"+str(server.get_local_port()))
	var accepted := false
	var until_ms := Time.get_ticks_msec()+3000
	while Time.get_ticks_msec()<until_ms:
		gateway.socket.poll()
		if not accepted and server.is_connection_available():
			peer.accept_stream(server.take_connection())
			accepted=true
		if accepted:peer.poll()
		if gateway.socket.get_ready_state()==WebSocketPeer.STATE_OPEN and peer.get_ready_state()==WebSocketPeer.STATE_OPEN:break
		await Engine.get_main_loop().process_frame
	checks["owned actual WebSocket peer opens"] = gateway.socket.get_ready_state()==WebSocketPeer.STATE_OPEN
	checks["unverified READY cannot write even outside recovery"] = not gateway.send("room.ready") and peer.get_available_packet_count()==0
	var deadline: int=int(Time.get_unix_time_from_system()*1000)+500
	gateway.bind_prelaunch_ticket("current-match","current-room",deadline,0)
	var sent: bool=gateway.send("room.ready")
	until_ms=Time.get_ticks_msec()+1000
	while peer.get_available_packet_count()==0 and Time.get_ticks_msec()<until_ms:
		gateway.socket.poll()
		peer.poll()
		await Engine.get_main_loop().process_frame
	var count: int=peer.get_available_packet_count()
	var ready_wire := PackedByteArray()
	while peer.get_available_packet_count()>0:ready_wire=peer.get_packet()
	var proto=load("res://network/protobuf.gd").new()
	var decoded: Dictionary=proto.decode("ClientEnvelope",ready_wire)
	var packet_fields: Array=_wire_field_numbers(ready_wire)
	var digest:=HashingContext.new();digest.start(HashingContext.HASH_SHA256)
	if not ready_wire.is_empty():digest.update(ready_wire)
	var actual_wire_sha: String=digest.finish().hex_encode()
	var proof: Array=trace.filter(func(row):return row.get("type","")=="protocol_observation" and row.get("event_type","")=="room.ready.sent")
	checks["READY metadata keeps dispatch identity without adding route fields to wire"] = proof.size()==1 and proof[0].get("run_id")=="ready-regression" and proof[0].get("cycle_id")=="ready-client:1" and proof[0].get("phase")=="matchmaking" and proof[0].get("match_id")=="current-match" and proof[0].get("room_id")=="current-room" and not packet_fields.is_empty() and not packet_fields.has(-1) and not packet_fields.has(6) and not packet_fields.has(7) and proof[0].wire_sha256==actual_wire_sha
	checks["verified unexpired positive control still writes one READY"] = sent and count==1
	gateway._receive(proto.encode("ServerEnvelope",{"protocol_version":1,"type":"room.ready_accepted","sequence":1,"payload":proto.encode("RoomReadyAcceptedEvent",{"match_id":"current-match","room_id":"current-room","deadline_unix_ms":deadline,"ready_players":1,"required_players":1})}))
	var accepted_before: bool=gateway._prelaunch_ready_accepted
	gateway._prelaunch_snapshot_attempts=2
	gateway.bind_prelaunch_ticket("current-match","current-room",deadline+10000,0)
	checks["same-scope rebind cannot extend original absolute deadline"] = gateway._prelaunch_ticket.deadline_unix_ms==deadline
	checks["same-scope rebind preserves confirmed READY and read budget"] = accepted_before and gateway._prelaunch_ready_accepted and gateway._prelaunch_snapshot_attempts==2

	await Engine.get_main_loop().create_timer(.6).timeout
	var refused: bool=not gateway.send("room.ready")
	gateway.socket.poll()
	peer.poll()
	checks["same real elapsed deadline prevents next write without recovery flag"] = not gateway.recovering and refused and peer.get_available_packet_count()==0
	gateway.socket.close()
	peer.close()
	server.stop()
	gateway.free()
	var game := GameStub.new()
	var probe := Probe.new()
	probe.Game=game
	probe.active_match_id="earlier-cycle"
	var known: int=int(Time.get_unix_time_from_system()*1000)+5000
	probe._on_event("room.ready_required",{"match_id":"new-match","room_id":"new-room","deadline_unix_ms":known})
	game.ready_prompt={}
	checks["new-match authority deadline survives old active latch and cleared hint"] = probe._ready_deadline_for_match("new-match")==known and probe.active_match_id=="earlier-cycle"
	probe._on_event("room.ready_required",{"match_id":"new-match","room_id":"new-room","deadline_unix_ms":known+10000})
	checks["later required cannot extend same match original deadline"] = probe._ready_deadline_for_match("new-match")==known
	game.ready_prompt={"match_id":"other-match","deadline_unix_ms":known+20000}
	checks["foreign mutable hint never supplies verified match deadline"] = probe._ready_deadline_for_match("new-match")==known and probe._ready_deadline_for_match("unknown-match")==0
	probe.active_match_id="current-event-match";probe.verified_ready_match_id="current-event-match"
	probe._on_event("room.ready_required",{"match_id":"current-event-match","room_id":"event-room","deadline_unix_ms":known})
	probe._on_event("room.ready_required",{"match_id":"current-event-match","room_id":"event-room","deadline_unix_ms":known+10000})
	checks["current-match event latch uses earliest cached deadline"] = probe.ready_deadline_unix_ms==known and probe._ready_deadline_for_match("current-event-match")==known
	for index in range(20):probe._remember_ready_deadline("bounded-"+str(index),known)
	checks["authority deadline memory is explicitly capped8"] = probe.known_ready_deadlines.size()==8
	probe.free()
	game.free()
	return {"ok":not checks.values().has(false),"checks":checks,"ready_wire_facts":{"field_numbers":packet_fields,"decoded_room_id_default":decoded.get("room_id"),"decoded_match_id_default":decoded.get("match_id"),"wire_SHA256":actual_wire_sha,"wire_hex":ready_wire.hex_encode(),"observation":proof},"scope":"OFFLINE actual Gateway.send with real owned loopback WebSocket/actual elapsedclock, real load event consumer and positive/negative stale-hint boundaries; no external network/gameplayworlds"}

func _wire_varint(data: PackedByteArray, at: int) -> Array:
	var value: int=0
	var shift: int=0
	for _index in range(10):
		if at>=data.size():return [-1,at]
		var part: int=data[at];at+=1;value|=(part&127)<<shift
		if (part&128)==0:return [value,at]
		shift+=7
	return [-1,at]
func _wire_field_numbers(data: PackedByteArray) -> Array:
	var fields: Array=[];var at: int=0
	while at<data.size():
		var tag: Array=_wire_varint(data,at)
		if tag[0]<=0:return [-1]
		at=tag[1];fields.append(tag[0]>>3)
		match tag[0]&7:
			0:
				var scalar: Array=_wire_varint(data,at)
				if scalar[0]<0:return [-1]
				at=scalar[1]
			1:at+=8
			2:
				var size: Array=_wire_varint(data,at)
				if size[0]<0:return [-1]
				at=size[1]+size[0]
			5:at+=4
			_:return [-1]
		if at>data.size():return [-1]
	return fields
