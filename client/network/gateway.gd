extends Node

signal failed(message: String)
signal event_received(kind: String, payload: Dictionary)
signal connection_changed(state: String)

const Proto = preload("res://network/protobuf.gd")
const COMMANDS := {
	"ping": "", "session.resume": "SessionResumeCommand", "room.ready": "RoomReadyCommand",
	"room.snapshot.read": "RoomSnapshotCommand", "room.move": "RoomMoveCommand",
	"battle.play_cards": "BattlePlayCardsCommand", "battle.select_target": "BattleSelectTargetCommand",
	"reward.choice.refresh": "RewardChoiceRefreshCommand", "reward.choice.claim": "RewardChoiceClaimCommand",
	"duel.leave": "DuelLeaveCommand", "duel.escape": "DuelEscapeCommand",
	"action.extract": "ActionExtractCommand", "action.spring": "ActionSpringCommand",
	"action.potion": "ActionPotionCommand", "relic.take": "RelicTakeCommand", "relic.replace": "RelicReplaceCommand"
}
const EVENTS := {
	"session.connected": "SessionConnectedEvent", "session.replaced": "SessionReplacedEvent",
	"session.snapshot": "SessionSnapshotEvent", "pong": "PongEvent", "match.found": "MatchFoundEvent",
	"room.ready_required": "RoomReadyRequiredEvent", "room.ready_accepted": "RoomReadyAcceptedEvent",
	"room.ready_removed": "RoomReadyRemovedEvent", "room.started": "RoomStartedEvent",
	"room.snapshot": "RoomSnapshotEvent", "room.moved": "RoomMovedEvent",
	"settlement.ready": "SettlementReadyEvent", "match.settled": "SettlementReadyEvent",
	"error.command_rejected": "CommandRejectedEvent", "battle.combo_resolved": "BattleComboResolvedEvent",
	"battle.target_selected": "BattleTargetSelectedEvent", "reward.choice": "RewardChoiceEvent",
	"reward.choice.refreshed": "RewardChoiceEvent", "reward.choice.claimed": "RewardChoiceClaimedEvent",
	"duel.started": "DuelStartedEvent", "duel.ended": "DuelEndedEvent", "duel.leave": "DuelLeaveEvent",
	"duel.escape_started": "DuelEscapeEvent", "duel.escape_failed": "DuelEscapeEvent",
	"duel.escape_interrupted": "DuelEscapeEvent", "player.died": "PlayerDiedEvent",
	"action.potion_used": "ActionPotionEvent", "relic.taken": "RelicTakeEvent", "relic.replaced": "RelicReplacedEvent"
}

var base_url := "http://127.0.0.1:5080"
var persist_session := true
var token := ""
var device_id := ""
var last_sequence: int = 0
var room_id := ""
var room_revision: int = 0
var socket := WebSocketPeer.new()
var online := false
var reconnect_enabled := false
var recovering := false
var _retry_at: int = 0
var _backoff: float = 1.0
var _last_ping: int = 0
var _connecting_at: int = 0
var _pending_http: Dictionary = {}
var _command_cooldown: int = 0
var _connected_sequence: int = 0
var _last_snapshot_read: int = 0

func _ready() -> void:
	var config := ConfigFile.new()
	if config.load("user://session.cfg") == OK:
		device_id = config.get_value("session", "device_id", "")
		last_sequence = int(config.get_value("session", "sequence", 0))
		room_id = config.get_value("session", "room_id", "")
		room_revision = int(config.get_value("session", "revision", 0))
		base_url = config.get_value("session", "base_url", base_url)
	if device_id.is_empty(): device_id = "godot-" + new_id()
	_save_session()

func new_id() -> String:
	return Crypto.new().generate_random_bytes(16).hex_encode()

func _save_session() -> void:
	if not persist_session: return
	# Tokens stay in process memory; only the development device identity is persisted.
	var config := ConfigFile.new()
	config.set_value("session", "device_id", device_id)
	config.set_value("session", "sequence", last_sequence)
	config.set_value("session", "room_id", room_id)
	config.set_value("session", "revision", room_revision)
	config.set_value("session", "base_url", base_url)
	config.save("user://session.cfg")

