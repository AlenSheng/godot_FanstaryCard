extends RefCounted

const Gateway = preload("res://network/gateway.gd")
const Proto = preload("res://network/protobuf.gd")
class OfflineStore extends "res://state/game_store.gd":
	func _ready() -> void: set_process(false)
class Probe extends "res://tests/gameplay_load_client.gd":
	func _ready() -> void: set_process(false)

func _room(store: Node) -> Dictionary:
	return {"config_version":store.CATALOG.data.version, "match_id":"ready-match", "room_id":"ready-room", "room_revision":10,
		"player":{"player_id":"self", "phase":"Pve", "hand":[]}, "pve":{"battle_id":"battle", "monsters":[]}, "allowed_actions":[]}

func _packet(kind: String, schema: String, sequence: int, payload: Dictionary, request_id: String="") -> PackedByteArray:
	var codec := Proto.new()
	return codec.encode("ServerEnvelope", {"protocol_version":1, "type":kind, "sequence":sequence, "request_id":request_id, "payload":codec.encode(schema,payload)})

func _fixture() -> Dictionary:
	var gateway := Gateway.new()
	gateway.persist_session=false; gateway.online=true; gateway.base_url="http://127.0.0.1:1"; gateway.session_generation=1; gateway.room_context_epoch=4
	gateway.telemetry_context={"run_id":"ready-run", "client_id":"ready-client", "process_epoch":"ready-process", "cycle_id":"ready-client:4", "phase":"matchmaking"}
	var store := OfflineStore.new(); store.gateway=gateway; store._room_context_epoch=4
	var probe := Probe.new(); probe.Game=store; probe.run_id="ready-run"; probe.client_id="ready-client"; probe.process_epoch="ready-process"; probe.cycles_completed=3; probe.stage="matchmaking"; probe.active_match_id="ready-match"; probe.verified_ready_match_id="ready-match"
	var trace: Array=[]; var failures: Array=[]; var delivered: Array=[]; var notices: Array=[]; var sounds: Array=[]
	gateway.event_received.connect(store._on_event)
	gateway.failed.connect(func(message):store.notice.emit(message))
	gateway.telemetry.connect(store._on_gateway_telemetry)
	store.network_telemetry.connect(probe._on_telemetry)
	store.notice.connect(probe._on_notice)
	gateway.failed.connect(probe._on_notice)
	gateway.event_received.connect(probe._on_event)
	gateway.telemetry.connect(func(sample):trace.append(sample.duplicate(true)))
	gateway.failed.connect(func(message):failures.append(message))
	gateway.event_received.connect(func(kind,payload):delivered.append({"kind":kind,"payload":payload.duplicate(true)}))
	store.notice.connect(func(message):notices.append(message))
	store.sound_requested.connect(func(cue):sounds.append(cue))
	return {"gateway":gateway,"store":store,"probe":probe,"trace":trace,"failures":failures,"delivered":delivered,"notices":notices,"sounds":sounds}

func _join(f: Dictionary, sequence: int=1) -> void:
	f.gateway._receive(_packet("room.started","RoomStartedEvent",sequence,{"match_id":"ready-match","room_id":"ready-room","snapshot":_room(f.store)}))

func _close(f: Dictionary) -> void:
	f.gateway.socket.close();f.gateway.end_session("",false);f.probe.free();f.store.free();f.gateway.free()

