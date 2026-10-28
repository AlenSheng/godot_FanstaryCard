extends Node

const Main = preload("res://ui/main.gd")
const P = preload("res://ui/palette.gd")
const Platform = preload("res://platform/platform_service.gd")
const HttpProtocol = preload("res://network/http_protocol.gd")

class SteamFixture extends Node:
	signal get_ticket_for_web_api(handle: int, result: int, size: int, buffer: PackedByteArray)
	var cancelled: Array = []
	var pending := false
	var result_code := 1
	var before_callback: Callable
	func steamInitEx(_app_id: int, _callbacks: bool) -> Dictionary: return {"status": 0}
	func getAppID() -> int: return 480
	func loggedOn() -> bool: return true
	func cancelAuthTicket(handle: int) -> void: cancelled.append(handle)
	func getAuthTicketForWebApi(_identity: String) -> int:
		pending = true
		return 7
	func run_callbacks() -> void:
		if not pending: return
		pending = false
		if before_callback.is_valid(): before_callback.call()
		get_ticket_for_web_api.emit(7, result_code, 2, PackedByteArray([1, 2]))

class PlatformFixture extends "res://platform/platform_service.gd":
	var api: Object
	func _steam_api() -> Object: return api

class GatewayFixture extends "res://network/gateway.gd":
	var requests: Array = []
	func request(path: String, method: int = HTTPClient.METHOD_GET, data: Variant = null, _quiet: Array = []) -> Dictionary:
		requests.append({"path": path, "method": method, "data": data, "origin": base_url})
		return {"ok": false, "data": null, "error": "Owned authentication rejection", "status": 401}

func _ready() -> void:
	Game.set_process(false)
	Game.gateway.end_session("", false)
	Game.gateway.set_process(false)
	Sound.set_process(false)
	Sound.set_music_context("")
	Sound.stop_all()
	Sound.stop_music()
	call_deferred("_run")

func _run() -> void:
	var checks := {}
	var original_gateway: Node = Game.gateway
	var original_platform: Node = Game.platform
	var original_info: Dictionary = Game.server_info.duplicate(true)
	var original_info_address: String = Game._server_info_address
	var configured_id: int = int(ProjectSettings.get_setting("platform/steam/app_id", 0))
	var configured_identity: String = str(ProjectSettings.get_setting("platform/steam/web_api_identity", ""))
	var configured_server: String = str(ProjectSettings.get_setting("platform/server_url", ""))
	var fixture_server := "https://owned-steam-fixture.invalid"
	checks["local login stays disabled on the Steam branch"] = not original_platform.local_login_enabled()
	var route := HttpProtocol.route("/api/v1/auth/steam", HTTPClient.METHOD_POST)
	checks["Steam sign-in uses the existing binary contract"] = route.get("request") == "SteamSignInRequest" and route.get("response") == "LocalSignInResponse"
	for language in ["zh-CN", "en"]:
		P.set_language(language)
		checks[language + " entry caption"] = I18n.t("进入") == ("Enter" if language == "en" else "进入")
	ProjectSettings.set_setting("platform/steam/app_id", 480)
	ProjectSettings.set_setting("platform/steam/web_api_identity", "owned-fixture")
	ProjectSettings.set_setting("platform/server_url", fixture_server)
	var api := SteamFixture.new()
	var adapter := PlatformFixture.new()
	adapter.api = api
	var gateway := GatewayFixture.new()
	gateway.persist_session = false
	add_child(api)
	add_child(adapter)
	add_child(gateway)
	gateway.set_process(false)
	Game.gateway = gateway
	Game.platform = adapter
	Game.server_info = {"capabilities": ["identity.steam"], "configVersion": str(Game.CATALOG.data.version)}
	Game._server_info_address = fixture_server
	Game.busy = false
	var entry := Main.new()
	await entry._enter_steam()
	checks["one entry action submits exactly one Steam request"] = gateway.requests.size() == 1
	if gateway.requests.size() == 1:
		var request: Dictionary = gateway.requests[0]
		checks["entry targets the configured cloud"] = request.origin == fixture_server and request.origin.begins_with("https://")
		checks["entry does not use local authentication"] = request.path == "/api/v1/auth/steam" and request.method == HTTPClient.METHOD_POST
		checks["only the callback ticket and game nickname are submitted"] = request.data.ticket == "0102" and request.data.has("displayName") and not request.data.has("steamId") and not request.data.has("deviceId")
		checks["automatic nickname is valid without an account field"] = str(request.data.displayName).length() >= 2 and str(request.data.displayName).length() <= 20
	checks["rejected cloud attempt cancels the Steam ticket"] = api.cancelled == [7] and adapter._ticket_handle == 0
	api.result_code = 2
	var failed: Dictionary = await adapter.request_login_ticket()
	checks["failed Steam callback cancels its handle"] = not failed.ok and adapter._ticket_handle == 0 and api.cancelled.size() == 2
	api.result_code = 1
	api.before_callback = func(): gateway.begin_sign_in(fixture_server)
	gateway.requests.clear()
	Game.busy = false
	await entry._enter_steam()
	checks["a replaced login context cannot submit a stale ticket"] = gateway.requests.is_empty() and adapter._ticket_handle == 0 and api.cancelled.size() == 3
	ProjectSettings.set_setting("platform/server_url", "http://127.0.0.1:1")
	Game.busy = false
	await entry._enter_steam()
	checks["Steam credentials are rejected before plain HTTP"] = gateway.requests.is_empty() and not Game.authentication_reason.is_empty() and api.cancelled.size() == 3
	entry.free()
	Game.busy = false
	Game.gateway = original_gateway
	Game.platform = original_platform
	Game.server_info = original_info
	Game._server_info_address = original_info_address
	ProjectSettings.set_setting("platform/steam/app_id", configured_id)
	ProjectSettings.set_setting("platform/steam/web_api_identity", configured_identity)
	ProjectSettings.set_setting("platform/server_url", configured_server)
	adapter.queue_free()
	api.queue_free()
	gateway.queue_free()
	await get_tree().process_frame
	var result := {"ok": not checks.values().has(false), "checks": checks, "scope": "Native adapter fixtures and actual entry/store methods; no Steam SDK or real provider login"}
	FileAccess.open(OS.get_environment("FANTASYCARD_STEAM_RESULT"), FileAccess.WRITE).store_string(JSON.stringify(result, "  "))
	print(JSON.stringify(result))
	get_tree().quit(0 if result.ok else 1)
