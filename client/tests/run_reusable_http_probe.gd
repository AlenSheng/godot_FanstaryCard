extends SceneTree

const ReusableHttpClient = preload("res://network/reusable_http_client.gd")

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var client := ReusableHttpClient.new()
	var origin := OS.get_environment("FANTASYCARD_SERVER_URL").strip_edges().trim_suffix("/")
	if origin.is_empty(): origin = "http://127.0.0.1:5080"
	for request_no in range(2):
		var started := Time.get_ticks_msec()
		var response: Array = await client.request(self, origin, "/health/ready",
			HTTPClient.METHOD_GET, PackedStringArray(), PackedByteArray())
		print("HTTP probe ", request_no, " result=", response[0], " status=", response[1],
			" reused=", response[4], " ms=", Time.get_ticks_msec() - started)
		if response[0] != HTTPRequest.RESULT_SUCCESS or response[1] != 200 or response[3].get_string_from_utf8() != "Healthy":
			quit(1)
			return
		if request_no == 1 and not response[4]:
			quit(1)
			return
	client.close()
	quit(0)