func run_test() -> Dictionary:
	var checks: Dictionary={};var f:=_fixture();var gateway: Node=f.gateway
	var listener:=TCPServer.new();var peer:=WebSocketPeer.new();var accepted: bool=false
	if listener.listen(0,"127.0.0.1")!=OK:_close(f);return {"ok":false,"checks":{"owned loopback listener":false}}
	gateway.socket.connect_to_url("ws://127.0.0.1:"+str(listener.get_local_port()));var end_ms: int=Time.get_ticks_msec()+3000
	while Time.get_ticks_msec()<end_ms:
		gateway.socket.poll()
		if not accepted and listener.is_connection_available():peer.accept_stream(listener.take_connection());accepted=true
		if accepted:peer.poll()
		if gateway.socket.get_ready_state()==WebSocketPeer.STATE_OPEN and peer.get_ready_state()==WebSocketPeer.STATE_OPEN:break
		await Engine.get_main_loop().process_frame
	checks["real owned WebSocket opens"] = gateway.socket.get_ready_state()==WebSocketPeer.STATE_OPEN
	gateway.bind_prelaunch_ticket("ready-match","ready-room",int(Time.get_unix_time_from_system()*1000)+60000,4)
	var first_id: String=gateway.new_id();var late_id: String=gateway.new_id();var original: Dictionary=gateway.capture_context()
	var first_sent: bool=gateway.send("room.ready",{},first_id);var late_sent: bool=gateway.send("room.ready",{},late_id)
	var packets: Array=[]
	while packets.size()<2 and Time.get_ticks_msec()<end_ms:
		gateway.socket.poll();peer.poll()
		while peer.get_available_packet_count()>0:packets.append(Proto.new().decode("ClientEnvelope",peer.get_packet()))
		await Engine.get_main_loop().process_frame
	checks["both actual READY sends precede late responses"] = first_sent and late_sent and packets.size()==2 and packets[0].type=="room.ready" and packets[1].request_id==late_id
	gateway._receive(_packet("room.ready_accepted","RoomReadyAcceptedEvent",1,{"match_id":"ready-match","room_id":"ready-room","deadline_unix_ms":int(Time.get_unix_time_from_system()*1000)+60000,"ready_players":1,"required_players":1},first_id))
	_join(f,2)
	checks["actual store adopts authoritative start and one epoch"] = f.store.room.get("match_id")=="ready-match" and gateway.room_id=="ready-room" and gateway.current_match_id=="ready-match" and gateway.room_context_epoch==5 and f.probe.ready_accepted
	f.probe.stage="playing";f.probe._update_context()
	f.store._pending_commands[late_id]={"action":"room.ready","confirmed":false,"room_id":"ready-room","sent_revision":10}
	gateway._receive(_packet("error.command_rejected","CommandRejectedEvent",3,{"code":"READY_NOT_FOUND","detail":"The player has no pending ready lobby."},late_id))
	var measured: Array=f.trace.filter(func(row):return row.get("type")=="realtime" and row.get("request_id")==late_id)
	var resolved: Array=f.trace.filter(func(row):return row.get("event_type")=="room.ready.rejection_resolved")
	checks["late READY retains exactly one original rejected measurement"] = measured.size()==1 and measured[0].result=="rejected" and measured[0].response_type=="error.command_rejected" and original.keys().all(func(key):return measured[0].get(key)==original[key])
	checks["verified late READY remains diagnostic with frozen origin"] = resolved.size()==1 and resolved[0].trace_only and resolved[0].result=="rejected" and resolved[0].code=="READY_NOT_FOUND" and resolved[0].detail=="The player has no pending ready lobby." and resolved[0].request_id==late_id and resolved[0].room_context_epoch==4 and resolved[0].verified_room_context_epoch==5 and resolved[0].phase=="matchmaking" and resolved[0].record_owner_source=="dispatch"
	checks["joined READY no longer emits user or probe errors"] = f.failures.is_empty() and f.notices.is_empty() and f.probe.errors.is_empty() and not f.sounds.has("error") and f.delivered[-1].kind=="room.started"
	checks["resolved observation does not confirm rejected command"] = gateway._response_contexts[late_id].result=="rejected" and gateway.last_sequence==3 and gateway.room_revision==10 and gateway.room_id=="ready-room"
	checks["diagnostic cannot confirm pending business operation"] = f.store._pending_commands.has(late_id) and not f.store._pending_commands[late_id].get("confirmed",false)
	checks["diagnostic cannot trigger a snapshot confirmation read"] = not gateway._pending_request_started.values().any(func(value):return value.get("action")=="room.snapshot.read")
	var starts: Array=f.probe.telemetry.filter(func(row):return row.get("event_type")=="room.started")
	checks["uncorrelated start still has Unknown business origin"] = starts.size()==1 and starts[0].cycle_id=="Unknown" and starts[0].phase=="Unknown" and starts[0].record_owner_source=="gateway_receive"
	peer.close();listener.stop();_close(f)
	f=_fixture();gateway=f.gateway;gateway.telemetry_context={}
	gateway.bind_prelaunch_ticket("ready-match","ready-room",int(Time.get_unix_time_from_system()*1000)+60000,4)
	var production_origin: Dictionary=gateway.capture_context()
	_join(f)
	gateway._pending_request_started["production-ready"]={"action":"room.ready","started_at":Time.get_ticks_msec(),"context":production_origin}
	gateway._receive(_packet("error.command_rejected","CommandRejectedEvent",2,{"code":"READY_NOT_FOUND","detail":"already joined"},"production-ready"))
	checks["normal client without load instrumentation resolves same-room late READY"] = not production_origin.has("run_id") and f.failures.is_empty() and f.notices.is_empty() and f.delivered[-1].kind=="room.started"
	checks["normal client raw rejection is still measured once"] = f.trace.filter(func(row):return row.get("type")=="realtime" and row.get("request_id")=="production-ready" and row.get("result")=="rejected").size()==1
	_close(f)

	for mode in ["not_joined","wrong_match","wrong_room","old_session","missing_session","missing_epoch","unchanged_epoch","same_ids_reentered","wrong_action","other_error","uncorrelated","missing_origin","foreign_worker","next_cycle","replayed","invalid_epoch_type"]:
		f=_fixture();gateway=f.gateway
		var origin: Dictionary=gateway.capture_context();origin.match_id="ready-match";origin.room_id="ready-room"
		if mode!="not_joined":_join(f)
		var action: String="room.ready";var code: String="READY_NOT_FOUND"
		match mode:
			"wrong_match":origin.match_id="other-match"
			"wrong_room":origin.room_id="other-room"
			"old_session":origin.session_generation=0
			"missing_session":origin.erase("session_generation")
			"missing_epoch":origin.erase("room_context_epoch")
			"unchanged_epoch":gateway.room_context_epoch=4
			"same_ids_reentered":gateway.room_context_epoch=7
			"wrong_action":action="battle.abandon"
			"other_error":code="READY_WINDOW_EXPIRED"
			"missing_origin":origin={}
			"foreign_worker":origin.process_epoch="other-process"
			"next_cycle":gateway.telemetry_context.cycle_id="ready-client:5"
			"replayed":gateway.recovering=true
			"invalid_epoch_type":origin.room_context_epoch="4"
		if mode!="uncorrelated":gateway._pending_request_started["negative"]={"action":action,"started_at":Time.get_ticks_msec(),"context":origin}
		gateway._receive(_packet("error.command_rejected","CommandRejectedEvent",gateway.last_sequence+1,{"code":code,"detail":"must remain visible"},"negative"))
		checks[mode+" keeps real rejection/error path"] = f.failures==["must remain visible"] and not f.probe.errors.is_empty() and not f.trace.any(func(row):return row.get("event_type")=="room.ready.rejection_resolved") and f.delivered[-1].kind=="error.command_rejected"
		_close(f)
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual Gateway.send/receive, owned WebSocket, real Store and recorder; causal order from recorded R2 late READY. No server/world or capacity qualification; original failed run retained."}
