extends SceneTree
const Http = preload("res://network/http_protocol.gd")
const Gateway = preload("res://network/gateway.gd")
var failures := []
func _initialize() -> void: call_deferred("run")
func measure(operation: Callable, expected: Dictionary) -> Dictionary:
	var before := OS.get_static_memory_usage()
	var start := Time.get_ticks_usec()
	var result: Dictionary = operation.call()
	var duration := float(Time.get_ticks_usec()-start)/1000.0
	var retained := OS.get_static_memory_usage()-before
	if result != expected: failures.append("decoded result differs")
	result.clear()
	return {"ms":duration,"retained_output_delta_bytes":retained,"post_release_delta_bytes":OS.get_static_memory_usage()-before}
func summarize(rows: Array) -> Dictionary:
	var times: Array = rows.map(func(row):return row.ms)
	times.sort()
	return {"iterations":rows.size(),"mean_ms":times.reduce(func(a,b):return a+b,0.0)/times.size(),"p50_ms":times[times.size()/2],"max_ms":times.back(),"mean_retained_output_delta_bytes":rows.reduce(func(a,b):return a+b.retained_output_delta_bytes,0.0)/rows.size(),"mean_post_release_delta_bytes":rows.reduce(func(a,b):return a+b.post_release_delta_bytes,0.0)/rows.size()}
func run() -> void:
	var baseline = load("res://baseline/http_protocol.gd")
	var body := FileAccess.get_file_as_bytes("res://data/bootstrap-real.pb")
	var contract := Http.route("/api/v1/bootstrap",HTTPClient.METHOD_GET)
	var headers := PackedStringArray(["Content-Type: application/protobuf"])
	var expected: Dictionary = baseline.decode_response(contract,200,headers,body)
	if not expected.ok:
		print("Invalid baseline sample"); quit(1); return
	var before := Callable(baseline,"decode_response").bind(contract,200,headers,body)
	var after := Callable(Http,"decode_response").bind(contract,200,headers,body)
	for i in range(3):
		before.call(); after.call()
	var peak_before := OS.get_static_memory_peak_usage()
	var before_rows := []
	var after_rows := []
	for i in range(20):
		if i % 2 == 0:
			before_rows.append(measure(before,expected)); after_rows.append(measure(after,expected))
		else:
			after_rows.append(measure(after,expected)); before_rows.append(measure(before,expected))
	var before_summary := summarize(before_rows)
	var after_summary := summarize(after_rows)
	if after_summary.mean_ms >= before_summary.mean_ms: failures.append("no measured CPU improvement")
	print(JSON.stringify({"sample_bytes":body.size(),"before":before_summary,"after":after_summary,"speedup":before_summary.mean_ms/after_summary.mean_ms,"process_static_peak_before_bytes":peak_before,"process_static_peak_after_bytes":OS.get_static_memory_peak_usage(),"memory_semantics":"Godot tracked static memory: retained output delta and post-release net delta; process peak is cumulative, not per-operation total allocations or resident memory","failures":failures}))
	quit(0 if failures.is_empty() else 1)