func request(path: String, method: int = HTTPClient.METHOD_GET, data: Variant = null, quiet_statuses: Array = []) -> Dictionary:
	data = normalize_request(data)
	var fingerprint := str(method) + path + JSON.stringify(data)
	if _pending_http.has(fingerprint):
		return {"ok": false, "status": 0, "error": "请求正在处理"}
	_pending_http[fingerprint] = true
	var key := "godot-" + new_id()
	var headers := PackedStringArray(["Content-Type: application/json", "X-Trace-Id: " + key])
	if not token.is_empty(): headers.append("Authorization: Bearer " + token)
	if method != HTTPClient.METHOD_GET: headers.append("Idempotency-Key: " + key)
	var result: Dictionary = {}
	# One logical request retains exactly one key across transport and throttling retries.
	for attempt in range(3):
		var http := HTTPRequest.new()
		http.timeout = 10.0
		add_child(http)
		var start := http.request(base_url + path, headers, method, "" if data == null else JSON.stringify(data))
		if start != OK:
			http.queue_free()
			result = {"ok": false, "status": 0, "error": "无法连接服务器"}
		else:
			var response: Array = await http.request_completed
			http.queue_free()
			var code: int = response[1]
			var parser := JSON.new()
			var parse_status := parser.parse(response[3].get_string_from_utf8())
			var parsed: Variant = normalize_response(parser.data) if parse_status == OK else null
			var success: bool = response[0] == HTTPRequest.RESULT_SUCCESS and code >= 200 and code < 300
			var message := "服务器不可用，请检查地址与服务器状态"
			if parsed is Dictionary: message = str(parsed.get("detail", parsed.get("title", message)))
			result = {"ok": success, "status": code, "data": parsed, "error": message}
			if code == 401:
				token = ""
				reconnect_enabled = false
				socket.close()
				connection_changed.emit("登录已过期")
			if success or code not in [0, 429, 502, 503, 504]: break
		if attempt < 2: await get_tree().create_timer(pow(2.0, attempt)).timeout
	_pending_http.erase(fingerprint)
	if not result.ok and result.status not in quiet_statuses: failed.emit(result.error)
	return result

static func normalize_request(data: Variant) -> Variant:
	if data is Dictionary:
		var result: Dictionary = data.duplicate(true)
		# Godot parses JSON numbers as floats; .NET rejects 1.0 for an Int64 DTO.
		for key in ["expectedVersion", "deckVersion", "quantity", "priceGold", "potionCount"]:
			if result.has(key): result[key] = int(result[key])
		return result
	return data

static func normalize_response(data: Variant) -> Variant:
	if data is Dictionary:
		var result: Dictionary = {}
		for key in data: result[key] = normalize_response(data[key])
		return result
	if data is Array:
		return data.map(func(value): return normalize_response(value))
	if data is float and is_finite(data) and data == floor(data) and abs(data) < 9007199254740992.0:
		return int(data)
	return data

func connect_realtime() -> void:
	if token.is_empty(): return
	reconnect_enabled = true
	online = false
	socket = WebSocketPeer.new()
	socket.inbound_buffer_size = 65536
	socket.outbound_buffer_size = 32768
	var url := base_url.replace("https://", "wss://").replace("http://", "ws://")
	var result := socket.connect_to_url(url + "/ws/v1/session?access_token=" + token.uri_encode())
	_connecting_at = Time.get_ticks_msec()
	connection_changed.emit("正在连接实时服务")
	if result != OK: _schedule_reconnect()

func _schedule_reconnect() -> void:
	online = false
	_retry_at = Time.get_ticks_msec() + int(_backoff * 1000)
	_backoff = minf(_backoff * 2.0, 30.0)
	connection_changed.emit("连接中断，正在重连")

