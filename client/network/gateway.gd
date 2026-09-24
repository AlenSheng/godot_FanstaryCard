extends Node

signal failed(message: String)
signal event_received(kind: String, payload: Dictionary)
signal connection_changed(state: String)
signal authentication_required(reason: String)
signal telemetry(sample: Dictionary)

const Proto = preload("res://network/protobuf.gd")
const DEFAULT_LOCAL_BASE_URL := "http://127.0.0.1:5080"
const PRODUCTION_BASE_URL := "https://www.relicbound.cn"
const LEGACY_CLOUD_ORIGINS := ["http://43.172.70.182", "https://43.172.70.182"]
const COMMANDS := {
	"ping": "", "session.resume": "SessionResumeCommand", "room.ready": "RoomReadyCommand",
	"room.snapshot.read": "RoomSnapshotCommand", "room.move": "RoomMoveCommand",
	"battle.play_cards": "BattlePlayCardsCommand", "battle.select_target": "BattleSelectTargetCommand", "battle.abandon": "BattleAbandonCommand",
	"combat.preview": "BattlePlayCardsCommand",
	"reward.choice.refresh": "RewardChoiceRefreshCommand", "reward.choice.claim": "RewardChoiceClaimCommand",
	"duel.leave": "DuelLeaveCommand", "duel.escape": "DuelEscapeCommand",
	"action.extract": "ActionExtractCommand", "action.spring": "ActionSpringCommand",
	"action.potion": "ActionPotionCommand", "relic.take": "RelicTakeCommand", "relic.replace": "RelicReplaceCommand",
	"inventory.move": "InventoryMoveCommand", "inventory.equip": "InventoryEquipCommand", "inventory.unequip": "InventoryUnequipCommand",
	"relic.read": "RelicReadCommand"
}
const EVENTS := {
	"session.connected": "SessionConnectedEvent", "session.replaced": "SessionReplacedEvent",
	"session.snapshot": "SessionSnapshotEvent", "pong": "PongEvent", "match.found": "MatchFoundEvent",
	"room.ready_required": "RoomReadyRequiredEvent", "room.ready_accepted": "RoomReadyAcceptedEvent",
	"room.ready_removed": "RoomReadyRemovedEvent", "room.started": "RoomStartedEvent",
	"room.snapshot": "RoomSnapshotEvent", "room.moved": "RoomMovedEvent",
	"settlement.ready": "SettlementReadyEvent", "match.settled": "SettlementReadyEvent",
	"error.command_rejected": "CommandRejectedEvent", "battle.combo_resolved": "BattleComboResolvedEvent",
	"combat.previewed": "BattleComboResolvedEvent",
	"combat.hit": "BattleComboResolvedEvent",
	"battle.target_selected": "BattleTargetSelectedEvent", "reward.choice": "RewardChoiceEvent",
	"reward.choice.refreshed": "RewardChoiceEvent", "reward.choice.claimed": "RewardChoiceClaimedEvent",
	"reward.choice_claimed": "RewardChoiceClaimedEvent",
	"duel.started": "DuelStartedEvent", "duel.ended": "DuelEndedEvent", "duel.leave": "DuelLeaveEvent",
	"duel.escape_started": "DuelEscapeEvent", "duel.escape_failed": "DuelEscapeEvent",
	"duel.escape_interrupted": "DuelEscapeEvent", "player.died": "PlayerDiedEvent",
	"action.potion_used": "ActionPotionEvent", "relic.taken": "RelicTakeEvent", "relic.replaced": "RelicReplacedEvent",
	"inventory.changed": "InventoryChangedEvent", "relic.contents": "RoomRelicPile"
}

var base_url := DEFAULT_LOCAL_BASE_URL
var launch_base_url_override := ""
var persist_session := true
var token := ""
var token_expires_at: float = 0.0
var authenticated_user_id := ""
var local_account_name := ""
var session_generation: int = 0
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
var last_rtt_ms: int = -1
var _connecting_at: int = 0
var _pending_http: Dictionary = {}
var _pending_request_started: Dictionary = {}
var _pending_ping_request_id := ""
var _ping_sent_at: int = 0
var _command_cooldown: int = 0
var _connected_sequence: int = 0
var _last_snapshot_read: int = 0
var _preview_request_ids: Dictionary = {}
var _realtime_ticket_pending := false

