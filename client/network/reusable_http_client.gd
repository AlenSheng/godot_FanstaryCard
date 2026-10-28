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
	# Refresh an idle connection before reuse; a cached CONNECTED status can
	# outlive the peer's close. This check happens before submitting a write.
	if _client != null: _client.poll()
	var reused := _client != null and _origin == origin and _client.get_status() == HTTPClient.STATUS_CONNECTED
	if not reused:
		close()
		_client = HTTPClient.new()
		_origin = origin
		if _connect_origin(origin) != OK:
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
	var expected_bytes := _client.get_response_body_length()
	var chunked := _client.is_response_chunked()
	var response_headers := _client.get_response_headers()
	var response_body := PackedByteArray()
	while _client.get_status() == HTTPClient.STATUS_BODY:
		if Time.get_ticks_msec() >= deadline: return _failure(HTTPRequest.RESULT_TIMEOUT)
		# Drain buffered bytes before polling a peer close. A connection status
		# alone cannot prove that the response body was complete.
		var chunk := _client.read_response_body_chunk()
		if response_body.size() + chunk.size() > body_limit:
			return _failure(HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED)
		response_body.append_array(chunk)
		if _client.get_status() == HTTPClient.STATUS_BODY and _client.poll() != OK:
			return _failure(HTTPRequest.RESULT_CONNECTION_ERROR)
		await tree.process_frame
	var final_status := _client.get_status()
	var complete := (response_body.size() == expected_bytes if expected_bytes >= 0 and not chunked else
		final_status == HTTPClient.STATUS_CONNECTED if chunked else
		final_status in [HTTPClient.STATUS_CONNECTED, HTTPClient.STATUS_DISCONNECTED])
	if not complete: return _failure(HTTPRequest.RESULT_CHUNKED_BODY_SIZE_MISMATCH)
	# Framing proves the compressed wire body is complete. Decode only after
	# that check, with the same limit on the expanded body as HTTPRequest.
	var encoding := ""
	var connection_close := false
	for header in response_headers:
		var name := header.get_slice(":", 0).strip_edges().to_lower()
		var value := header.substr(header.find(":") + 1).strip_edges().to_lower()
		if name == "content-encoding": encoding = value
		elif name == "connection":
			for token in value.split(","):
				if token.strip_edges() == "close": connection_close = true
	if encoding not in ["", "identity"]:
		if encoding not in ["gzip", "deflate"]:
			return _failure(HTTPRequest.RESULT_BODY_DECOMPRESS_FAILED)
		if encoding == "gzip":
			if response_body.size() < 18 or response_body[0] != 0x1f or response_body[1] != 0x8b or response_body[2] != 8:
				return _failure(HTTPRequest.RESULT_BODY_DECOMPRESS_FAILED)
			if response_body.decode_u32(response_body.size() - 4) > body_limit:
				return _failure(HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED)
		var expanded := response_body.decompress_dynamic(body_limit, FileAccess.COMPRESSION_GZIP if encoding == "gzip" else FileAccess.COMPRESSION_DEFLATE)
		if expanded.is_empty() and not _is_complete_empty_compressed_body(response_body, encoding == "deflate"):
			return _failure(HTTPRequest.RESULT_BODY_DECOMPRESS_FAILED)
		response_body = expanded
	# The peer can advertise closure before its FIN reaches us.
	if connection_close or _client.get_status() != HTTPClient.STATUS_CONNECTED:
		close()
	busy = false
	return [HTTPRequest.RESULT_SUCCESS, code, response_headers, response_body, reused]

func _is_complete_empty_compressed_body(body: PackedByteArray, use_deflate: bool) -> bool:
	if body.is_empty(): return false
	var stream := StreamPeerGZIP.new()
	if stream.start_decompression(use_deflate) != OK: return false
	var accepted: Array = stream.put_partial_data(body)
	var complete := false
	if accepted[0] == OK and accepted[1] == body.size() and stream.get_available_bytes() == 0:
		# A finished inflater consumes no probe byte. A truncated stream must
		# consume it or fail, so an empty output alone cannot prove success.
		var boundary: Array = stream.put_partial_data(PackedByteArray([0]))
		complete = boundary[0] == OK and boundary[1] == 0 and stream.get_available_bytes() == 0
	stream.clear()
	return complete

func _failure(result: int) -> Array:
	close()
	busy = false
	return [result, 0, PackedStringArray(), PackedByteArray(), false]

func _connect_origin(origin: String) -> Error:
	# HTTPClient accepts a scheme prefix, but requires the port separately.
	# Passing "127.0.0.1:5000" as a hostname attempts a DNS lookup.
	var scheme := origin.get_slice("://", 0)
	if scheme not in ["http", "https"]: return ERR_INVALID_PARAMETER
	var authority := origin.get_slice("://", 1).get_slice("/", 0)
	var host := authority
	var port := 443 if scheme == "https" else 80
	if authority.begins_with("["):
		var end := authority.find("]")
		if end < 0: return ERR_INVALID_PARAMETER
		host = authority.substr(1, end - 1)
		if authority.length() > end + 1:
			if authority[end + 1] != ":" or not authority.substr(end + 2).is_valid_int(): return ERR_INVALID_PARAMETER
			port = int(authority.substr(end + 2))
	elif authority.contains(":"):
		host = authority.get_slice(":", 0)
		var value := authority.get_slice(":", 1)
		if not value.is_valid_int(): return ERR_INVALID_PARAMETER
		port = int(value)
	if host.is_empty() or port < 1 or port > 65535: return ERR_INVALID_PARAMETER
	return _client.connect_to_host(scheme + "://" + host, port)
