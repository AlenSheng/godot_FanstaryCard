extends SceneTree
const Reusable = preload("res://network/reusable_http_client.gd")
var failures: Array[String] = []

func _initialize() -> void: call_deferred("_run")

func _run() -> void:
	var client := Reusable.new()
	var origin := OS.get_environment("FANTASYCARD_SERVER_URL")
	for path in ["/length", "/length", "/close-length", "/close-body", "/chunked", "/empty", "/head", "/truncated", "/truncated-chunk", "/limit", "/production-limit", "/bad-gzip", "/gzip", "/deflate", "/gzip-limit", "/slow", "/idle-close", "/length"]:
		var method := HTTPClient.METHOD_HEAD if path == "/head" else HTTPClient.METHOD_GET
		var response: Array = await client.request(self, origin, path, method,
			PackedStringArray(), PackedByteArray(), 200 if path == "/slow" else 2000, 100 if path == "/limit" else 2 * 1024 * 1024)
		var expected_success: bool = path not in ["/truncated", "/truncated-chunk", "/limit", "/production-limit", "/bad-gzip", "/gzip-limit", "/slow"]
		var passed: bool = (response[0] == HTTPRequest.RESULT_SUCCESS) == expected_success
		if expected_success:
			passed = passed and int(response[1]) in [200, 204]
			passed = passed and response[3].get_string_from_utf8() == ("" if path in ["/head", "/empty"] else "abcdef")
		else: passed = passed and response[3].is_empty()
		if not passed: failures.append(path)
		print(JSON.stringify({"path": path, "passed": passed, "result": response[0], "status": response[1], "bytes": response[3].size(), "reused": response[4]}))
		if path == "/idle-close": await create_timer(.2).timeout
	var invalid_tls := OS.get_environment("PR13_INVALID_TLS_ORIGIN")
	if not invalid_tls.is_empty():
		var tls_response: Array = await client.request(self, invalid_tls, "/length", HTTPClient.METHOD_GET, PackedStringArray(), PackedByteArray(), 2000)
		var tls_rejected: bool = tls_response[0] != HTTPRequest.RESULT_SUCCESS and tls_response[3].is_empty()
		if not tls_rejected: failures.append("invalid-tls")
		print(JSON.stringify({"path":"invalid-tls","passed":tls_rejected,"result":tls_response[0],"bytes":tls_response[3].size()}))
	client.close()
	print(JSON.stringify({"suite": "http-boundary", "ok": failures.is_empty(), "failures": failures}))
	quit(0 if failures.is_empty() else 1)
