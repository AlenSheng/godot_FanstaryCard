extends Node

var _steam: Object
var _initialized := false
var _ticket_handle: int = 0
var _ticket_pending := false
var _ticket_result: Dictionary = {}

func _steam_api() -> Object:
	return Engine.get_singleton("Steam") if Engine.has_singleton("Steam") else null

func local_login_enabled() -> bool:
	return OS.is_debug_build() and bool(ProjectSettings.get_setting("platform/development/local_auth", true))

func login_unavailable_reason() -> String:
	if int(ProjectSettings.get_setting("platform/steam/app_id", 0)) <= 0:
		return I18n.t("Steam 登录尚未配置游戏 AppID")
	if str(ProjectSettings.get_setting("platform/steam/web_api_identity", "")).strip_edges().is_empty():
		return I18n.t("Steam 登录尚未配置票据身份")
	var steam := _steam_api()
	if steam == null:
		return I18n.t("当前客户端未安装 Steam 接入组件")
	for method in ["steamInitEx", "getAuthTicketForWebApi", "cancelAuthTicket", "run_callbacks", "getAppID", "loggedOn", "getPersonaName"]:
		if not steam.has_method(method): return I18n.t("Steam 接入组件版本不支持当前登录方式")
	if not steam.has_signal("get_ticket_for_web_api"):
		return I18n.t("Steam 接入组件不支持网页登录票据回调")
	return ""

func request_login_ticket() -> Dictionary:
	var unavailable := login_unavailable_reason()
	if not unavailable.is_empty(): return {"ok": false, "error": unavailable}
	if _ticket_pending: return {"ok": false, "error": I18n.t("Steam 登录正在处理")}
	_steam = _steam_api()
	if not _initialized:
		var init: Variant = _steam.call("steamInitEx", int(ProjectSettings.get_setting("platform/steam/app_id", 0)), false)
		if not init is Dictionary or int(init.get("status", -1)) != 0:
			return {"ok": false, "error": I18n.t("无法连接 Steam，请启动 Steam 并从游戏库启动游戏")}
		_initialized = true
		_steam.connect("get_ticket_for_web_api", _on_web_api_ticket)
	if int(_steam.call("getAppID")) != int(ProjectSettings.get_setting("platform/steam/app_id", 0)):
		return {"ok": false, "error": I18n.t("Steam 游戏身份与客户端配置不一致")}
	if not bool(_steam.call("loggedOn")):
		return {"ok": false, "error": I18n.t("请先登录 Steam")}
	var persona_name := str(_steam.call("getPersonaName")).strip_edges()
	if persona_name.is_empty():
		return {"ok": false, "error": I18n.t("暂时无法读取 Steam 昵称，请稍后重试。")}
	release_ticket()
	_ticket_pending = true
	_ticket_result = {}
	_ticket_handle = int(_steam.call("getAuthTicketForWebApi", str(ProjectSettings.get_setting("platform/steam/web_api_identity", ""))))
	if _ticket_handle == 0:
		_ticket_pending = false
		return {"ok": false, "error": I18n.t("Steam 未能创建登录票据，请重试")}
	var deadline := Time.get_ticks_msec() + 15000
	while _ticket_pending and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame
	_ticket_pending = false
	if _ticket_result.is_empty():
		release_ticket()
		return {"ok": false, "error": I18n.t("获取 Steam 登录票据超时，请重试")}
	var result := _ticket_result.duplicate()
	if bool(result.get("ok", false)): result["display_name"] = persona_name
	else: release_ticket()
	return result

func _process(_delta: float) -> void:
	if _initialized and is_instance_valid(_steam): _steam.call("run_callbacks")

func _on_web_api_ticket(handle: int, result: int, ticket_size: int, ticket_buffer: PackedByteArray) -> void:
	if not _ticket_pending or handle != _ticket_handle: return
	_ticket_pending = false
	if result != 1 or ticket_size <= 0 or ticket_size > 4096 or ticket_size > ticket_buffer.size():
		_ticket_result = {"ok": false, "error": I18n.t("Steam 未能提供有效登录票据，请重试")}
		return
	_ticket_result = {"ok": true, "ticket": ticket_buffer.slice(0, ticket_size).hex_encode()}

func release_ticket() -> void:
	_ticket_pending = false
	_ticket_result = {}
	if _ticket_handle != 0 and is_instance_valid(_steam): _steam.call("cancelAuthTicket", _ticket_handle)
	_ticket_handle = 0

func _exit_tree() -> void:
	release_ticket()
