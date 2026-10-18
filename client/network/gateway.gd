extends Node

signal failed(message: String)
signal event_received(kind: String, payload: Dictionary)
signal connection_changed(state: String)
signal authentication_required(reason: String)
signal telemetry(sample: Dictionary)

const Proto = preload("res://network/protobuf.gd")
const HttpProtocol = preload("res://network/http_protocol.gd")
const ReusableHttpClient = preload("res://network/reusable_http_client.gd")
const HTTP_BACKGROUND_DECODE_BYTES := 8 * 1024
const PING_INTERVAL_MS := 10000
const PONG_TIMEOUT_MS := 20000
const DEFAULT_LOCAL_BASE_URL := "http://127.0.0.1:5080"
const PRODUCTION_BASE_URL := "https://www.relicbound.cn"
const LEGACY_CLOUD_ORIGINS := ["http://43.172.70.182", "https://43.172.70.182"]
const COMMANDS := {
	"ping": "", "session.resume": "SessionResumeCommand", "room.ready": "RoomReadyCommand",
	"room.snapshot.read": "RoomSnapshotCommand", "room.move": "RoomMoveCommand",
	"battle.play_cards": "BattlePlayCardsCommand", "battle.select_target": "BattleSelectTargetCommand", "battle.abandon": "BattleAbandonCommand",
	"combat.preview": "BattlePlayCardsCommand", "monster.choose": "MonsterCardChooseCommand",
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
	"room.command_cancelled": "RoomCommandCancelledEvent",
	"map.player_count": "MapPlayerCountEvent",
	"settlement.ready": "SettlementReadyEvent", "match.settled": "SettlementReadyEvent",
	"error.command_rejected": "CommandRejectedEvent", "battle.combo_resolved": "BattleComboResolvedEvent",
	"combat.previewed": "BattleComboResolvedEvent",
	"combat.hit": "BattleComboResolvedEvent",
	"battle.target_selected": "BattleTargetSelectedEvent", "reward.choice": "RewardChoiceEvent",
	"reward.choice.refreshed": "RewardChoiceEvent", "reward.choice.claimed": "RewardChoiceClaimedEvent",
	"reward.choice_claimed": "RewardChoiceClaimedEvent",
	"duel.started": "DuelStartedEvent", "duel.ended": "DuelEndedEvent", "duel.leave_ack": "DuelLeaveEvent",
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
var _ticket_generation: int = -1
var _pending_http: Dictionary = {}
var _http_origin_contexts: Dictionary = {}
var _http_read_epoch := 0
var telemetry_context: Dictionary = {}
var current_match_id := ""
var room_context_epoch := -1
var _prelaunch_ticket: Dictionary = {}
var _prelaunch_snapshot_attempts := 0
var _prelaunch_snapshot_at := 0
var _prelaunch_ready_accepted := false

func bind_prelaunch_ticket(match_id: String, known_room_id: String, deadline_unix_ms: int, epoch: int) -> void:
	# The caller has just read this account's Matched ticket. Match/room/deadline
	# come from its authenticated found notification; this never adopts a route.
	if not room_id.is_empty() or match_id.is_empty() or known_room_id.is_empty() or deadline_unix_ms <= int(Time.get_unix_time_from_system()*1000.0): return
	if room_context_epoch >= 0 and room_context_epoch != epoch: return
	room_context_epoch = epoch
	var identity := {"match_id":match_id,"room_id":known_room_id,"deadline_unix_ms":deadline_unix_ms,"session_generation":session_generation,"room_context_epoch":epoch}
	var same_scope := not _prelaunch_ticket.is_empty() and str(_prelaunch_ticket.match_id) == match_id and str(_prelaunch_ticket.room_id) == known_room_id and int(_prelaunch_ticket.session_generation) == session_generation and int(_prelaunch_ticket.room_context_epoch) == epoch
	if same_scope:
		identity.deadline_unix_ms = mini(int(_prelaunch_ticket.deadline_unix_ms), deadline_unix_ms)
	else:
		_prelaunch_snapshot_attempts = 0
		_prelaunch_snapshot_at = 0
		_prelaunch_ready_accepted = false
	_prelaunch_ticket = identity

func _prelaunch_valid() -> bool:
	return room_id.is_empty() and not _prelaunch_ticket.is_empty() and int(_prelaunch_ticket.session_generation)==session_generation and int(_prelaunch_ticket.room_context_epoch)==room_context_epoch and int(_prelaunch_ticket.deadline_unix_ms)>int(Time.get_unix_time_from_system()*1000.0)

func _expected_match_context() -> String:
	return str(_prelaunch_ticket.match_id) if _prelaunch_valid() else current_match_id

func _read_prelaunch_snapshot() -> void:
	if not _prelaunch_valid() or _prelaunch_snapshot_attempts >= 3 or Time.get_ticks_msec() < _prelaunch_snapshot_at: return
	_prelaunch_snapshot_attempts += 1
	_prelaunch_snapshot_at = Time.get_ticks_msec() + 1000
	# The wire command is empty: the server resolves this account's route.
	# The verified room identity stays in immutable local request context.
	send("room.snapshot.read")

func capture_context() -> Dictionary:
	var context := telemetry_context.duplicate(true)
	context.merge({"origin": base_url, "session_generation": session_generation,
		"room_id": room_id, "match_id": current_match_id}, true)
	if _prelaunch_valid():
		context["room_id"] = _prelaunch_ticket.room_id
		context["match_id"] = _prelaunch_ticket.match_id
	# Instrumentation replaces telemetry_context at each load phase. Room
	# identity belongs to the session and must survive those analytics updates.
	if room_context_epoch >= 0: context["room_context_epoch"] = room_context_epoch
	return context
var _reusable_http := ReusableHttpClient.new()
var use_reusable_http := true
var _pending_request_started: Dictionary = {}
var _response_contexts: Dictionary = {}
var _pending_ping_request_id := ""
var _ping_sent_at: int = 0
var _command_cooldown: int = 0
var _connected_sequence: int = 0
var _last_snapshot_read: int = 0
var _preview_request_ids: Dictionary = {}

func _ready() -> void:
	# A launcher may select a server for this run without changing the address
	# remembered in user://session.cfg. This keeps local development and cloud
	# smoke tests isolated from one another.
	launch_base_url_override = OS.get_environment("FANTASYCARD_SERVER_URL").strip_edges().trim_suffix("/")
	if not launch_base_url_override.is_empty():
		base_url = launch_base_url_override
	# Autoloads initialize before the load scene. Opt out before reading or writing
	# the shared user:// file, which otherwise lets workers inherit each other's
	# replay cursor and room identity.
	if not OS.get_environment("FANTASYCARD_LOAD_RUN_ID").is_empty():
		persist_session = false
		device_id = "load-" + new_id()
		# Game may refresh client-info before the load scene is ready. Capture
		# this process's declared owner before that first asynchronous request.
		var load_run := OS.get_environment("FANTASYCARD_LOAD_RUN_ID").strip_edges()
		var load_client := OS.get_environment("FANTASYCARD_LOAD_CLIENT_ID").strip_edges()
		var load_epoch := OS.get_environment("FANTASYCARD_LOAD_PROCESS_EPOCH").strip_edges()
		if not load_run.is_empty() and not load_client.is_empty() and not load_epoch.is_empty():
			telemetry_context = {"run_id": load_run, "client_id": load_client,
				"process_epoch": load_epoch, "cycle_id": load_client + ":1", "phase": "initial"}
		return
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
	if not OS.is_debug_build() and launch_base_url_override.is_empty(): base_url = str(ProjectSettings.get_setting("platform/server_url", "")).strip_edges()
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
	base_url = address
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
	current_match_id = ""
	room_context_epoch = -1
	_prelaunch_ticket = {}
	_prelaunch_snapshot_attempts = 0
	_prelaunch_ready_accepted = false
	token = ""
	token_expires_at = 0.0
	reconnect_enabled = false
	online = false
	recovering = false
	_retry_at = 0
	_command_cooldown = 0
	_preview_request_ids = {}
	_pending_request_started = {}
	_response_contexts = {}
	_pending_ping_request_id = ""
	_ping_sent_at = 0
	socket.close()
	if notify:
		connection_changed.emit(reason)
		authentication_required.emit(reason)

func session_expired() -> bool:
	return not token.is_empty() and token_expires_at > 0.0 and Time.get_unix_time_from_system() >= token_expires_at

func request(path: String, method: int = HTTPClient.METHOD_GET, data: Variant = null, quiet_statuses: Array = []) -> Dictionary:
	var generation := session_generation
	var result: Dictionary = await _request_page(path, method, data, quiet_statuses)
	if not result.ok or method != HTTPClient.METHOD_GET: return result
	var canonical := path.get_slice("?", 0).trim_suffix("/")
	var collections := []
	if canonical in ["/api/v1/market", "/api/v1/market/context", "/api/v1/bootstrap", "/api/v1/economy/context"]:
		collections.append({"header": "X-Market-Next-Offset", "path": "/api/v1/market", "key": "listings" if canonical == "/api/v1/market/context" else "market"})
	if canonical in ["/api/v1/mail", "/api/v1/bootstrap"]:
		collections.append({"header": "X-Mail-Next-Offset", "path": "/api/v1/mail", "key": "mail"})
	var aggregate_bytes: int = result.get("body_bytes", 0)
	for collection in collections:
		var cursor := HttpProtocol.header(result.get("headers", PackedStringArray()), collection.header)
		var previous := -1
		var pages := 0
		while not cursor.is_empty():
			if generation != session_generation: return {"ok": false, "status": 401, "error": "登录状态已改变，请重新登录", "stale_session": true}
			if not cursor.is_valid_int() or int(cursor) <= previous or pages >= 32:
				return _pagination_error("服务器分页游标无效", quiet_statuses)
			previous = int(cursor)
			pages += 1
			var page: Dictionary = await _request_page(collection.path + "?offset=" + cursor + "&limit=200", method, null, quiet_statuses)
			if not page.ok: return page
			if generation != session_generation: return {"ok": false, "status": 401, "error": "登录状态已改变，请重新登录", "stale_session": true}
			aggregate_bytes += int(page.get("body_bytes", 0))
			var target: Variant
			var incoming: Variant
			if collection.path == "/api/v1/mail":
				var mailbox: Variant = result.data if canonical == collection.path else result.data.get(collection.key)
				target = mailbox.get("items") if mailbox is Dictionary else null
				incoming = page.data.get("items") if page.data is Dictionary else null
			else:
				target = result.data if canonical == collection.path else result.data.get(collection.key)
				incoming = page.data
			if not target is Array or not incoming is Array:
				return _pagination_error("服务器分页内容无效", quiet_statuses)
			if target.size() + incoming.size() > 4096 or aggregate_bytes > 16 * 1024 * 1024:
				return _pagination_error("列表超过客户端读取上限，请缩小查询范围", quiet_statuses)
			target.append_array(incoming)
			cursor = HttpProtocol.header(page.get("headers", PackedStringArray()), collection.header)
	return result

func _pagination_error(message: String, quiet_statuses: Array) -> Dictionary:
	if 0 not in quiet_statuses: failed.emit(message)
	return {"ok": false, "status": 0, "error": message}

func _decode_http_response(contract: Dictionary, status: int, headers: PackedStringArray, body: PackedByteArray) -> Dictionary:
	var started := Time.get_ticks_usec()
	var decoded: Dictionary
	var background := body.size() > HTTP_BACKGROUND_DECODE_BYTES
	if background:
		# The task sees immutable protocol metadata and bytes only. It never calls
		# SceneTree/Node/UI APIs. Read the result only after completion and join.
		var completed: Array = []
		var task := WorkerThreadPool.add_task(func():
			completed.append(HttpProtocol.decode_response(contract, status, headers, body)))
		while not WorkerThreadPool.is_task_completed(task):
			await get_tree().process_frame
		WorkerThreadPool.wait_for_task_completion(task)
		decoded = completed[0] if not completed.is_empty() else {"ok": false, "data": null, "error": "服务器响应解码失败"}
	else:
		decoded = HttpProtocol.decode_response(contract, status, headers, body)
	decoded["decode_ms"] = float(Time.get_ticks_usec() - started) / 1000.0
	decoded["decode_worker"] = background
	return decoded

func _request_page(path: String, method: int = HTTPClient.METHOD_GET, data: Variant = null, quiet_statuses: Array = []) -> Dictionary:
	if session_expired():
		end_session("登录已过期，请重新登录")
		return {"ok": false, "status": 401, "error": "登录已过期，请重新登录"}
	var contract := HttpProtocol.route(path, method)
	var perimeter := HttpProtocol.is_perimeter(path, method)
	if contract.is_empty() and not perimeter:
		return {"ok": false, "status": 0, "error": "未注册的网络接口"}
	var generation := session_generation
	var body := PackedByteArray()
	if not perimeter:
		if data != null and not data is Dictionary:
			return {"ok": false, "status": 0, "error": "请求数据类型错误"}
		var proto := Proto.new(true)
		body = proto.encode(contract.request, HttpProtocol.to_wire(contract.request, data if data is Dictionary else {}))
		if not proto.error.is_empty(): return {"ok": false, "status": 0, "error": "请求编码失败: " + proto.error}
	# Binary identity preserves all 64 integer bits and is never logged.
	if method != HTTPClient.METHOD_GET: _http_read_epoch += 1
	var fingerprint := str(generation) + ":" + base_url + ":" + (str(_http_read_epoch) if method == HTTPClient.METHOD_GET else "write") + ":" + str(method) + path + ("" if body.is_empty() else Marshalls.raw_to_base64(body))
	if _pending_http.has(fingerprint):
		if method != HTTPClient.METHOD_GET:
			return {"ok": false, "status": 0, "error": "请求正在处理"}
		var existing: Dictionary = _pending_http[fingerprint]
		while not existing.done and generation == session_generation:
			await get_tree().process_frame
		if generation != session_generation: return {"ok": false, "status": 401, "stale_session": true, "error": "登录状态已改变"}
		return existing.result.duplicate(true)
	var flight := {"done": false, "result": {}}
	_pending_http[fingerprint] = flight
	var request_started_at := Time.get_ticks_msec()
	var request_deadline := request_started_at + 30000
	var key := "godot-" + new_id()
	var origin_context := capture_context()
	_http_origin_contexts[key] = origin_context
	var media := "application/json" if perimeter else "application/protobuf"
	var headers := PackedStringArray(["Content-Type: " + media, "Accept: " + media, "X-Trace-Id: " + key])
	if not perimeter and not token.is_empty(): headers.append("Authorization: Bearer " + token)
	if method != HTTPClient.METHOD_GET: headers.append("Idempotency-Key: " + key)
	var result: Dictionary = {"ok": false, "status": 0, "error": "无法连接服务器"}
	# One logical request retains exactly one key across transport and throttling retries.
	var attempt_count := 0
	var retry_backoff_ms := 0.0
	for attempt in range(3):
		if generation != session_generation or Time.get_ticks_msec() >= request_deadline: break
		attempt_count = attempt + 1
		var attempt_started_at := Time.get_ticks_msec()
		var delay := pow(2.0, attempt)
		var response: Array = await _request_http_transport(path, method, headers, body, mini(10000, maxi(1, request_deadline - Time.get_ticks_msec())))
		if response[0] != HTTPRequest.RESULT_SUCCESS and int(response[1]) == 0:
			result = {"ok": false, "status": 0, "error": "无法连接服务器"}
			var terminal_transport_failure: bool = response[0] in [HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED, HTTPRequest.RESULT_BODY_DECOMPRESS_FAILED]
			_emit_http_attempt(path, method, key, generation, attempt_count, attempt_started_at, 0,
				"timeout" if response[0] == HTTPRequest.RESULT_TIMEOUT else "transport_error",
				0, 0.0, delay * 1000.0 if attempt < 2 and not terminal_transport_failure else 0.0)
			if terminal_transport_failure: break
		else:
			if generation != session_generation:
				_emit_http_attempt(path, method, key, generation, attempt_count, attempt_started_at, int(response[1]), "cancelled", response[3].size(), 0.0, 0.0, response.size() > 4 and response[4])
				break
			var code: int = response[1]
			var decoded: Dictionary
			if perimeter:
				var parser := JSON.new()
				var parse_status := parser.parse(response[3].get_string_from_utf8())
				decoded = {"ok": parse_status == OK, "data": normalize_response(parser.data) if parse_status == OK else null, "error": "服务器响应无效"}
			else: decoded = await _decode_http_response(contract, code, response[2], response[3])
			if generation != session_generation:
				_emit_http_attempt(path, method, key, generation, attempt_count, attempt_started_at, code, "cancelled", response[3].size(), decoded.get("decode_ms", 0.0), 0.0, response.size() > 4 and response[4])
				break
			var parsed: Variant = decoded.data
			var success: bool = response[0] == HTTPRequest.RESULT_SUCCESS and code >= 200 and code < 300 and decoded.ok
			var message := "服务器不可用，请检查地址与服务器状态"
			if not decoded.ok: message = decoded.error
			elif parsed is Dictionary: message = str(parsed.get("detail", parsed.get("title", message)))
			result = {"ok": success, "status": code, "data": parsed, "error": message, "headers": response[2], "body_bytes": response[3].size(), "decode_ms": decoded.get("decode_ms", 0.0), "decode_worker": decoded.get("decode_worker", false)}
			var may_retry: bool = not success and code in [0, 429, 502, 503, 504] and attempt < 2
			# A received invalid protobuf/JSON body is a terminal decode failure.
			if code != 0 and not decoded.ok: may_retry = false
			if response[0] in [HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED, HTTPRequest.RESULT_BODY_DECOMPRESS_FAILED]: may_retry = false
			if may_retry:
				var retry_after := HttpProtocol.header(response[2], "Retry-After")
				if retry_after.is_valid_int(): delay = maxf(delay, float(retry_after))
				elif parsed is Dictionary and parsed.get("retryAfterSeconds") != null: delay = maxf(delay, float(parsed.retryAfterSeconds))
				if delay > 60.0: may_retry = false
			var attempt_result := "success" if success else ("decode_error" if not decoded.ok else ("timeout" if response[0] == HTTPRequest.RESULT_TIMEOUT else ("transport_error" if response[0] != HTTPRequest.RESULT_SUCCESS else "http_error")))
			_emit_http_attempt(path, method, key, generation, attempt_count, attempt_started_at, code, attempt_result, response[3].size(), decoded.get("decode_ms", 0.0), delay * 1000.0 if may_retry else 0.0, response.size() > 4 and response[4])
			if code == 401:
				end_session("Steam 登录票据无效，请重试" if path == "/api/v1/auth/steam" else "登录已过期，请重新登录")
			if not may_retry: break
		if attempt < 2:
			retry_backoff_ms += delay * 1000.0
			# Jitter only adds to the server's minimum wait. The total logical
			# deadline and session cancellation also bound Retry-After.
			var wake_at := Time.get_ticks_msec() + int(delay * 1000.0) + randi_range(0, 200)
			while Time.get_ticks_msec() < mini(wake_at, request_deadline) and generation == session_generation:
				await get_tree().process_frame
	_pending_http.erase(fingerprint)
	var terminal := {"type": "http", "path": path, "route": str(contract.get("path", path.get_slice("?", 0))),
		"method": method, "logical_request_id": key, "trace_id": key, "attempt_no": attempt_count,
		"session_generation": generation, "duration_ms": Time.get_ticks_msec() - request_started_at,
		"status": result.get("status", 0), "ok": result.get("ok", false),
		"result": "cancelled" if generation != session_generation else ("success" if result.get("ok", false) else "error"),
		"body_bytes": result.get("body_bytes", 0), "decode_ms": result.get("decode_ms", 0.0),
		"retry_backoff_ms": retry_backoff_ms}
	terminal.merge(origin_context, false)
	telemetry.emit(terminal)
	_http_origin_contexts.erase(key)
	if generation != session_generation:
		result = {"ok": false, "status": 401, "error": "登录状态已改变，请重新登录", "stale_session": true}
	flight.result = result.duplicate(true)
	flight.done = true
	if generation != session_generation: return result
	if not result.ok and result.status not in quiet_statuses: failed.emit(result.error)
	return result

func _request_http_transport(path: String, method: int, headers: PackedStringArray,
		body: PackedByteArray, timeout_ms: int = 10000) -> Array:
	if use_reusable_http and not OS.has_feature("web") and not _reusable_http.busy:
		return await _reusable_http.request(get_tree(), base_url, path, method, headers, body, timeout_ms)
	if not OS.has_feature("web"):
		# Native one-off/concurrent requests must handle empty 204 replies too.
		# Keep them independent of the shared connection and close on completion.
		var one_off := ReusableHttpClient.new()
		var response: Array = await one_off.request(get_tree(), base_url, path, method, headers, body, timeout_ms)
		one_off.close()
		return response
	var http := HTTPRequest.new()
	http.timeout = float(timeout_ms) / 1000.0
	http.body_size_limit = 2 * 1024 * 1024
	add_child(http)
	var start := http.request_raw(base_url + path, headers, method, body)
	if start != OK:
		http.queue_free()
		return [HTTPRequest.RESULT_CANT_CONNECT, 0, PackedStringArray(), PackedByteArray(), false]
	var response: Array = await http.request_completed
	http.queue_free()
	return response

func _emit_http_attempt(path: String, method: int, request_id: String, generation: int,
		attempt_no: int, started_at: int, status: int, outcome: String, body_bytes: int,
		decode_ms: float, retry_backoff_ms: float, connection_reused: bool = false) -> void:
	var contract := HttpProtocol.route(path, method)
	var sample := {"type": "http_attempt", "route": str(contract.get("path", path.get_slice("?", 0))),
		"method": method, "logical_request_id": request_id, "trace_id": request_id,
		"attempt_no": attempt_no, "session_generation": generation,
		"duration_ms": Time.get_ticks_msec() - started_at, "status": status,
		"result": outcome, "ok": outcome == "success", "body_bytes": body_bytes,
		"decode_ms": decode_ms, "retry_backoff_ms": retry_backoff_ms,
		"connection_reused": connection_reused}
	sample.merge(_http_origin_contexts.get(request_id, {}), false)
	telemetry.emit(sample)

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
	if session_expired(): end_session("登录已过期，请重新登录")
	if token.is_empty() or _ticket_generation == session_generation: return
	var generation := session_generation
	reconnect_enabled = true
	online = false
	_ticket_generation = generation
	connection_changed.emit("正在连接实时服务")
	var response: Dictionary = await request("/api/v1/realtime/ticket", HTTPClient.METHOD_POST, {}, [0, 429, 502, 503, 504])
	if _ticket_generation == generation: _ticket_generation = -1
	if generation != session_generation or not reconnect_enabled: return
	if not response.ok or not response.get("data") is Dictionary:
		_schedule_reconnect()
		return
	var ticket: String = str(response.data.get("ticket", ""))
	if ticket.is_empty() or parse_expiry(str(response.data.get("expiresAt", ""))) <= Time.get_unix_time_from_system():
		_schedule_reconnect()
		return
	socket = WebSocketPeer.new()
	_connected_sequence = 0
	socket.inbound_buffer_size = 65536
	socket.outbound_buffer_size = 32768
	var url := base_url.replace("https://", "wss://").replace("http://", "ws://")
	var result := socket.connect_to_url(url + "/ws/v1/session?ticket=" + ticket.uri_encode())
	_connecting_at = Time.get_ticks_msec()
	if result != OK: _schedule_reconnect()

func _schedule_reconnect() -> void:
	online = false
	if not _pending_ping_request_id.is_empty(): _pending_request_started.erase(_pending_ping_request_id)
	_pending_ping_request_id = ""
	# A half-open close handshake may never finish. Retire this peer before
	# scheduling the next authenticated connection, keeping logical context.
	socket.close()
	socket = WebSocketPeer.new()
	_connected_sequence = 0
	_retry_at = Time.get_ticks_msec() + int(_backoff * 1000)
	_backoff = minf(_backoff * 2.0, 30.0)
	connection_changed.emit("连接中断，正在重连")

func _process(_delta: float) -> void:
	if session_expired(): end_session("登录已过期，请重新登录")
	if not reconnect_enabled or _ticket_generation == session_generation: return
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
		if online and not _pending_ping_request_id.is_empty() and Time.get_ticks_msec() - _ping_sent_at >= PONG_TIMEOUT_MS:
			var timeout_sample: Dictionary = {"type":"realtime_timeout","action":"ping","request_id":_pending_ping_request_id,
				"duration_ms":Time.get_ticks_msec()-_ping_sent_at,"reason":"pong_deadline"}
			timeout_sample.merge(capture_context(),false)
			telemetry.emit(timeout_sample)
			_schedule_reconnect()
			return
		if online and _pending_ping_request_id.is_empty() and Time.get_ticks_msec() - _last_ping > PING_INTERVAL_MS:
			var ping_request_id := new_id()
			if send("ping", {}, ping_request_id): _last_ping = Time.get_ticks_msec()
		if online and _prelaunch_ready_accepted: _read_prelaunch_snapshot()
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
	# READY has no route fields on wire; only a current verified, unexpired
	# prelaunch ticket can authorize sending it, including outside recovery.
	if kind == "room.ready" and not _prelaunch_valid(): return false
	if Time.get_ticks_msec() < _command_cooldown: return false
	if recovering and kind not in ["ping", "session.resume", "room.snapshot.read"]:
		if kind != "room.ready" or not _prelaunch_valid(): return false
	var proto := Proto.new()
	var effective_request_id := new_id() if request_id.is_empty() else request_id
	var envelope := {"protocol_version": 1, "type": kind, "request_id": effective_request_id}
	var origin := capture_context()
	if kind not in ["ping", "session.resume", "room.ready"] and not str(origin.get("room_id", "")).is_empty() and not str(origin.get("match_id", "")).is_empty():
		envelope["room_id"] = origin.room_id
		envelope["match_id"] = origin.match_id
	if not COMMANDS[kind].is_empty():
		envelope.payload = proto.encode(COMMANDS[kind], payload)
		if not proto.error.is_empty(): return false
	if kind not in ["ping", "session.resume", "room.snapshot.read", "room.ready", "relic.read"]:
		envelope.expected_revision = room_revision
	var encoded := proto.encode("ClientEnvelope", envelope)
	if not proto.error.is_empty(): return false
	var sent := socket.put_packet(encoded) == OK
	if sent and kind == "combat.preview":
		_preview_request_ids[envelope.request_id] = true
		if _preview_request_ids.size() > 32: _preview_request_ids.erase(_preview_request_ids.keys()[0])
	if sent:
		_pending_request_started[effective_request_id] = {"action": kind, "started_at": Time.get_ticks_msec(), "context": origin}
		if _pending_request_started.size() > 128: _pending_request_started.erase(_pending_request_started.keys()[0])
		if kind not in ["ping", "session.resume", "room.snapshot.read", "combat.preview", "relic.read"]:
			var dispatched := {"type":"command_lifecycle", "event_type":"command.sent", "action":kind, "request_id":effective_request_id, "result":"sent", "trace_only":true}
			dispatched.merge(origin, false)
			telemetry.emit(dispatched)
		if kind == "ping":
			_pending_ping_request_id = effective_request_id
			_ping_sent_at = Time.get_ticks_msec()
	if sent and kind == "room.ready":
		var wire_hash := HashingContext.new()
		wire_hash.start(HashingContext.HASH_SHA256)
		wire_hash.update(encoded)
		var observation := {"type":"protocol_observation", "event_type":"room.ready.sent", "trace_only":true,
			"request_id":effective_request_id, "payload_bytes":envelope.get("payload", PackedByteArray()).size(),
			"payload_fields":payload.size(), "has_room_id":envelope.has("room_id"), "has_match_id":envelope.has("match_id"),
			"wire_sha256":wire_hash.finish().hex_encode()}
		observation.merge(origin, false)
		telemetry.emit(observation)
	if sent: socket.poll()
	return sent

func _capture_receive_owner() -> Dictionary:
	# Physical receive ownership is known independently of an originating
	# request. Never infer a business cycle or phase for unsolicited frames.
	var current := capture_context()
	var received := {}
	for key in ["run_id", "client_id", "process_epoch"]:
		if current.has(key): received[key] = current[key]
	return received

func _ready_rejection_has_joined_context(payload: Dictionary) -> bool:
	# A READY can be in flight when its verified lobby becomes the joined room.
	# Require that exact one-step transition; keep the wire result rejected.
	if payload.get("code", "") != "READY_NOT_FOUND" or payload.get("_command_action", "") != "room.ready" or payload.get("_command_result", "") != "rejected": return false
	if str(payload.get("_request_id", "")).is_empty() or payload.get("_replayed", true): return false
	var origin_value: Variant = payload.get("_origin_context")
	if not origin_value is Dictionary: return false
	var origin: Dictionary = origin_value
	if typeof(origin.get("session_generation")) != TYPE_INT or typeof(origin.get("room_context_epoch")) != TYPE_INT: return false
	if int(origin.session_generation) != session_generation or int(origin.room_context_epoch) < 0 or room_context_epoch != int(origin.room_context_epoch) + 1: return false
	if current_match_id.is_empty() or room_id.is_empty(): return false
	if typeof(origin.get("match_id")) != TYPE_STRING or typeof(origin.get("room_id")) != TYPE_STRING: return false
	if origin.match_id != current_match_id or origin.room_id != room_id: return false
	for key in ["run_id", "client_id", "process_epoch", "cycle_id"]:
		if origin.has(key) != telemetry_context.has(key): return false
		if origin.has(key):
			if typeof(origin[key]) != TYPE_STRING or str(origin[key]).is_empty() or origin[key] == "Unknown" or origin[key] != telemetry_context[key]: return false
	return true

func _emit_lifecycle_guard(observation: Dictionary, payload: Dictionary, receive_owner: Dictionary) -> void:
	var correlated := payload.has("_origin_context")
	var origin_value: Variant = payload.get("_origin_context", {})
	var origin: Dictionary = origin_value if origin_value is Dictionary else {}
	observation.merge(origin if correlated else receive_owner, false)
	observation["context_capture_kind"] = "request" if correlated else "uncorrelated_receive"
	observation["record_owner_source"] = "dispatch" if correlated else "gateway_receive"
	telemetry.emit(observation)

func _receive(packet: PackedByteArray) -> void:
	var receive_owner := _capture_receive_owner()
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
	for request_id in _response_contexts.keys():
		if Time.get_ticks_msec() >= int(_response_contexts[request_id].expires_at): _response_contexts.erase(request_id)
	if _pending_request_started.has(response_request_id):
		var started: Dictionary = _pending_request_started[response_request_id]
		payload["_origin_context"] = started.get("context", {}).duplicate(true)
		_pending_request_started.erase(response_request_id)
		# An ACK/cancellation and its authoritative snapshot share a request ID.
		# Retain the immutable origin for every frame, but measure the request once.
		_response_contexts[response_request_id] = {"context": started.get("context", {}).duplicate(true), "action": started.get("action", ""), "result": "cancelled" if kind == "room.command_cancelled" else "rejected" if kind == "error.command_rejected" else "completed", "expires_at": Time.get_ticks_msec() + 120000}
		if _response_contexts.size() > 128: _response_contexts.erase(_response_contexts.keys()[0])
		var duration_ms := Time.get_ticks_msec() - int(started.get("started_at", Time.get_ticks_msec()))
		payload["_command_action"] = started.get("action", "")
		payload["_command_result"] = _response_contexts[response_request_id].result
		var sample := {"type": "realtime", "action": started.get("action", kind), "response_type": kind, "duration_ms": duration_ms, "request_id": response_request_id, "replayed": recovering,
			"result": "cancelled" if kind == "room.command_cancelled" else "rejected" if kind == "error.command_rejected" else "completed"}
		sample.merge(started.get("context", {}), false)
		telemetry.emit(sample)
	elif _response_contexts.has(response_request_id):
		payload["_origin_context"] = _response_contexts[response_request_id].context.duplicate(true)
		payload["_command_action"] = _response_contexts[response_request_id].action
		payload["_command_result"] = _response_contexts[response_request_id].result
	if kind == "pong" and not _pending_ping_request_id.is_empty() and response_request_id == _pending_ping_request_id:
		last_rtt_ms = Time.get_ticks_msec() - _ping_sent_at
		_pending_ping_request_id = ""
		var rtt_sample := {"type": "rtt", "duration_ms": last_rtt_ms, "request_id": response_request_id}
		rtt_sample.merge(payload.get("_origin_context", {}), false)
		telemetry.emit(rtt_sample)
	if kind in ["combat.previewed", "error.command_rejected"]:
		payload["_request_id"] = envelope.get("request_id", "")
		payload["_room_revision"] = envelope.get("room_revision", -1)
	if kind == "combat.previewed": _preview_request_ids.erase(envelope.get("request_id", ""))
	if kind == "session.connected":
		# Replay includes connection markers; only the first marker on this peer
		# may start recovery. New peers reset the marker even if the stream restarts.
		if sequence <= _connected_sequence: return
		_connected_sequence = sequence
		online = true
		_backoff = 1.0
		_retry_at = 0
		_last_ping = Time.get_ticks_msec()
		recovering = last_sequence > 0 and last_sequence < sequence - 1
		connection_changed.emit("已连接")
		if recovering:
			send("session.resume", {"last_sequence": last_sequence, "room_id": room_id, "room_revision": room_revision})
		else:
			# The event stream can expire while the client is closed. Its new
			# sequence is authoritative even when the cached cursor was higher.
			last_sequence = sequence
		# Bootstrap may report a room without the socket pushing a snapshot
		# (for example while the old room is being settled).
		if not room_id.is_empty(): send("room.snapshot.read")
		_save_session()
		return
	if kind == "session.replaced":
		end_session(str(payload.get("reason", "账号已在其他窗口连接，请在此窗口重新登录后继续")))
		return
	if sequence <= last_sequence:
		if kind in ["match.found", "room.ready_required", "room.ready_accepted", "room.started"]:
			_emit_lifecycle_guard({"type":"lifecycle_guard", "event_type":kind, "decision":"Ignored", "trace_only":true,
				"reason":"stale_or_duplicate_sequence", "sequence":sequence, "last_sequence":last_sequence}, payload, receive_owner)
		return
	if kind == "room.ready_accepted" and _prelaunch_valid() and str(payload.get("match_id", "")) == str(_prelaunch_ticket.match_id) and str(payload.get("room_id", "")) == str(_prelaunch_ticket.room_id):
		_prelaunch_ready_accepted = true
		# Allow the coordinator's next iteration to register the room. A
		# transient NOT_IN_ROOM cannot revoke this prelaunch ticket context.
		_prelaunch_snapshot_at = maxi(_prelaunch_snapshot_at, Time.get_ticks_msec() + 250)
	if sequence > last_sequence + 1 and kind not in ["session.snapshot", "room.snapshot"]:
		if not recovering:
			recovering = true
			send("session.resume", {"last_sequence": last_sequence, "room_id": room_id, "room_revision": room_revision})
		# If an earlier required frame can never be delivered, a real future
		# started packet is only a hint to read authority. Its payload/cursor
		# is not applied. The independently verified ticket must match it.
		if kind == "room.started" and _prelaunch_valid() and str(payload.get("match_id", "")) == str(_prelaunch_ticket.match_id) and str(payload.get("room_id", "")) == str(_prelaunch_ticket.room_id):
			_read_prelaunch_snapshot()
		return
	var prior_room_callback := false
	if kind == "room.started" and not room_id.is_empty() and not current_match_id.is_empty():
		prior_room_callback = str(payload.get("match_id", "")) != current_match_id
	elif kind == "room.started" and _prelaunch_valid():
		prior_room_callback = str(payload.get("match_id", "")) != str(_prelaunch_ticket.match_id)
	elif kind == "room.snapshot":
		var expected := capture_context()
		if not str(expected.match_id).is_empty():
			prior_room_callback = str(payload.get("match_id", "")) != str(expected.match_id) or str(payload.get("room_id", "")) != str(expected.room_id)
		if payload.has("_origin_context"):
			var origin: Dictionary = payload._origin_context
			prior_room_callback = prior_room_callback or (int(origin.get("session_generation", -1)) != session_generation
				or str(origin.get("match_id", "")) != str(expected.match_id)
				or str(origin.get("room_id", "")) != str(expected.room_id)
				or (room_context_epoch >= 0 and int(origin.get("room_context_epoch", -1)) != room_context_epoch))
		elif not response_request_id.is_empty():
			# Expired/unrecognized request responses need a fresh scoped read.
			prior_room_callback = true
	if prior_room_callback:
		var expected_context := capture_context()
		_emit_lifecycle_guard({"type":"lifecycle_guard", "event_type":kind, "decision":"Ignored", "trace_only":true,
			"reason":"prior_room_context", "sequence":sequence, "last_sequence":last_sequence,
			"expected_match_id":expected_context.get("match_id", ""), "expected_room_id":expected_context.get("room_id", ""),
			"received_match_id":payload.get("match_id", ""), "received_room_id":payload.get("room_id", "")}, payload, receive_owner)
		# Consume the session cursor, but an old room callback cannot replace
		# the current route/revision or release its snapshot recovery lock.
		last_sequence = sequence
		_save_session()
		return
	if kind == "room.snapshot":
		if _prelaunch_valid() and str(payload.get("match_id", "")) != str(_prelaunch_ticket.match_id): return
		room_id = payload.get("room_id", room_id)
		current_match_id = str(payload.get("match_id", current_match_id))
		room_revision = int(payload.get("room_revision", room_revision))
		recovering = false
		_prelaunch_ticket = {}
	elif kind == "room.started":
		current_match_id = str(payload.get("match_id", payload.get("snapshot", {}).get("match_id", current_match_id)))
		# A sequence-gap resume can finish before the room route is registered.
		# Its READY replay then has no room snapshot to release recovery. Once
		# the real start arrives, request authority through the allowed read path.
		if recovering and not str(payload.get("room_id", "")).is_empty():
			room_id = str(payload.room_id)
			send("room.snapshot.read")
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
		if _ready_rejection_has_joined_context(payload):
			_emit_lifecycle_guard({"type":"protocol_observation", "event_type":"room.ready.rejection_resolved", "decision":"Resolved", "trace_only":true,
				"reason":"already_entered_same_room", "code":payload.code, "detail":payload.get("detail", ""), "response_type":kind, "result":"rejected",
				"request_id":response_request_id, "sequence":sequence, "verified_room_context_epoch":room_context_epoch,
				"verified_match_id":current_match_id, "verified_room_id":room_id}, payload, receive_owner)
			# Diagnostics never enter business-event confirmation consumers.
			return
		if payload.get("code", "") == "NOT_IN_ROOM":
			var origin: Dictionary = payload.get("_origin_context", {})
			# An uncorrelated or prior-cycle rejection cannot revoke the current
			# route. Require the context recorded when this command was sent.
			if origin.is_empty() or str(origin.get("match_id", "")).is_empty() or str(origin.get("match_id", "")) != current_match_id: return
			if int(origin.get("session_generation", -1)) != session_generation: return
			if str(origin.get("room_id", "")).is_empty() or (not room_id.is_empty() and str(origin.get("room_id", "")) != room_id): return
			if room_context_epoch >= 0 and int(origin.get("room_context_epoch", -1)) != room_context_epoch: return
			room_id = ""
			room_revision = 0
			recovering = false
			_save_session()
		event_received.emit(kind, payload)
		if payload.get("_retry_handled", false): return
		failed.emit(payload.get("detail", "操作被拒绝"))
		if not room_id.is_empty(): send("room.snapshot.read")
		return
	if not payload.has("_origin_context") and kind in ["match.found", "room.ready_required", "room.ready_accepted", "room.started", "room.moved", "battle.combo_resolved", "settlement.ready", "match.settled", "player.died", "action.extract_completed"]:
		payload["_receive_owner_context"] = receive_owner.duplicate(true)
	event_received.emit(kind, payload)
