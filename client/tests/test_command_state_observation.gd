extends RefCounted
class Probe extends "res://tests/gameplay_load_client.gd":
	func _ready() -> void: set_process(false)
class Store extends "res://state/game_store.gd":
	func _ready() -> void: set_process(false)
class QuietGateway extends "res://network/gateway.gd":
	func _ready() -> void: set_process(false)
func _case() -> Dictionary:
	var g=Store.new();var w=QuietGateway.new();w.persist_session=false;g.gateway=w
	var p=Probe.new();p.Game=g;p.run_id="run";p.client_id="client";p.process_epoch="process";p.own_user_id="self";p.active_match_id="match";p.stage="playing"
	w.room_id="room";w.current_match_id="match";w.room_context_epoch=2;w.room_revision=40;w.session_generation=1
	g.room=_room();p._update_context();return {"probe":p,"game":g,"gateway":w}
func _room(duel: bool=false) -> Dictionary:
	var r={"room_id":"room","match_id":"match","room_revision":40,"player":{"player_id":"self","phase":"Pvp" if duel else "Pve","stun_remaining_ms":0,"combat":{"hp":80,"maximum_hp":70,"effective_maximum_hp":80}},"allowed_actions":["battle.play_cards"],"pve":{"battle_id":"pve"}}
	if duel:r.duel={"duel_id":"duel","opponent_id":"other"}
	return r
func _sent(w) -> Dictionary:
	return w.capture_context().merged({"type":"command_lifecycle","event_type":"command.sent","action":"battle.play_cards","request_id":"request","packet_room_id":"room","packet_match_id":"match","packet_expected_revision":40,"packet_battle_id":"pve"},true)
func _snapshot(r:Dictionary) -> Dictionary:
	return r.merged({"_receive_owner_context":{"run_id":"run","client_id":"client","process_epoch":"process"},"_sequence":10,"_event_revision":r.room_revision,"_replayed":false},true)