func _ready() -> void:
	# A launcher may select a server for this run without changing the address
	# remembered in user://session.cfg. This keeps local development and cloud
	# smoke tests isolated from one another.
	launch_base_url_override = OS.get_environment("FANTASYCARD_SERVER_URL").strip_edges().trim_suffix("/")
	if not launch_base_url_override.is_empty():
		base_url = launch_base_url_override
	var config := ConfigFile.new()
	if config.load("user://session.cfg") == OK:
		device_id = config.get_value("session", "device_id", "")
		last_sequence = int(config.get_value("session", "sequence", 0))
		room_id = config.get_value("session", "room_id", "")
		room_revision = int(config.get_value("session", "revision", 0))
		var saved_base_url := str(config.get_value("session", "base_url", "")).strip_edges()
		if launch_base_url_override.is_empty() and not saved_base_url.is_empty(): base_url = saved_base_url
		authenticated_user_id = config.get_value("session", "user_id", "")
		local_account_name = config.get_value("session", "local_account_name", "")
	if base_url.trim_suffix("/") in LEGACY_CLOUD_ORIGINS:
		# Cloud hardening deliberately rejects direct origin-IP TLS requests.
		# Preserve existing players' sessions by moving their remembered address
		# to the public hostname before the readiness request is made.
		base_url = PRODUCTION_BASE_URL
	if not OS.is_debug_build():
		launch_base_url_override = ""
		base_url = str(ProjectSettings.get_setting("platform/server_url", "")).strip_edges()
	if device_id.is_empty(): device_id = "godot-" + new_id()
	_save_session()

func new_id() -> String:
	return Crypto.new().generate_random_bytes(16).hex_encode()

func _save_session() -> void:
	if not persist_session: return
	# Tokens stay in process memory; persisted names are only a login convenience.
	var config := ConfigFile.new()
	config.load("user://session.cfg")
	config.set_value("session", "device_id", device_id)
	config.set_value("session", "sequence", last_sequence)
	config.set_value("session", "room_id", room_id)
	config.set_value("session", "revision", room_revision)
	if launch_base_url_override.is_empty(): config.set_value("session", "base_url", base_url)
	config.set_value("session", "user_id", authenticated_user_id)
	config.set_value("session", "local_account_name", local_account_name)
	config.save("user://session.cfg")

func remember_local_account(server_name: String) -> void:
	local_account_name = server_name
	_save_session()

func begin_sign_in(address: String) -> void:
	end_session("", false)
	# A fresh credential must never resume terminal events (such as a prior ban)
	# from an earlier session, even when the player and server are unchanged.
	clear_replay()
	base_url = str(ProjectSettings.get_setting("platform/server_url", "")).strip_edges() if not OS.is_debug_build() else address
	_save_session()

func accept_session(access_token: String, expires_at: String, user_id: String) -> bool:
	if access_token.is_empty() or user_id.is_empty(): return false
	var expiry := parse_expiry(expires_at)
	if expiry <= Time.get_unix_time_from_system(): return false
	if authenticated_user_id != user_id: clear_replay()
	authenticated_user_id = user_id
	token = access_token
	token_expires_at = expiry
	_save_session()
	return true

static func parse_expiry(value: String) -> float:
	var normalized := value.strip_edges()
	if normalized.length() < 19: return 0.0
	var offset := 0
	var tail := normalized.substr(19)
	for sign_value in ["+", "-"]:
		var index := tail.find(sign_value)
		if index >= 0:
			var parts := tail.substr(index + 1).split(":")
			if parts.size() != 2 or not parts[0].is_valid_int() or not parts[1].is_valid_int(): return 0.0
			offset = (int(parts[0]) * 60 + int(parts[1])) * 60 * (1 if sign_value == "+" else -1)
	return float(Time.get_unix_time_from_datetime_string(normalized.substr(0, 19))) - offset

func clear_replay() -> void:
	last_sequence = 0
	room_id = ""
	room_revision = 0
	_connected_sequence = 0

func end_session(reason: String, notify: bool = true) -> void:
	session_generation += 1
	token = ""
	token_expires_at = 0.0
	reconnect_enabled = false
	online = false
	recovering = false
	_retry_at = 0
	_command_cooldown = 0
	_preview_request_ids = {}
	_pending_request_started = {}
	_pending_ping_request_id = ""
	_ping_sent_at = 0
	socket.close()
	if notify:
		connection_changed.emit(reason)
		authentication_required.emit(reason)

