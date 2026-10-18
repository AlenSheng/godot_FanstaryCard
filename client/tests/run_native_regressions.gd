extends Node
var rows: Array=[]
func _ready() -> void:
 Game.set_process(false);Game.gateway.end_session("",false);Game.gateway.base_url="http://127.0.0.1:1";Sound.set_process(false);Sound.set_music_context("");Sound.stop_all();Sound.stop_music();call_deferred("run")
func run() -> void:
 for name in ["test_command_state_observation.gd","test_active_battle_observation.gd","test_reward_claim_confirmation.gd","test_confirmation_snapshot.gd","test_late_ready_rejection.gd","test_gateway_receive_ownership.gd","test_gateway_bootstrap_context.gd","test_session_sequence.gd","test_gateway_replay.gd","test_terminal_command_context.gd","test_load_progress.gd","test_load_audit_storage.gd","test_ready_deadline_guard.gd","test_load_contexts.gd","test_dispatch_origin_reentrancy.gd","test_load_control_flow.gd"]:
  var path: String="res://tests/"+name
  var script: Script=load(path) if ResourceLoader.exists(path) else null
  var result: Dictionary
  if script==null:result={"ok":false,"error":"required_test_source_unavailable","path":path}
  else:
   var suite=script.new();result=await suite.run_test();suite=null
  rows.append({"suite":name,"result":result});print(JSON.stringify(rows[-1]));await get_tree().process_frame
 Sound.set_process(false);Sound.set_music_context("");Sound.stop_all();Sound.stop_music();await get_tree().create_timer(.35).timeout
 var report: Dictionary={"ok":rows.all(func(v):return v.result.get("ok",false)),"suites":rows,"scope":"OFFLINE native client regressions,owned local sockets and files,no real login/world"}
 var output: String=OS.get_environment("NATIVE_REGRESSION_REPORT")
 if output.is_empty():output="user://native-regressions-%d-%d.json"%[OS.get_process_id(),Time.get_ticks_usec()]
 if FileAccess.file_exists(output):push_error("Use a new native regression report path");get_tree().quit(1);return
 FileAccess.open(output,FileAccess.WRITE).store_string(JSON.stringify(report));get_tree().quit(0 if report.ok else 1)
