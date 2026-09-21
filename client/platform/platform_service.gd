extends Node

var _steam: Object
var _initialized := false
var _ticket_handle: int = 0
var _ticket_pending := false
var _ticket_result: Dictionary = {}
var _google: Object
var _google_pending := false
var _google_result: Dictionary = {}

func local_login_enabled() -> bool:
	return OS.is_debug_build() and bool(ProjectSettings.get_setting("platform/development/local_auth", true))

func google_login_unavailable_reason() -> String:
	if str(ProjectSettings.get_setting("platform/google/web_client_id", "")).strip_edges().is_empty():
		return "Google 登录尚未配置 Web Client ID"
	if not Engine.has_singleton("GoogleSignIn"):
		return "当前客户端未安装 Google 登录接入组件"
	_google = Engine.get_singleton("GoogleSignIn")
	if not _google.has_method("sign_in"):
		return "Google 登录接入组件版本不支持当前登录方式"
	if not _google.has_signal("sign_in_completed"):
		return "Google 登录接入组件缺少登录结果回调"
	return ""

func request_google_id_token() -> Dictionary:
	var unavailable := google_login_unavailable_reason()
	if not unavailable.is_empty(): return {"ok": false, "error": unavailable}
	if _google_pending: return {"ok": false, "error": "Google 登录正在处理"}
	_google_pending = true
	_google_result = {}
	if not _google.is_connected("sign_in_completed", _on_google_sign_in_completed):
		_google.connect("sign_in_completed", _on_google_sign_in_completed)
	var immediate: Variant = _google.call("sign_in", str(ProjectSettings.get_setting("platform/google/web_client_id", "")))
	if immediate is Dictionary and bool(immediate.get("ok", false)):
		_google_result = immediate.duplicate()
	var deadline := Time.get_ticks_msec() + 15000
	while _google_pending and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame
	_google_pending = false
	if _google_result.is_empty():
		return {"ok": false, "error": "Google 未能提供有效登录凭证，请重试"}
	var token := str(_google_result.get("id_token", _google_result.get("idToken", _google_result.get("token", ""))))
	if token.is_empty(): return {"ok": false, "error": "Google 未能提供有效登录凭证，请重试"}
	return {"ok": true, "id_token": token}

func _on_google_sign_in_completed(result: Variant = null, extra: Variant = null) -> void:
	if result is Dictionary:
		_google_result = result.duplicate()
	elif result is String:
		_google_result = {"id_token": result}
	elif extra is Dictionary:
		_google_result = extra.duplicate()
	_google_pending = false

func login_unavailable_reason() -> String:
	if int(ProjectSettings.get_setting("platform/steam/app_id", 0)) <= 0:
		return "Steam 登录尚未配置游戏 AppID"
	if str(ProjectSettings.get_setting("platform/steam/web_api_identity", "")).strip_edges().is_empty():
		return "Steam 登录尚未配置票据身份"
	if not Engine.has_singleton("Steam"):
		return "当前客户端未安装 Steam 接入组件"
	var steam := Engine.get_singleton("Steam")
	for method in ["steamInitEx", "getAuthTicketForWebApi", "cancelAuthTicket", "run_callbacks", "getAppID", "loggedOn"]:
		if not steam.has_method(method): return "Steam 接入组件版本不支持当前登录方式"
	if not steam.has_signal("get_ticket_for_web_api"):
		return "Steam 接入组件不支持网页登录票据回调"
	return ""

func request_login_ticket() -> Dictionary:
	var unavailable := login_unavailable_reason()
	if not unavailable.is_empty(): return {"ok": false, "error": unavailable}
	if _ticket_pending: return {"ok": false, "error": "Steam 登录正在处理"}
	_steam = Engine.get_singleton("Steam")
	if not _initialized:
		var init: Variant = _steam.call("steamInitEx", int(ProjectSettings.get_setting("platform/steam/app_id", 0)), false)
		if not init is Dictionary or int(init.get("status", -1)) != 0:
			return {"ok": false, "error": "无法连接 Steam，请启动 Steam 并从游戏库启动游戏"}
		_initialized = true
		_steam.connect("get_ticket_for_web_api", _on_web_api_ticket)
	if int(_steam.call("getAppID")) != int(ProjectSettings.get_setting("platform/steam/app_id", 0)):
		return {"ok": false, "error": "Steam 游戏身份与客户端配置不一致"}
	if not bool(_steam.call("loggedOn")):
		return {"ok": false, "error": "请先登录 Steam"}
	release_ticket()
	_ticket_pending = true
	_ticket_result = {}
	_ticket_handle = int(_steam.call("getAuthTicketForWebApi", str(ProjectSettings.get_setting("platform/steam/web_api_identity", ""))))
	if _ticket_handle == 0:
		_ticket_pending = false
		return {"ok": false, "error": "Steam 未能创建登录票据，请重试"}
	var deadline := Time.get_ticks_msec() + 15000
	while _ticket_pending and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame
	_ticket_pending = false
	if _ticket_result.is_empty():
		release_ticket()
		return {"ok": false, "error": "获取 Steam 登录票据超时，请重试"}
	return _ticket_result.duplicate()

func _process(_delta: float) -> void:
	if _initialized and is_instance_valid(_steam): _steam.call("run_callbacks")

func _on_web_api_ticket(handle: int, result: int, ticket_size: int, ticket_buffer: PackedByteArray) -> void:
	if not _ticket_pending or handle != _ticket_handle: return
	_ticket_pending = false
	if result != 1 or ticket_size <= 0 or ticket_size > 4096 or ticket_size > ticket_buffer.size():
		_ticket_result = {"ok": false, "error": "Steam 未能提供有效登录票据，请重试"}
		return
	_ticket_result = {"ok": true, "ticket": ticket_buffer.slice(0, ticket_size).hex_encode()}

func release_ticket() -> void:
	_ticket_pending = false
	_ticket_result = {}
	if _ticket_handle != 0 and is_instance_valid(_steam): _steam.call("cancelAuthTicket", _ticket_handle)
	_ticket_handle = 0

func _exit_tree() -> void:
	release_ticket()