func _free(c:Dictionary) -> void:c.probe.free();c.game.free();c.gateway.free()
func run_test() -> Dictionary:
	var checks={};var c=_case();var p=c.probe;var g=c.game;var w=c.gateway
	var original=g.room.duplicate(true);p.last_progress_ms=123;p._on_telemetry(_sent(w));var row:Dictionary=p.telemetry[-1];var state:Dictionary=row.get("dispatch_state",{})
	checks["command callback records exact local actor phase and raw permission list"]=state.get("local_snapshot",{}).get("player_phase")=="Pve" and state.get("local_snapshot",{}).get("allowed_actions")==["battle.play_cards"]
	checks["packet and snapshot revision are independently bound"]=state.get("identity_binding")=="SameCurrentRoute" and state.get("revision_relation")=="SameSnapshotRevision" and state.get("battle_relation")=="SameActiveBattle"
	checks["legal80over70HP is preserved without a numeric verdict"]=state.get("local_snapshot",{}).get("player_hp")==80 and state.get("local_snapshot",{}).get("base_maximum_hp")==70 and not state.has("hp_anomaly")
	checks["state capture does not mutate store or advance gameplay"]=g.room==original and p.last_progress_ms==123 and not row.get("gameplay_progress",true)
	g.room.allowed_actions.clear();checks["recorded permission list is immutable"]=state.get("local_snapshot",{}).get("allowed_actions")==["battle.play_cards"];g.room=original.duplicate(true)
	var late=_sent(w);late.type="realtime";late.event_type="realtime";late.response_type="error.command_rejected";late.result="rejected";late.cycle_id="client:0";g.room=_room(true);p._on_telemetry(late);row=p.telemetry[-1]
	checks["late rejection keeps origin and cannot manufacture dispatch state"]=row.cycle_id=="client:0" and not row.has("dispatch_state")
	g.room=original.duplicate(true);var missing=_sent(w);missing.erase("packet_expected_revision");p._on_telemetry(missing);checks["missing packet revision remainsUnknown"]=p.telemetry[-1].get("dispatch_state",{}).get("revision_relation")=="Unknown"
	var prior=_sent(w);prior.room_context_epoch=1;p._on_telemetry(prior);checks["old epoch cannot bind current dispatch snapshot"]=p.telemetry[-1].get("dispatch_state",{}).get("identity_binding")=="OriginMismatch"
	g.room.room_revision=41;p._on_telemetry(_sent(w));checks["reentrant later snapshot is explicitly later not send state"]=p.telemetry[-1].get("dispatch_state",{}).get("revision_relation")=="LaterSnapshotRevision"
	g.room.room_revision=39;p._on_telemetry(_sent(w));checks["known older local snapshot is explicitly earlier"]=p.telemetry[-1].get("dispatch_state",{}).get("revision_relation")=="EarlierSnapshotRevision"
	g.room=original.duplicate(true);p.last_progress_ms=123;p._on_event("room.snapshot",_snapshot(original));var snapshots=p.telemetry.filter(func(v):return v.get("event_type")=="room.command_state_observed");row=snapshots[-1] if not snapshots.is_empty() else {}
	checks["unsolicited authority snapshot has physical owner and explicit phase"]=row.get("authority_state",{}).get("identity_binding")=="SameCurrentRoute" and row.get("authority_state",{}).get("snapshot",{}).get("player_phase")=="Pve"
	checks["unsolicited snapshot does not invent business cycle or progress"]=row.get("cycle_id")=="Unknown" and row.get("origin_context_state")=="Unknown" and p.last_progress_ms==123
	var count=snapshots.size();var same=original.duplicate(true);same.room_revision=41;same.player.combat.hp=81;p._on_event("room.snapshot",_snapshot(same));checks["ordinary revision and HP ticks do not flood critical state trace"]=p.telemetry.filter(func(v):return v.get("event_type")=="room.command_state_observed").size()==count
	var replay=_snapshot(_room(true));replay._replayed=true;p._on_event("room.snapshot",replay);row=p.telemetry[-1];checks["replayed snapshot remains explicitly unqualified"]=row.get("authority_state",{}).get("identity_binding")=="Replayed"
	p._on_event("room.snapshot",_snapshot(_room(true)));row=p.telemetry[-1];checks["replay cannot suppress next real PVP phase transition"]=row.get("authority_state",{}).get("identity_binding")=="SameCurrentRoute" and row.get("authority_state",{}).get("snapshot",{}).get("active_battle_id")=="duel" and row.get("authority_state",{}).get("snapshot",{}).get("pve_battle_id")=="pve"
	var foreign=_snapshot(original);foreign.player=original.player.duplicate(true);foreign.player.player_id="foreign";p._on_event("room.snapshot",foreign);checks["foreign actor snapshot is not current authority"]=p.telemetry[-1].get("authority_state",{}).get("identity_binding")=="RouteMismatch"
	_free(c)
	# The actual packet and emitted metadata must agree even when an earlier
	# synchronous observer switches the local room before Native records it.
	c=_case();p=c.probe;g=c.game;w=c.gateway;var listener:=TCPServer.new();var peer:=WebSocketPeer.new();var accepted:=false;var opened:=listener.listen(0,"127.0.0.1")==OK
	if opened:
		w.socket.connect_to_url("ws://127.0.0.1:"+str(listener.get_local_port()));var until:=Time.get_ticks_msec()+3000
		while Time.get_ticks_msec()<until:
			w.socket.poll()
			if not accepted and listener.is_connection_available():peer.accept_stream(listener.take_connection());accepted=true
			if accepted:peer.poll()
			if w.socket.get_ready_state()==WebSocketPeer.STATE_OPEN and peer.get_ready_state()==WebSocketPeer.STATE_OPEN:break
			await Engine.get_main_loop().process_frame
		opened=w.socket.get_ready_state()==WebSocketPeer.STATE_OPEN
	checks["owned real WebSocket is open"]=opened
	if opened:
		w.telemetry.connect(func(sample):
			if sample.get("event_type")=="command.sent":g.room={"room_id":"new-room","match_id":"new-match","room_revision":41,"player":{"player_id":"self","phase":"ActionBar"}};w.room_id="new-room";w.current_match_id="new-match";w.room_context_epoch=3)
		w.telemetry.connect(p._on_telemetry);var sent:bool=w.send("battle.play_cards",{"battle_id":"pve","target_id":"rat","card_instance_ids":["card"]},"wire-request");var until:=Time.get_ticks_msec()+1000
		while peer.get_available_packet_count()==0 and Time.get_ticks_msec()<until:w.socket.poll();peer.poll();await Engine.get_main_loop().process_frame
		var bytes:PackedByteArray=peer.get_packet() if peer.get_available_packet_count()>0 else PackedByteArray();var codec=load("res://network/protobuf.gd").new();var packet:Dictionary=codec.decode("ClientEnvelope",bytes);var body:Dictionary=codec.decode("BattlePlayCardsCommand",packet.get("payload",PackedByteArray()));row=p.telemetry[-1]
		checks["wire envelope identity revision and payload remain original"]=sent and packet.get("room_id")=="room" and packet.get("match_id")=="match" and packet.get("expected_revision")==40 and body.get("battle_id")=="pve"
		checks["packet metadata survives synchronous reentrancy"]=row.get("packet_room_id")==packet.get("room_id") and row.get("packet_match_id")==packet.get("match_id") and row.get("packet_expected_revision")==packet.get("expected_revision") and row.get("packet_battle_id")==body.get("battle_id")
		checks["selected instance metadata equals actual owned socket wire"]=row.get("packet_card_instance_ids_valid",false) and row.get("packet_card_instance_ids")==body.get("card_instance_ids") and row.get("packet_target_id")==body.get("target_id")
		checks["changed local owner is not labelled original send state"]=row.get("dispatch_state",{}).get("identity_binding")=="OriginMismatch"
	w.socket.close();peer.close();listener.stop();_free(c)
	c=_case();p=c.probe;g=c.game;w=c.gateway
	w.event_received.connect(func(kind,payload):
		if kind=="room.snapshot":w.telemetry_context={"run_id":"later-run","client_id":"later-client","process_epoch":"later-process"})
	w.event_received.connect(p._on_event)
	var codec=load("res://network/protobuf.gd").new();var wire:PackedByteArray=codec.encode("ServerEnvelope",{"protocol_version":1,"type":"room.snapshot","sequence":1,"room_revision":40,"payload":codec.encode("RoomSnapshotEvent",_room())})
	w._receive(wire);row=p.telemetry[-1] if not p.telemetry.is_empty() else {}
	checks["real decoder freezes unsolicited snapshot receiver before reentrant observer"]=row.get("authority_state",{}).get("receive_owner",{}).get("run_id")=="run" and row.get("run_id")=="run" and row.get("client_id")=="client"
	checks["snapshot receiver identity does not invent a request or business cycle"]=row.get("authority_state",{}).get("identity_binding")=="SameCurrentRoute" and row.get("cycle_id")=="Unknown" and row.get("origin_context_state")=="Unknown"
	_free(c)
	var edges:Dictionary=await run_packet_metadata_edges();checks.merge(edges.checks)
	var authority_edges:Dictionary=await run_authority_integrity_edges();checks.merge(authority_edges.checks)
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual recorder and Gateway over owned WebSocket;synthetic states;no real authority worlds,no rejection whitelist or acceptance relaxation"}

