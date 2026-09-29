extends RefCounted

# One HTTP/1.1 connection per Gateway. A concurrent request can use the
# existing HTTPRequest path while this connection is busy.
var busy := false
var _origin := ""
var _client: HTTPClient

func close() -> void:
	if _client != null: _client.close()
	_client = null
	_origin = ""

func request(tree: SceneTree, origin: String, path: String, method: int,
		headers: PackedStringArray, body: PackedByteArray,
		timeout_ms: int = 10000, body_limit: int = 2 * 1024 * 1024) -> Array:
	busy = true
	var deadline := Time.get_ticks_msec() + timeout_ms
	var reused := _client != null and _origin == origin and _client.get_status() == HTTPClient.STATUS_CONNECTED
	if not reused:
		close()
		_client = HTTPClient.new()
		_origin = origin
		if _client.connect_to_host(origin) != OK:
			return _failure(HTTPRequest.RESULT_CANT_CONNECT)
	while _client.get_status() in [HTTPClient.STATUS_RESOLVING, HTTPClient.STATUS_CONNECTING]:
		if Time.get_ticks_msec() >= deadline: return _failure(HTTPRequest.RESULT_TIMEOUT)
		if _client.poll() != OK: return _failure(HTTPRequest.RESULT_CANT_CONNECT)
		await tree.process_frame
	if _client.get_status() != HTTPClient.STATUS_CONNECTED:
		return _failure(HTTPRequest.RESULT_CANT_CONNECT)
	var request_headers := headers.duplicate()
	if method != HTTPClient.METHOD_GET and method != HTTPClient.METHOD_HEAD:
		request_headers.append("Content-Length: " + str(body.size()))
	if _client.request_raw(method, path, request_headers, body) != OK:
		return _failure(HTTPRequest.RESULT_CONNECTION_ERROR)
	while _client.get_status() == HTTPClient.STATUS_REQUESTING:
		if Time.get_ticks_msec() >= deadline: return _failure(HTTPRequest.RESULT_TIMEOUT)
		if _client.poll() != OK: return _failure(HTTPRequest.RESULT_CONNECTION_ERROR)
		await tree.process_frame
	if _client.get_status() not in [HTTPClient.STATUS_BODY, HTTPClient.STATUS_CONNECTED] or not _client.has_response():
		return _failure(HTTPRequest.RESULT_CONNECTION_ERROR)
	var code := _client.get_response_code()
	var response_headers := _client.get_response_headers()
	var response_body := PackedByteArray()
	while _client.get_status() == HTTPClient.STATUS_BODY:
		if Time.get_ticks_msec() >= deadline: return _failure(HTTPRequest.RESULT_TIMEOUT)
		if _client.poll() != OK: return _failure(HTTPRequest.RESULT_CONNECTION_ERROR)
		var chunk := _client.read_response_body_chunk()
		if response_body.size() + chunk.size() > body_limit:
			return _failure(HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED)
		response_body.append_array(chunk)
		await tree.process_frame
	if _client.get_status() != HTTPClient.STATUS_CONNECTED:
		close()
	busy = false
	return [HTTPRequest.RESULT_SUCCESS, code, response_headers, response_body, reused]

func _failure(result: int) -> Array:
	close()
	busy = false
	return [result, 0, PackedStringArray(), PackedByteArray(), false]
