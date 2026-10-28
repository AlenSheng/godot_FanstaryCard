extends RefCounted
class TerminalGateway extends "res://network/gateway.gd":
 var failure: int=HTTPRequest.RESULT_BODY_DECOMPRESS_FAILED
 var calls: int=0
 func _request_http_transport(_path: String,_method: int,_headers: PackedStringArray,_body: PackedByteArray,_timeout_ms: int=10000) -> Array:
  calls+=1
  return [failure,0,PackedStringArray(),PackedByteArray(),false]
func run_test() -> Dictionary:
 var checks: Dictionary={}
 for failure in [HTTPRequest.RESULT_BODY_DECOMPRESS_FAILED,HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED]:
  for method in [HTTPClient.METHOD_GET,HTTPClient.METHOD_POST]:
   var gateway:=TerminalGateway.new();gateway.persist_session=false;gateway.failure=failure;var samples: Array=[]
   Engine.get_main_loop().root.add_child(gateway);gateway.set_process(false)
   gateway.accept_session("fixture-player-A","2099-01-01T00:00:00Z","fixture-A")
   gateway.telemetry.connect(func(v):samples.append(v.duplicate(true)))
   var path: String="/api/v1/players/me" if method==HTTPClient.METHOD_GET else "/api/v1/shop/purchases"
   var result: Dictionary=await gateway.request(path,method,null if method==HTTPClient.METHOD_GET else {"productId":"fixture-only","quantity":1},[0])
   checks[str(failure)+"/"+str(method)+" terminal failure has exactly one attempt"] = gateway.calls==1 and not result.get("ok",true) and not result.has("data")
   checks[str(failure)+"/"+str(method)+" terminal failure reports zero retry wait"] = samples.size()==2 and samples.all(func(v):return v.get("retry_backoff_ms",-1)==0)
   gateway.end_session("",false);gateway.queue_free();await Engine.get_main_loop().process_frame
 return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual request policy with explicit terminal transport results; no wire or asset claim"}
