extends Node

const P = preload("res://ui/palette.gd")
const LegacySettings = preload("res://ui/settings_panel.gd")
const HttpProtocol = preload("res://network/http_protocol.gd")
const Codec = preload("res://network/protobuf.gd")

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
	I18n.set_language("en")
	checks["legacy language selects current palette"] = P.language() == "en"
	checks["legacy UI text uses current title"] = I18n.t("幻境牌旅") == P.localized("game_title")
	checks["legacy translation remains available"] = I18n.t("确认退出登录？") == "Log out now?"
	P.set_language("zh-CN")
	checks["current language is visible to legacy components"] = I18n.locale == "zh" and I18n.t("设置") == "设置"
	for locale_code in ["zh", "en"]:
		I18n.set_language(locale_code)
		for width in [960, 1280, 1920]:
			get_tree().root.size = Vector2i(width, width * 9 / 16)
			var panel := LegacySettings.new()
			add_child(panel)
			var label := "%s/%d" % [locale_code, width]
			checks[label + " retained settings entry instantiates"] = panel.get_child_count() == 1
			panel.show_settings()
			await get_tree().process_frame
			await get_tree().process_frame
			var popup := panel.get_node("SettingsPopup") as PopupPanel
			var selector := popup.find_child("LanguageSelector", true, false) as OptionButton
			var logical_size := get_viewport().get_visible_rect().size
			checks[label + " retained settings fits viewport"] = popup.visible and selector.item_count == 2 and popup.position.x >= 0 and popup.position.y >= 0 and popup.position.x + popup.size.x <= logical_size.x and popup.position.y + popup.size.y <= logical_size.y
			popup.hide()
			panel.queue_free()
			await get_tree().process_frame
	if Game.has_method("login_google"):
		var google := HttpProtocol.route("/api/v1/auth/google", HTTPClient.METHOD_POST)
		checks["Google request has a typed route"] = google.get("request") == "GoogleSignInRequest" and google.get("response") == "LocalSignInResponse"
		var codec := Codec.new(true)
		var payload := codec.encode("GoogleSignInRequest", HttpProtocol.to_wire("GoogleSignInRequest", {"idToken": "owned-provider-fixture", "displayName": "Google traveller"}))
		checks["Google request encodes without fallback"] = not payload.is_empty() and codec.error.is_empty()
		var restored := codec.decode_http("GoogleSignInRequest", payload)
		checks["Google token and name survive binary mapping"] = restored.get("idToken") == "owned-provider-fixture" and restored.get("displayName") == "Google traveller"
		checks["legacy ticket uses the common response"] = HttpProtocol.route("/api/v1/auth/ws-ticket", HTTPClient.METHOD_POST).get("response") == "RealtimeTicketResponse"
		checks["deletion request uses a typed status"] = HttpProtocol.route("/api/v1/account-deletion", HTTPClient.METHOD_POST).get("response") == "AccountDeletionStatus"
		checks["deletion cancellation remains bodyless"] = HttpProtocol.route("/api/v1/account-deletion", HTTPClient.METHOD_DELETE).get("response") == "Empty"
		checks["Google account actions have English copy"] = I18n.t("申请删除账号") == "Request account deletion" and I18n.t("取消删除请求") == "Cancel deletion request"
	var result := {"ok": not checks.values().has(false), "checks": checks, "scope": "Headless native branch compatibility, no login or capacity workload"}
	var destination := OS.get_environment("FANTASYCARD_BRANCH_SYNC_RESULT")
	FileAccess.open(destination, FileAccess.WRITE).store_string(JSON.stringify(result))
	print(JSON.stringify(result))
	get_tree().quit(0 if result.ok else 1)