func _process(_delta: float) -> void:
	if not reconnect_enabled: return
	socket.poll()
	var state := socket.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN:
		while socket.get_available_packet_count() > 0:
			var packet := socket.get_packet()
			if socket.was_string_packet():
				failed.emit("实时协议需要二进制帧")
				continue
			_receive(packet)
		if online and Time.get_ticks_msec() - _last_ping > 10000:
			send("ping")
			_last_ping = Time.get_ticks_msec()
		if online and not room_id.is_empty() and not recovering and Time.get_ticks_msec() - _last_snapshot_read >= 500:
			send("room.snapshot.read")
			_last_snapshot_read = Time.get_ticks_msec()
	elif state == WebSocketPeer.STATE_CLOSED:
		if _retry_at == 0: _schedule_reconnect()
		if Time.get_ticks_msec() >= _retry_at:
			_retry_at = 0
			connect_realtime()
	elif state == WebSocketPeer.STATE_CONNECTING and Time.get_ticks_msec() - _connecting_at > 10000:
		socket.close()
		_schedule_reconnect()

func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
	if not COMMANDS.has(kind) or socket.get_ready_state() != WebSocketPeer.STATE_OPEN: return false
	if Time.get_ticks_msec() < _command_cooldown: return false
	if recovering and kind not in ["ping", "session.resume", "room.snapshot.read"]: return false
	var proto := Proto.new()
	var envelope := {"protocol_version": 1, "type": kind, "request_id": new_id() if request_id.is_empty() else request_id}
	if not COMMANDS[kind].is_empty(): envelope.payload = proto.encode(COMMANDS[kind], payload)
	if kind not in ["ping", "session.resume", "room.snapshot.read", "room.ready"]:
		envelope.expected_revision = room_revision
	var sent := socket.put_packet(proto.encode("ClientEnvelope", envelope)) == OK
	if sent: socket.poll()
	return sent

func _receive(packet: PackedByteArray) -> void:
	var proto := Proto.new()
	var envelope := proto.decode("ServerEnvelope", packet)
	if not proto.error.is_empty() or envelope.get("protocol_version", 0) != 1:
		failed.emit("无法解析服务器协议")
		return
	var kind: String = envelope.get("type", "")
	var sequence: int = envelope.get("sequence", 0)
	var schema: String = EVENTS.get(kind, "")
	if kind.begins_with("action.extract_"): schema = "ActionExtractEvent"
	if kind.begins_with("action.spring_"): schema = "ActionSpringEvent"
	var payload := proto.decode(schema, envelope.get("payload", PackedByteArray())) if not schema.is_empty() else {}
	if not proto.error.is_empty():
		failed.emit("服务器消息内容损坏")
		return
	if kind == "session.connected":
		_connected_sequence = sequence
		online = true
		_backoff = 1.0
		_retry_at = 0
		recovering = last_sequence > 0 and last_sequence < sequence - 1
		connection_changed.emit("已连接")
		if recovering:
			send("session.resume", {"last_sequence": last_sequence, "room_id": room_id, "room_revision": room_revision})
		else: last_sequence = sequence
		return
	if kind == "session.replaced":
		reconnect_enabled = false
		online = false
		socket.close()
		connection_changed.emit("账号已在其他窗口连接")
		return
	if sequence <= last_sequence: return
	if sequence > last_sequence + 1 and kind not in ["session.snapshot", "room.snapshot"]:
		if not recovering:
			recovering = true
			send("session.resume", {"last_sequence": last_sequence, "room_id": room_id, "room_revision": room_revision})
		return
	if kind == "room.snapshot":
		room_id = payload.get("room_id", room_id)
		room_revision = int(payload.get("room_revision", room_revision))
		recovering = false
	elif envelope.has("room_revision"):
		room_revision = maxi(room_revision, int(envelope.room_revision))
	if kind == "session.snapshot":
		recovering = false
		if not room_id.is_empty(): send("room.snapshot.read")
	last_sequence = sequence
	if last_sequence == _connected_sequence - 1:
		last_sequence = _connected_sequence
		recovering = false
	_save_session()
	if kind == "error.rate_limited":
		_command_cooldown = Time.get_ticks_msec() + 2000
		failed.emit("操作过快，请稍后重试")
	if kind == "error.command_rejected":
		failed.emit(payload.get("detail", "操作被拒绝"))
		if payload.get("code", "") == "NOT_IN_ROOM":
			room_id = ""
			recovering = false
		elif not room_id.is_empty(): send("room.snapshot.read")
	event_received.emit(kind, payload)
