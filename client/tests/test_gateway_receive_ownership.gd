extends RefCounted
const Gateway=preload("res://network/gateway.gd")
const Proto=preload("res://network/protobuf.gd")
class Probe extends "res://tests/gameplay_load_client.gd":
 func _ready() -> void:set_process(false)
class StubGame extends Node:
 var room: Dictionary={"room_id":"observer-room","match_id":"observer-match"}
 var ready_prompt: Dictionary={}
func packet(kind: String,sequence: int,payload: Dictionary={},request_id: String="") -> PackedByteArray:
 var codec:=Proto.new();var schemas: Dictionary={"pong":"PongEvent","match.found":"MatchFoundEvent","room.started":"RoomStartedEvent"}
 var envelope: Dictionary={"protocol_version":1,"type":kind,"sequence":sequence,"request_id":request_id}
 if not payload.is_empty():envelope.payload=codec.encode(schemas[kind],payload)
 return codec.encode("ServerEnvelope",envelope)
func run_test() -> Dictionary:
 var checks: Dictionary={};var tree=Engine.get_main_loop();var gateway:=Gateway.new();gateway.persist_session=false;tree.root.add_child(gateway);gateway.set_process(false)
 var probe:=Probe.new();var game:=StubGame.new();probe.Game=game;probe.run_id="observer-run";probe.client_id="observer-client";probe.process_epoch="observer-process";probe.cycles_completed=6;probe.stage="settlement"
 gateway.telemetry.connect(probe._on_telemetry)
 var listener:=TCPServer.new();var peer:=WebSocketPeer.new();var accepted: bool=false
 if listener.listen(0,"127.0.0.1")!=OK:gateway.free();probe.free();game.free();return {"ok":false,"checks":{"owned listener":false}}
 gateway.socket.connect_to_url("ws://127.0.0.1:"+str(listener.get_local_port()));var deadline: int=Time.get_ticks_msec()+3000
 while Time.get_ticks_msec()<deadline:
  gateway.socket.poll()
  if not accepted and listener.is_connection_available():peer.accept_stream(listener.take_connection());accepted=true
  if accepted:peer.poll()
  if gateway.socket.get_ready_state()==WebSocketPeer.STATE_OPEN and peer.get_ready_state()==WebSocketPeer.STATE_OPEN:break
  await tree.process_frame
 checks["actual owned WebSocket is open"] = gateway.socket.get_ready_state()==WebSocketPeer.STATE_OPEN
 gateway.telemetry_context={"run_id":"dispatch-run","client_id":"dispatch-client","process_epoch":"dispatch-process","cycle_id":"dispatch-client:1","phase":"playing"};gateway.room_id="dispatch-room";gateway.current_match_id="dispatch-match";gateway.room_context_epoch=1
 var origin: Dictionary=gateway.capture_context();var sent: bool=gateway.send("ping")
 while peer.get_available_packet_count()==0 and Time.get_ticks_msec()<deadline:gateway.socket.poll();peer.poll();await tree.process_frame
 var wire: PackedByteArray=peer.get_packet() if peer.get_available_packet_count()>0 else PackedByteArray();var codec:=Proto.new();var decoded: Dictionary=codec.decode("ClientEnvelope",wire);var rid: String=str(decoded.get("request_id",""))
 gateway.telemetry_context={"run_id":"later-run","client_id":"later-client","process_epoch":"later-process","cycle_id":"later-client:7","phase":"settlement"}
 peer.put_packet(packet("pong",0,{},rid));deadline=Time.get_ticks_msec()+3000
 while gateway.socket.get_available_packet_count()==0 and Time.get_ticks_msec()<deadline:gateway.socket.poll();peer.poll();await tree.process_frame
 if gateway.socket.get_available_packet_count()>0:gateway._receive(gateway.socket.get_packet())
 var rtts: Array=probe.telemetry.filter(func(v):return v.type=="rtt")
 checks["actual ping and received pong retain frozen dispatch context across observer change"] = sent and not rid.is_empty() and rtts.size()==1 and origin.keys().all(func(k):return rtts[0].get(k)==origin[k])
 checks["RTT keeps actual correlation key and elapsed clock"] = rtts.size()==1 and rtts[0].request_id==rid and rtts[0].duration_ms>=0
 gateway._receive(packet("pong",0))
 checks["uncorrelated pong cannot invent another RTT"] = probe.telemetry.filter(func(v):return v.type=="rtt").size()==1
 var receiver: Dictionary={"run_id":"receive-run","client_id":"receive-client","process_epoch":"receive-process","cycle_id":"receive-client:7","phase":"settlement"};gateway.telemetry_context=receiver.duplicate(true)
 gateway.event_received.connect(func(_kind,_payload):gateway.telemetry_context={"run_id":"reentered-run","client_id":"reentered-client","process_epoch":"reentered-process","cycle_id":"reentered-client:8","phase":"cleanup"})
 gateway.event_received.connect(probe._on_event)
 gateway._receive(packet("match.found",1,{"match_id":"receive-match","room_id":"receive-room"}))
 var pushes: Array=probe.telemetry.filter(func(v):return v.get("event_type")=="match.found" and v.type=="lifecycle");var push: Dictionary=pushes[-1] if not pushes.is_empty() else {}
 checks["uncorrelated push owner is captured before reentrant event callbacks"] = not push.is_empty() and ["run_id","client_id","process_epoch"].all(func(k):return push.get(k)==receiver[k]) and push.get("record_owner_source")=="gateway_receive"
 checks["uncorrelated push keeps unknown business cycle and phase"] = push.get("cycle_id")=="Unknown" and push.get("phase")=="Unknown" and push.get("origin_context_state")=="Unknown"
 var prior: Dictionary=origin.duplicate(true);gateway._pending_request_started["prior-request"]={"action":"room.snapshot.read","started_at":Time.get_ticks_msec(),"context":prior}
 gateway._receive(packet("room.started",1,{"room_id":"prior-room","match_id":"prior-match"},"prior-request"));var guards: Array=probe.telemetry.filter(func(v):return v.type=="lifecycle_guard");var guard: Dictionary=guards[-1] if not guards.is_empty() else {}
 checks["guard prefers known original dispatch over current receiver"] = not guard.is_empty() and origin.keys().all(func(k):return guard.get(k)==origin[k]) and guard.get("record_owner_source")=="dispatch"
 gateway._pending_request_started["missing-request"]={"action":"room.snapshot.read","started_at":Time.get_ticks_msec(),"context":{}}
 gateway._receive(packet("room.started",1,{"room_id":"prior-room","match_id":"prior-match"},"missing-request"));guards=probe.telemetry.filter(func(v):return v.type=="lifecycle_guard");guard=guards[-1]
 checks["missing correlated origin cannot borrow receive owner or current cycle"] = guard.run_id=="Unknown" and guard.client_id=="Unknown" and guard.cycle_id=="Unknown" and guard.phase=="Unknown" and guard.record_owner_source=="dispatch"
 probe._on_event("player.died",{"player_id":"fixture-player","_origin_context":null,"_receive_owner_context":receiver});var null_origin: Dictionary=probe.telemetry[-1]
 checks["malformed null correlated origin remains unknown despite receive hint"] = null_origin.run_id=="Unknown" and null_origin.cycle_id=="Unknown"
 gateway.socket.close();peer.close();listener.stop();gateway.end_session("",false);gateway.queue_free();await tree.process_frame;probe.free();game.free()
 return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual Gateway send/receive and recorder;actual owned WebSocket ping/pong,explicit binary push/guard fixtures;no backend or capacity claim"}
