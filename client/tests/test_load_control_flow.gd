extends RefCounted
class GatewayStub extends Node:
 var online: bool=false
 var session_generation: int=0
 var telemetry_context: Dictionary={}
 func new_id() -> String:return "00000000000000000000000000000000"
class GameStub extends Node:
 var gateway: Node
 var room: Dictionary={}
 var lobby: Dictionary={}
 var ready_prompt: Dictionary={}
 var _class_switch_request_active: bool=false
 var login_started: bool=false
 var login_context: Dictionary={}
 var class_started: bool=false
 var mode: String="login"
 var permitted: Array=[]
 var commands: Array=[]
 var selected_cards: Array=[]
 var play_calls: int=0
 func login(_url: String,_name: String) -> void:
  login_context=gateway.telemetry_context.duplicate(true)
  login_started=true;await Engine.get_main_loop().process_frame
  if mode=="class":lobby={"player":{"selectedClass":"Guardian"}};gateway.online=true
 func select_class(_hero: String) -> void:class_started=true;_class_switch_request_active=true
 func allowed(action: String) -> bool:return permitted.has(action)
 func command(action: String,payload: Dictionary={}) -> bool:commands.append({"action":action,"payload":payload.duplicate(true)});return true
 func toggle_card(id: String) -> void:selected_cards.append(id)
 func play_cards() -> void:play_calls+=1
class Probe extends "res://tests/gameplay_load_client.gd":
 var cleanup_calls: int=0
 var finish_calls: Array=[]
 var expedition_calls: int=0
 var selection_calls: int=0
 func _ready() -> void:set_process(false)
 func _graceful_cleanup() -> void:cleanup_calls+=1
 func _finish(ok: bool,message: String,exit_code: int=-1) -> void:finish_calls.append({"ok":ok,"message":message,"exit_code":exit_code})
 func _run_expedition() -> void:expedition_calls+=1
 func _select_cards(hand: Array) -> Array:selection_calls+=1;return hand.map(func(card):return str(card.instance_id))
func run_test() -> Dictionary:
 var checks: Dictionary={};var tree=Engine.get_main_loop();var root: String=OS.get_environment("LOAD073_NATIVE_ROOT")
 if root.is_empty():root=ProjectSettings.globalize_path("user://load-control-"+str(Time.get_ticks_usec()))
 DirAccess.make_dir_recursive_absolute(root)
 for mode in ["login","class"]:
  var game:=GameStub.new();var gateway:=GatewayStub.new();game.gateway=gateway;game.mode=mode;var probe:=Probe.new();tree.root.add_child(probe);probe.Game=game;probe.run_id="stop-control";probe.client_id=mode;probe.process_epoch="fixture";probe.report_path=root+"/stop-"+mode+".json";probe.stop_file=root+"/STOP-"+mode+".request";probe.last_status_at_ms=Time.get_ticks_msec();probe._run()
  var until_ms: int=Time.get_ticks_msec()+3000
  while not (game.login_started if mode=="login" else game.class_started) and Time.get_ticks_msec()<until_ms:await tree.process_frame
  checks[mode+" login captures owner before first asynchronous call"] = game.login_context.get("run_id")=="stop-control" and game.login_context.get("client_id")==mode and game.login_context.get("process_epoch")=="fixture" and game.login_context.get("cycle_id")==mode+":1" and game.login_context.get("phase")=="login"
  var reached: bool=game.login_started if mode=="login" else game.class_started
  FileAccess.open(probe.stop_file,FileAccess.WRITE).store_string("owned STOP control");probe._process(0.0)
  while probe.finish_calls.is_empty() and Time.get_ticks_msec()<until_ms:await tree.process_frame
  checks[mode+" STOP follows real run/login branch into cleanup and cancelled0"] = reached and probe.stop_requested and probe.cleanup_calls==1 and probe.finish_calls.size()==1 and not probe.finish_calls[0].ok and probe.finish_calls[0].exit_code==0 and probe.expedition_calls==0
  checks[mode+" STOP is not a false login or hero-confirmation failure"] = not probe.checks.any(func(row):return not row.passed) and (not game.class_started if mode=="login" else game._class_switch_request_active)
  probe.queue_free();await tree.process_frame;game.free();gateway.free()
 var game:=GameStub.new();var gateway:=GatewayStub.new();game.gateway=gateway;var probe:=Probe.new();probe.Game=game
 game.permitted=["battle.select_target"];game.room={"pve":{"battle_id":"fixture-battle","current_target_id":"dead","monsters":[{"monster_id":"dead","hp":0},{"monster_id":"live","hp":1}]},"player":{"hand":[]}}
 checks["dead current target selects first living target exactly once"] = probe._try_battle_action() and game.commands==[{"action":"battle.select_target","payload":{"battle_id":"fixture-battle","target_id":"live"}}]
 game.permitted=["battle.play_cards"];game.room={"pve":{},"player":{"hand":[{"instance_id":"one"},{"instance_id":"two"}]}};game.commands=[]
 checks["play branch forwards selected order once"] = probe._try_battle_action() and game.selected_cards==["one","two"] and game.play_calls==1 and probe.selection_calls==1
 game.room.player.hand=[]
 checks["empty-hand branch preserves old wait/continue without fake play"] = probe._try_battle_action() and game.play_calls==1
 game.permitted=[];checks["non-battle phase falls through to other legal actions"] = not probe._try_battle_action()
 game.permitted=["battle.abandon"];probe.load_profile="functional-cycles";probe.last_effective_ms=Time.get_ticks_msec()-60001
 checks["functional cycles never use cyclic stagnation fallback"] = not probe._try_stagnation_fallback()
 probe.load_profile="cyclic-gameplay";probe.last_effective_ms=Time.get_ticks_msec()-59900
 checks["pre60second controlled boundary does not abandon"] = not probe._try_stagnation_fallback()
 probe.started_at_ms=Time.get_ticks_msec()-1000;probe.started_process_frames=Engine.get_process_frames()-10;var clock: Dictionary=probe._frame_clock_observation()
 checks["frame clock names process frames without claiming rendered FPS"] = clock.process_frames>=10 and clock.observed_ms>=1000 and clock.mean_process_fps>0 and str(clock.scope).contains("not rendered FPS")
 probe.free();game.free();gateway.free();return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual load control flow with explicit coroutine/backend stubs;cleanup/finish observed only,not actual asset cleanup or new battle/60second LIVE evidence"}