func session_expired() -> bool:
	return not token.is_empty() and token_expires_at > 0.0 and Time.get_unix_time_from_system() >= token_expires_at

func request(path: String, method: int = HTTPClient.METHOD_GET, data: Variant = null, quiet_statuses: Array = []) -> Dictionary:
	if session_expired():
		end_session("登录已过期，请重新登录")
		return {"ok": false, "status": 401, "error": "登录已过期，请重新登录"}
	var generation := session_generation
	data = normalize_request(data)
	var fingerprint := str(generation) + ":" + str(method) + path + JSON.stringify(data)
	if _pending_http.has(fingerprint):
		return {"ok": false, "status": 0, "error": "请求正在处理"}
	_pending_http[fingerprint] = true
	var request_started_at := Time.get_ticks_msec()
	var key := "godot-" + new_id()
	var headers := PackedStringArray(["Content-Type: application/json", "X-Trace-Id: " + key])
	if not token.is_empty(): headers.append("Authorization: Bearer " + token)
	if method != HTTPClient.METHOD_GET: headers.append("Idempotency-Key: " + key)
	var result: Dictionary = {}
	# One logical request retains exactly one key across transport and throttling retries.
	for attempt in range(3):
		if generation != session_generation: break
		var http := HTTPRequest.new()
		http.timeout = 30.0 if path.begins_with("/api/v1/auth/") else 10.0
		add_child(http)
		var start := http.request(base_url + path, headers, method, "" if data == null else JSON.stringify(data))
		if start != OK:
			http.queue_free()
			result = {"ok": false, "status": 0, "error": "无法连接服务器"}
		else:
			var response: Array = await http.request_completed
			http.queue_free()
			if generation != session_generation: break
			var code: int = response[1]
			var parser := JSON.new()
			var parse_status := parser.parse(response[3].get_string_from_utf8())
			var parsed: Variant = normalize_response(parser.data) if parse_status == OK else null
			var success: bool = response[0] == HTTPRequest.RESULT_SUCCESS and code >= 200 and code < 300
			var message := "服务器不可用，请检查地址与服务器状态"
			if parsed is Dictionary: message = str(parsed.get("detail", parsed.get("title", message)))
			result = {"ok": success, "status": code, "data": parsed, "error": message}
			if code == 401:
				end_session("Steam 登录票据无效，请重试" if path == "/api/v1/auth/steam" else "登录已过期，请重新登录")
			if success or code not in [0, 429, 502, 503, 504]: break
		if attempt < 2: await get_tree().create_timer(pow(2.0, attempt)).timeout
	_pending_http.erase(fingerprint)
	telemetry.emit({"type": "http", "path": path, "method": method, "duration_ms": Time.get_ticks_msec() - request_started_at, "status": result.get("status", 0), "ok": result.get("ok", false)})
	if generation != session_generation:
		return {"ok": false, "status": 401, "error": "登录状态已改变，请重新登录", "stale_session": true}
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
	if _realtime_ticket_pending: return
	if session_expired(): end_session("登录已过期，请重新登录")
	if token.is_empty(): return
	reconnect_enabled = true
	online = false
	_realtime_ticket_pending = true
	var generation := session_generation
	var ticket_result: Dictionary = await request("/api/v1/auth/ws-ticket", HTTPClient.METHOD_POST, {})
	_realtime_ticket_pending = false
	if generation != session_generation or not reconnect_enabled: return
	if not ticket_result.ok or ticket_result.data is not Dictionary:
		_schedule_reconnect()
		return
	var realtime_ticket := str(ticket_result.data.get("ticket", ""))
	if realtime_ticket.is_empty():
		_schedule_reconnect()
		return
	socket = WebSocketPeer.new()
	socket.inbound_buffer_size = 65536
	socket.outbound_buffer_size = 32768
	var url := base_url.replace("https://", "wss://").replace("http://", "ws://")
	var result := socket.connect_to_url(url + "/ws/v1/session?ws_ticket=" + realtime_ticket.uri_encode())
	_connecting_at = Time.get_ticks_msec()
	connection_changed.emit("正在连接实时服务")
	if result != OK: _schedule_reconnect()

func _schedule_reconnect() -> void:
	online = false
	_retry_at = Time.get_ticks_msec() + int(_backoff * 1000)
	_backoff = minf(_backoff * 2.0, 30.0)
	connection_changed.emit("连接中断，正在重连")