func run_packet_metadata_edges() -> Dictionary:
	var checks={};var c=_case();var p=c.probe;var w=c.gateway;var listener:=TCPServer.new();var peer:=WebSocketPeer.new();var accepted:=false;var opened:=listener.listen(0,"127.0.0.1")==OK
	if opened:
		w.socket.connect_to_url("ws://127.0.0.1:"+str(listener.get_local_port()));var until:=Time.get_ticks_msec()+3000
		while Time.get_ticks_msec()<until:
			w.socket.poll()
			if not accepted and listener.is_connection_available():peer.accept_stream(listener.take_connection());accepted=true
			if accepted:peer.poll()
			if w.socket.get_ready_state()==WebSocketPeer.STATE_OPEN and peer.get_ready_state()==WebSocketPeer.STATE_OPEN:break
			await Engine.get_main_loop().process_frame
		opened=w.socket.get_ready_state()==WebSocketPeer.STATE_OPEN
	if opened:
		w.telemetry.connect(p._on_telemetry)
		for job in [{"name":"unknown move battle field is not packet evidence","action":"room.move","schema":"RoomMoveCommand","field":"battle_id","payload":{"row":1,"column":0,"battle_id":"not-on-wire"}}, {"name":"duel uses actual duel_id not extra battle_id","action":"duel.leave","schema":"DuelLeaveCommand","field":"duel_id","payload":{"duel_id":"duel","battle_id":"not-on-wire"}}, {"name":"null encoded field cannot borrow another input field","action":"battle.play_cards","schema":"BattlePlayCardsCommand","field":"battle_id","payload":{"battle_id":null,"duel_id":"not-on-wire","target_id":"rat","card_instance_ids":["card"]}}]:
			var sent:bool=w.send(job.action,job.payload,"edge-"+job.action);var until:=Time.get_ticks_msec()+1000
			while peer.get_available_packet_count()==0 and Time.get_ticks_msec()<until:w.socket.poll();peer.poll();await Engine.get_main_loop().process_frame
			var bytes:PackedByteArray=peer.get_packet() if peer.get_available_packet_count()>0 else PackedByteArray();var codec=load("res://network/protobuf.gd").new();var packet:Dictionary=codec.decode("ClientEnvelope",bytes);var body:Dictionary=codec.decode(job.schema,packet.get("payload",PackedByteArray()));var row:Dictionary=p.telemetry[-1] if not p.telemetry.is_empty() else {}
			checks[job.name]=sent and codec.error.is_empty() and row.get("packet_battle_id")==body.get(job.field,"")
	else:checks["edge owned WebSocket open"]=false
	w.socket.close();peer.close();listener.stop();_free(c)
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual encoded payload compared with metadata;no authority world"}

