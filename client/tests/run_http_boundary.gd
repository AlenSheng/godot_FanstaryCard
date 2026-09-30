extends SceneTree
const Reusable = preload("res://network/reusable_http_client.gd")
var failures: Array[String] = []

func _initialize() -> void: call_deferred("_run")

func _run() -> void:
	var client := Reusable.new()
	var origin := OS.get_environment("FANTASYCARD_SERVER_URL")
	for path in ["/length", "/length", "/close-length", "/close-body", "/chunked", "/empty", "/head", "/truncated", "/truncated-chunk", "/limit", "/slow", "/idle-close", "/length"]:
		var method := HTTPClient.METHOD_HEAD if path == "/head" else HTTPClient.METHOD_GET
		var response: Array = await client.request(self, origin, path, method,
			PackedStringArray(), PackedByteArray(), 200 if path == "/slow" else 2000, 100 if path == "/limit" else 4096)
		var expected_success: bool = path not in ["/truncated", "/truncated-chunk", "/limit", "/slow"]
		var passed: bool = (response[0] == HTTPRequest.RESULT_SUCCESS) == expected_success
		if expected_success:
			passed = passed and int(response[1]) in [200, 204]
			passed = passed and response[3].get_string_from_utf8() == ("" if path in ["/head", "/empty"] else "abcdef")
		if not passed: failures.append(path)
		print(JSON.stringify({"path": path, "passed": passed, "result": response[0], "status": response[1], "bytes": response[3].size(), "reused": response[4]}))
		if path == "/idle-close": await create_timer(.2).timeout
	client.close()
	print(JSON.stringify({"suite": "http-boundary", "ok": failures.is_empty(), "failures": failures}))
	quit(0 if failures.is_empty() else 1)
