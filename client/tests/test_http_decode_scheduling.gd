extends SceneTree
const Gateway = preload("res://network/gateway.gd")
const Http = preload("res://network/http_protocol.gd")
var tracking := false
var last_frame_us: int = 0
var frame_gaps := []
var failures := []
func _initialize() -> void:
	process_frame.connect(_frame)
	call_deferred("run")
func _frame() -> void:
	if not tracking: return
	var now := Time.get_ticks_usec()
	frame_gaps.append(float(now-last_frame_us)/1000.0)
	last_frame_us=now
func run() -> void:
	var body := FileAccess.get_file_as_bytes("res://data/bootstrap-real.pb")
	if body.size() <= 8192:
		print("Real bootstrap sample missing or below background threshold")
		quit(1); return
	var contract := Http.route("/api/v1/bootstrap",HTTPClient.METHOD_GET)
	var headers := PackedStringArray(["Content-Type: application/protobuf"])
	var gateway := Gateway.new()
	gateway.persist_session=false
	root.add_child(gateway)
	var baseline := []
	var worker := []
	var expected: Dictionary
	for i in range(4):
		var start := Time.get_ticks_usec()
		expected=Http.decode_response(contract,200,headers,body)
		if i > 0: baseline.append(float(Time.get_ticks_usec()-start)/1000.0)
	await process_frame
	for i in range(3):
		last_frame_us=Time.get_ticks_usec()
		tracking=true
		var decoded: Dictionary = await gateway._decode_http_response(contract,200,headers,body)
		tracking=false
		worker.append(decoded.decode_ms)
		if not decoded.ok or decoded.data != expected.data or not decoded.decode_worker: failures.append("background semantics differ")
		await process_frame
	var baseline_mean: float=baseline.reduce(func(a,b):return a+b,0.0)/baseline.size()
	var worker_mean: float=worker.reduce(func(a,b):return a+b,0.0)/worker.size()
	var max_gap: float=frame_gaps.max() if not frame_gaps.is_empty() else 0.0
	if frame_gaps.size()<3: failures.append("main thread did not advance during decode")
	if max_gap>=baseline_mean: failures.append("main thread longest frame not improved")
	print(JSON.stringify({"sample_bytes":body.size(),"inline_mean_ms":baseline_mean,"worker_wall_mean_ms":worker_mean,"frames_advanced":frame_gaps.size(),"max_frame_gap_ms":max_gap,"failures":failures}))
	gateway.queue_free()
	await process_frame
	quit(0 if failures.is_empty() else 1)
