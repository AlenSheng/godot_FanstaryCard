extends RefCounted
class Probe extends "res://tests/gameplay_load_client.gd":
 func _ready() -> void:set_process(false)
class StubGame extends Node:
 var room: Dictionary={}
class SettlementGame extends Node:
 var room: Dictionary={}
 var lobby: Dictionary={"configVersion":"explicit-offline-context-fixture"}
 var preparation: Dictionary={}
 var ticket: Dictionary={}
 var settlement: Dictionary={}
 var gateway: Node
 var probe: Node
 var dispatched: Dictionary={}
 var dispatched_stage: String=""
 func prepare(_tier: String,_potions: int) -> void:preparation={"preparationId":"fixture-preparation"}
 func enqueue() -> void:
  ticket={"ticketId":"fixture-ticket"};room={"match_id":"fixture-match","room_id":"fixture-room"};settlement={"matchId":"fixture-match"};probe.active_match_id="fixture-match"
  # Model the actual cloud counterexample: last process-frame snapshot was
  # playing, then the expedition coroutine reaches ACK before another frame.
  gateway.telemetry_context={"phase":"playing","cycle_id":"context-fixture:2"}
 func allowed(_action: String) -> bool:return false
 func acknowledge_settlement() -> bool:
  dispatched=gateway.telemetry_context.duplicate(true);dispatched_stage=probe.stage
  await Engine.get_main_loop().process_frame
  room={};settlement={};return true
class SettlementGateway extends Node:
 var online:=true
 var telemetry_context: Dictionary={}
class CleanupGateway extends SettlementGateway:
 var session_generation:=7
class CleanupGame extends Node:
 var room: Dictionary={}
 var preparation: Dictionary={"preparationId":"cleanup-preparation"}
 var ticket: Dictionary={"ticketId":"cleanup-ticket","preparationId":"cleanup-preparation"}
 var settlement: Dictionary={}
 var gateway: Node
 var commands: Array=[]
 func allowed(action: String) -> bool:return action=="battle.abandon" and not room.is_empty()
 func command(action: String) -> bool:
  commands.append({"action":action,"match_id":room.get("match_id","")});settlement={"matchId":room.get("match_id","")};room={};return true
class CleanupProbe extends Probe:
 var wait_action: Callable
 var waits:=0
 func _wait(_seconds: float) -> void:
  waits+=1
  if wait_action.is_valid():wait_action.call()
  await Engine.get_main_loop().process_frame
