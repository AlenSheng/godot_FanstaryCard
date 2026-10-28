extends RefCounted
const Gateway=preload("res://network/gateway.gd")
func run_test() -> Dictionary:
 var checks: Dictionary={};var tree=Engine.get_main_loop();var names: Array[String]=["FANTASYCARD_LOAD_RUN_ID","FANTASYCARD_LOAD_CLIENT_ID","FANTASYCARD_LOAD_PROCESS_EPOCH"];var original: Dictionary={}
 for name in names:original[name]={"present":OS.has_environment(name),"value":OS.get_environment(name)}
 for mode in ["complete","missing-client","missing-epoch","normal-client"]:
  OS.set_environment(names[0],"bootstrap-run" if mode!="normal-client" else "")
  OS.set_environment(names[1],"bootstrap-client" if mode!="missing-client" else "")
  OS.set_environment(names[2],"bootstrap-process" if mode!="missing-epoch" else "")
  var gateway:=Gateway.new();gateway.persist_session=false;tree.root.add_child(gateway);gateway.set_process(false)
  if mode=="complete":
   var context: Dictionary=gateway.capture_context()
   checks["provided worker identity is present immediately after ready before a requester"] = context.get("run_id")=="bootstrap-run" and context.get("client_id")=="bootstrap-client" and context.get("process_epoch")=="bootstrap-process"
   checks["bootstrap is initial phase and existing first cycle identity without completion credit"] = context.get("phase")=="initial" and context.get("cycle_id")=="bootstrap-client:1"
   checks["known empty room and match stay empty at bootstrap"] = context.get("room_id")=="" and context.get("match_id")==""
   checks["bootstrap identity does not start session or reset replay beyond fresh defaults"] = gateway.session_generation==0 and gateway.last_sequence==0
  else:checks[mode+" cannot invent complete worker identity"] = gateway.telemetry_context.is_empty()
  gateway.end_session("",false);gateway.queue_free();await tree.process_frame
 for name in names:
  if original[name].present:OS.set_environment(name,str(original[name].value))
  else:OS.unset_environment(name)
 return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual Gateway._ready with explicitly controlled worker environment;no HTTP/asset/capacity claim"}
