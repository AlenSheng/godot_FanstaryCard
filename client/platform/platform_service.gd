extends Node

const P = preload("res://ui/palette.gd")

var _steam: Object
var _initialized := false
var _ticket_handle: int = 0
var _ticket_pending := false
var _ticket_result: Dictionary = {}

func local_login_enabled() -> bool:
	return OS.is_debug_build() and bool(ProjectSettings.get_setting("platform/development/local_auth", true))

func login_unavailable_reason() -> String:
	if int(ProjectSettings.get_setting("platform/steam/app_id", 0)) <= 0:
		return P.localized("steam_app_id_missing")
	if str(ProjectSettings.get_setting("platform/steam/web_api_identity", "")).strip_edges().is_empty():
		return P.localized("steam_identity_missing")
	if not Engine.has_singleton("Steam"):
		return P.localized("steam_component_missing")
	var steam := Engine.get_singleton("Steam")
	for method in ["steamInitEx", "getAuthTicketForWebApi", "cancelAuthTicket", "run_callbacks", "getAppID", "loggedOn"]:
		if not steam.has_method(method): return P.localized("steam_component_unsupported")
	if not steam.has_signal("get_ticket_for_web_api"):
		return P.localized("steam_browser_callback_unsupported")
	return ""

func request_login_ticket() -> Dictionary:
	var unavailable := login_unavailable_reason()
	if not unavailable.is_empty(): return {"ok": false, "error": unavailable}
	if _ticket_pending: return {"ok": false, "error": P.localized("steam_login_processing")}
	_steam = Engine.get_singleton("Steam")
	if not _initialized:
		var init: Variant = _steam.call("steamInitEx", int(ProjectSettings.get_setting("platform/steam/app_id", 0)), false)
		if not init is Dictionary or int(init.get("status", -1)) != 0:
			return {"ok": false, "error": P.localized("steam_connect_failed")}
		_initialized = true
		_steam.connect("get_ticket_for_web_api", _on_web_api_ticket)
	if int(_steam.call("getAppID")) != int(ProjectSettings.get_setting("platform/steam/app_id", 0)):
		return {"ok": false, "error": P.localized("steam_config_mismatch")}
	if not bool(_steam.call("loggedOn")):
		return {"ok": false, "error": P.localized("steam_login_required")}
	release_ticket()
	_ticket_pending = true
	_ticket_result = {}
	_ticket_handle = int(_steam.call("getAuthTicketForWebApi", str(ProjectSettings.get_setting("platform/steam/web_api_identity", ""))))
	if _ticket_handle == 0:
		_ticket_pending = false
		return {"ok": false, "error": P.localized("steam_ticket_create_failed")}
	var deadline := Time.get_ticks_msec() + 15000
	while _ticket_pending and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame
	_ticket_pending = false
	if _ticket_result.is_empty():
		release_ticket()
		return {"ok": false, "error": P.localized("steam_ticket_timeout")}
	return _ticket_result.duplicate()

func _process(_delta: float) -> void:
	if _initialized and is_instance_valid(_steam): _steam.call("run_callbacks")

func _on_web_api_ticket(handle: int, result: int, ticket_size: int, ticket_buffer: PackedByteArray) -> void:
	if not _ticket_pending or handle != _ticket_handle: return
	_ticket_pending = false
	if result != 1 or ticket_size <= 0 or ticket_size > 4096 or ticket_size > ticket_buffer.size():
		_ticket_result = {"ok": false, "error": P.localized("steam_ticket_empty")}
		return
	_ticket_result = {"ok": true, "ticket": ticket_buffer.slice(0, ticket_size).hex_encode()}

func release_ticket() -> void:
	_ticket_pending = false
	_ticket_result = {}
	if _ticket_handle != 0 and is_instance_valid(_steam): _steam.call("cancelAuthTicket", _ticket_handle)
	_ticket_handle = 0

func _exit_tree() -> void:
	release_ticket()
