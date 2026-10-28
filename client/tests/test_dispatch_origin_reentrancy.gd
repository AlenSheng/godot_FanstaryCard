extends RefCounted
class OfflineStore extends "res://state/game_store.gd":
 func _ready() -> void:set_process(false)
class Probe extends "res://tests/gameplay_load_client.gd":
 func _ready() -> void:set_process(false)
func run_test() -> Dictionary:
 var checks: Dictionary={};var gateway=load("res://network/gateway.gd").new();gateway.persist_session=false;gateway.online=true;gateway.current_match_id="dispatch-match";gateway.room_id="dispatch-room";gateway.room_context_epoch=1;gateway.room_revision=1;gateway.telemetry_context={"run_id":"origin-run","client_id":"origin-client","process_epoch":"origin-process","cycle_id":"origin-client:1","phase":"playing"}
 var listener:=TCPServer.new();var peer:=WebSocketPeer.new();var accepted: bool=false
 if listener.listen(0,"127.0.0.1")!=OK:gateway.free();return {"ok":false,"checks":{"owned actual listener":false}}
 gateway.socket.connect_to_url("ws://127.0.0.1:"+str(listener.get_local_port()));var deadline: int=Time.get_ticks_msec()+3000
 while Time.get_ticks_msec()<deadline:
  gateway.socket.poll()
  if not accepted and listener.is_connection_available():peer.accept_stream(listener.take_connection());accepted=true
  if accepted:peer.poll()
  if peer.get_ready_state()==WebSocketPeer.STATE_OPEN and gateway.socket.get_ready_state()==WebSocketPeer.STATE_OPEN:break
  await Engine.get_main_loop().process_frame
 checks["owned real WebSocket is open"] = gateway.socket.get_ready_state()==WebSocketPeer.STATE_OPEN
 var store:=OfflineStore.new();store.gateway=gateway;store.room={"room_id":"dispatch-room","match_id":"dispatch-match","room_revision":1,"allowed_actions":["battle.abandon"]};var probe:=Probe.new();probe.Game=store;probe.active_match_id="dispatch-match";probe.stage="playing";probe.load_profile="cyclic-gameplay";probe.last_effective_ms=Time.get_ticks_msec()-60001
 var original: Dictionary=gateway.capture_context();var trace: Array=[]
 gateway.telemetry.connect(func(sample):trace.append(sample.duplicate(true)))
 gateway.telemetry.connect(func(sample):
  if sample.get("type")=="command_lifecycle" and sample.get("action")=="battle.abandon":
   gateway.current_match_id="later-match";gateway.room_id="later-room";gateway.room_context_epoch=2;gateway.room_revision=2;store.room={"room_id":"later-room","match_id":"later-match","room_revision":2,"allowed_actions":[]};gateway.telemetry_context={"run_id":"later-run","client_id":"later-client","process_epoch":"later-process","cycle_id":"later-client:2","phase":"settlement"})
 var selected: bool=probe._try_stagnation_fallback();var fallback: Array=probe.telemetry.filter(func(v):return v.get("event_type")=="battle.abandon.fallback")
 checks["real fallback command was selected and dispatched"] = selected and trace.any(func(v):return v.get("event_type")=="command.sent" and v.get("action")=="battle.abandon")
 checks["fallback telemetry captured before reentrant send observer changed context"] = fallback.size()==1 and original.keys().all(func(k):return fallback[0].get(k)==original[k])
 var pending: Array=store._pending_commands.values()
 checks["store pending command captures dispatch origin before synchronous signals"] = pending.size()==1 and original.keys().all(func(k):return pending[0].origin_context.get(k)==original[k])
 checks["pending route revision and sound owner remain at dispatch"] = pending.size()==1 and pending[0].room_id=="dispatch-room" and pending[0].sent_revision==1 and store._sound_commands.values()[0].room_id=="dispatch-room"
 var until_ms: int=Time.get_ticks_msec()+1000
 while peer.get_available_packet_count()==0 and Time.get_ticks_msec()<until_ms:gateway.socket.poll();peer.poll();await Engine.get_main_loop().process_frame
 var wire: PackedByteArray=peer.get_packet() if peer.get_available_packet_count()>0 else PackedByteArray();var proto=load("res://network/protobuf.gd").new();var packet: Dictionary=proto.decode("ClientEnvelope",wire)
 checks["actual packet still targets original room and match"] = packet.get("room_id")=="dispatch-room" and packet.get("match_id")=="dispatch-match" and packet.get("type")=="battle.abandon"
 gateway.socket.close();peer.close();listener.stop();probe.free();store.free();gateway.free();return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE real GameStore.command/Gateway.send and real ownedWebSocket;explicit synchronous metadata callback control,no actual authority world or natural60second wait"}
