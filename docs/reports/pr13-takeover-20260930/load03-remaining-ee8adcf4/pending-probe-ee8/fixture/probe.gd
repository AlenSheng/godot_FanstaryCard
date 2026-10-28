extends SceneTree
const Gateway = preload("res://network/gateway.gd")
var gateway: Node
var samples: Array = []
var finished := false
func _initialize() -> void: _run.call_deferred()
func _collect(sample: Dictionary) -> void: samples.append(sample.duplicate(true))
func _pending() -> void:
 await gateway.request("/api/v1/client-info?pending=1")
 finished = true
func _run() -> void:
 gateway = Gateway.new()
 gateway.persist_session = false
 root.add_child(gateway)
 gateway.telemetry.connect(_collect)
 gateway.telemetry_context = {"phase":"playing", "cycle_id":"M-cycle", "match_id":"M"}
 var first: Dictionary = await gateway.request("/api/v1/client-info")
 _pending()
 await create_timer(.5).timeout
 var paused := {"first_ok": first.ok, "production_pending_http": gateway._pending_http.size(),
  "production_pending_origins": gateway._http_origin_contexts.size(), "samples": samples.duplicate(true),
  "harness_invocations_started": 2, "harness_invocations_finished": 1}
 gateway.telemetry_context = {"phase":"settlement", "cycle_id":"N-cycle", "match_id":"N"}
 var http := HTTPRequest.new()
 root.add_child(http)
 http.request(OS.get_environment("FANTASYCARD_SERVER_URL") + "/fixture/release")
 await http.request_completed
 http.queue_free()
 var deadline := Time.get_ticks_msec()+3000
 while not finished and Time.get_ticks_msec()<deadline: await process_frame
 var result := {"paused":paused, "finished":finished, "final_samples":samples,
  "pending_after":gateway._pending_http.size(),"source":"f812 Gateway unchanged"}
 var file := FileAccess.open(OS.get_environment("PROBE_RESULT"), FileAccess.WRITE)
 file.store_string(JSON.stringify(result));file.close()
 print(JSON.stringify({"probe_complete":true,"finished":finished}))
 gateway._reusable_http.close()
 gateway.queue_free()
 await process_frame
 quit(0 if finished and first.ok else 1)