func run_test() -> Dictionary:
 var checks: Dictionary={};var probe:=Probe.new();var game:=StubGame.new();probe.Game=game;probe.run_id="observer-current-run";probe.client_id="observer-current-client";probe.process_epoch="observer-current-process";probe.cycles_completed=6;probe.stage="settlement";probe.active_match_id="current-match";game.room={"room_id":"current-room","match_id":"current-match"}
 var origin: Dictionary={"run_id":"dispatch-run","client_id":"dispatch-client","process_epoch":"dispatch-process","cycle_id":"dispatch-client:1","phase":"playing","room_id":"old-room","match_id":"old-match","logical_request_id":"stable-logical"}
 probe._on_telemetry(origin.merged({"type":"http","status":200},true));var row: Dictionary=probe.telemetry[-1]
 checks["captured source identity remains immutable"] = origin.keys().all(func(k):return row.get(k)==origin[k]) and row.observer_context.client_id=="observer-current-client"
 probe._on_telemetry({"type":"http","logical_request_id":"missing-origin","room_id":"","match_id":"","status":200});row=probe.telemetry[-1]
 checks["missing asynchronous context is Unknown not current cycle"] = row.origin_context_state=="Unknown" and row.cycle_id=="Unknown" and row.phase=="Unknown" and row.room_id=="" and row.match_id==""
 probe.stop_requested=true;probe._on_telemetry(origin.merged({"type":"http_attempt","status":200},true));row=probe.telemetry[-1]
 checks["STOP drain window is separate from original business phase"] = row.observation_phase=="drain" and row.phase=="playing" and row.cycle_id=="dispatch-client:1"
 probe._on_telemetry({"type":"lifecycle","event_type":"local.control"});row=probe.telemetry[-1]
 checks["local synchronous context remains local"] = row.origin_context_state=="Local" and row.cycle_id=="observer-current-client:7" and row.phase=="settlement"
 probe._on_telemetry({"type":"http","logical_request_id":"null-origin","_origin_context":null});row=probe.telemetry[-1]
 checks["malformed null origin remains explicitly unknown"] = row.origin_context_state=="Unknown" and row.phase=="Unknown"
 checks["no diagnostic HTTP traffic becomes gameplay progress"] = probe.telemetry.all(func(v):return not v.gameplay_progress)
 probe.free();game.free()
 var settlement_game:=SettlementGame.new();var settlement_gateway:=SettlementGateway.new();var settlement_probe:=Probe.new();Engine.get_main_loop().root.add_child(settlement_probe);settlement_game.gateway=settlement_gateway;settlement_game.probe=settlement_probe;settlement_probe.Game=settlement_game;settlement_probe.run_id="context-run";settlement_probe.client_id="context-fixture";settlement_probe.process_epoch="context-epoch";settlement_probe.cycles_completed=1;settlement_probe.stage="expedition"
 await settlement_probe._run_expedition()
 checks["ACK dispatch captures settlement phase before next process frame"] = settlement_game.dispatched_stage=="settlement" and settlement_game.dispatched.get("phase")=="settlement"
 checks["settlement context refresh preserves cycle identity and original successful completion"] = settlement_game.dispatched.get("run_id")=="context-run" and settlement_game.dispatched.get("cycle_id")=="context-fixture:2" and settlement_probe.scenario_finished and settlement_probe.checks.all(func(v):return v.passed)
 settlement_probe.free();settlement_game.free();settlement_gateway.free()
 for mode in ["late-current","changed-session","foreign-room","unverified","already-current","ticket-released"]:
  var cleanup_game:=CleanupGame.new();var cleanup_gateway:=CleanupGateway.new();var cleanup_probe:=CleanupProbe.new();Engine.get_main_loop().root.add_child(cleanup_probe);cleanup_game.gateway=cleanup_gateway;cleanup_probe.Game=cleanup_game;cleanup_probe.active_match_id="cleanup-match";cleanup_probe.verified_ready_match_id="" if mode=="unverified" else "cleanup-match";cleanup_probe.stage="cleanup";cleanup_probe.client_id="cleanup-fixture";cleanup_probe.run_id="cleanup-run";cleanup_probe.process_epoch="cleanup-epoch";cleanup_probe.stop_requested=true
  if mode=="already-current":cleanup_game.room={"match_id":"cleanup-match","room_id":"cleanup-room"}
  cleanup_probe.wait_action=func():
   if mode=="ticket-released":cleanup_game.ticket={}
   else:cleanup_game.room={"match_id":"foreign-match" if mode=="foreign-room" else "cleanup-match","room_id":"cleanup-room"}
   if mode=="changed-session":cleanup_gateway.session_generation+=1
  await cleanup_probe._drain_cleanup_room(7,"cleanup-match","cleanup-preparation","cleanup-ticket")
  var should_exit: bool=mode in ["late-current","already-current"]
  checks["STOP late join route guard "+mode] = cleanup_game.commands.size()==(1 if should_exit else 0) and (not should_exit or cleanup_game.commands[0].match_id=="cleanup-match") and cleanup_probe.cycles_completed==0
  checks["STOP late join wait budget path "+mode] = cleanup_probe.waits==(0 if mode in ["unverified","already-current"] else 1)
  cleanup_probe.free();cleanup_game.free();cleanup_gateway.free()
 return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE production recorder, original expedition dispatch and late READY STOP route guards with explicit fixture values/no world/network; actual cloud counterexamples retained separately"}