func _process(_delta: float) -> void:
	if session_expired(): end_session("登录已过期，请重新登录")
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
			if not reconnect_enabled: return
		if online and Time.get_ticks_msec() - _last_ping > 10000:
			var ping_request_id := new_id()
			if send("ping", {}, ping_request_id): _last_ping = Time.get_ticks_msec()
	elif state == WebSocketPeer.STATE_CLOSED:
		if _retry_at == 0: _schedule_reconnect()
		if Time.get_ticks_msec() >= _retry_at:
			_retry_at = 0
			connect_realtime()
	elif state == WebSocketPeer.STATE_CONNECTING and Time.get_ticks_msec() - _connecting_at > 10000:
		socket.close()
		_schedule_reconnect()

func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
	if session_expired():
		end_session("登录已过期，请重新登录")
		return false
	if not COMMANDS.has(kind) or socket.get_ready_state() != WebSocketPeer.STATE_OPEN: return false
	if Time.get_ticks_msec() < _command_cooldown: return false
	if recovering and kind not in ["ping", "session.resume", "room.snapshot.read"]: return false
	var proto := Proto.new()
	var effective_request_id := new_id() if request_id.is_empty() else request_id
	var envelope := {"protocol_version": 1, "type": kind, "request_id": effective_request_id}
	if not COMMANDS[kind].is_empty(): envelope.payload = proto.encode(COMMANDS[kind], payload)
	if kind not in ["ping", "session.resume", "room.snapshot.read", "room.ready", "relic.read"]:
		envelope.expected_revision = room_revision
	var sent := socket.put_packet(proto.encode("ClientEnvelope", envelope)) == OK
	if sent and kind == "combat.preview":
		_preview_request_ids[envelope.request_id] = true
		if _preview_request_ids.size() > 32: _preview_request_ids.erase(_preview_request_ids.keys()[0])
	if sent:
		_pending_request_started[effective_request_id] = {"action": kind, "started_at": Time.get_ticks_msec()}
		if _pending_request_started.size() > 128: _pending_request_started.erase(_pending_request_started.keys()[0])
		if kind == "ping":
			_pending_ping_request_id = effective_request_id
			_ping_sent_at = Time.get_ticks_msec()
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
	# Keep presentation silent for every replay packet, including after a snapshot
	# or the final replay advances the recovery cursor.
	payload["_replayed"] = recovering or (sequence > 0 and sequence < _connected_sequence)
	payload["_sequence"] = sequence
	payload["_request_id"] = envelope.get("request_id", "")
	payload["_event_revision"] = envelope.get("room_revision", -1)
	var response_request_id := str(envelope.get("request_id", ""))
	if _pending_request_started.has(response_request_id):
		var started: Dictionary = _pending_request_started[response_request_id]
		_pending_request_started.erase(response_request_id)
		var duration_ms := Time.get_ticks_msec() - int(started.get("started_at", Time.get_ticks_msec()))
		telemetry.emit({"type": "realtime", "action": started.get("action", kind), "response_type": kind, "duration_ms": duration_ms, "request_id": response_request_id, "replayed": recovering})
	if kind == "pong" and response_request_id == _pending_ping_request_id:
		last_rtt_ms = Time.get_ticks_msec() - _ping_sent_at
		_pending_ping_request_id = ""
		telemetry.emit({"type": "rtt", "duration_ms": last_rtt_ms})
	if kind in ["combat.previewed", "error.command_rejected"]:
		payload["_request_id"] = envelope.get("request_id", "")
		payload["_room_revision"] = envelope.get("room_revision", -1)
	if kind == "combat.previewed": _preview_request_ids.erase(envelope.get("request_id", ""))
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
		end_session(str(payload.get("reason", "账号已在其他窗口连接，请在此窗口重新登录后继续")))
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
		if _preview_request_ids.has(payload.get("_request_id", "")):
			_preview_request_ids.erase(payload._request_id)
			event_received.emit("combat.preview_rejected", payload)
			return
		event_received.emit(kind, payload)
		if payload.get("_retry_handled", false): return
		failed.emit(payload.get("detail", "操作被拒绝"))
		if payload.get("code", "") == "NOT_IN_ROOM":
			room_id = ""
			recovering = false
		elif not room_id.is_empty(): send("room.snapshot.read")
		return
	event_received.emit(kind, payload)