func run_authority_integrity_edges() -> Dictionary:
	var checks={};var c=_case();var p=c.probe
	var incomplete=_snapshot(_room());incomplete.erase("room_revision");p._on_event("room.snapshot",incomplete);p._on_event("room.snapshot",_snapshot(_room()));var row:Dictionary=p.telemetry[-1]
	checks["incomplete revision cannot suppress first complete authority state"]=row.get("authority_state",{}).get("state_evidence_quality")=="Complete" and row.get("authority_state",{}).get("snapshot",{}).get("room_revision")==40
	incomplete=_snapshot(_room(true));incomplete.erase("_sequence");p._on_event("room.snapshot",incomplete);p._on_event("room.snapshot",_snapshot(_room(true)));row=p.telemetry[-1]
	checks["missing sequence cannot suppress next complete PVP transition"]=row.get("authority_state",{}).get("state_evidence_quality")=="Complete" and row.get("authority_state",{}).get("sequence")==10 and row.get("authority_state",{}).get("snapshot",{}).get("active_battle_id")=="duel"
	var actionbar=_room();actionbar.player.phase="ActionBar";actionbar.allowed_actions=[];incomplete=_snapshot(actionbar);incomplete.allowed_actions={};p._on_event("room.snapshot",incomplete);p._on_event("room.snapshot",_snapshot(actionbar));row=p.telemetry[-1]
	checks["malformed permission list cannot suppress valid empty permissions"]=row.get("authority_state",{}).get("state_evidence_quality")=="Complete" and row.get("authority_state",{}).get("snapshot",{}).get("allowed_actions_valid",false)
	_free(c);return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE incomplete snapshot dedup integrity;no authority world"}
