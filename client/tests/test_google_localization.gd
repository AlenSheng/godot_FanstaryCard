extends RefCounted

const P = preload("res://ui/palette.gd")
const AudioSettings = preload("res://ui/audio_settings.gd")
const KEYS := ["google_login", "account_deletion_request", "account_deletion_cancel", "account_deletion_confirmation", "account_deletion_requested", "account_deletion_cancelled", "google_disabled", "google_client_id_missing", "google_component_missing", "google_component_unsupported", "google_callback_missing", "google_login_processing", "google_token_invalid", "official_server_only"]

class GatewayFixture extends "res://network/gateway.gd":
	var requests: Array = []
	func request(path: String, method: int = HTTPClient.METHOD_GET, _data: Variant = null, _quiet: Array = []) -> Dictionary:
		requests.append({"path": path, "method": method})
		return {"ok": true, "data": {"status": "Pending"}, "error": ""}

func run_test() -> Dictionary:
	var checks := {}
	var tree := Engine.get_main_loop() as SceneTree
	var original_gateway: Node = Game.gateway
	var original_lobby: Dictionary = Game.lobby.duplicate(true)
	var original_busy: bool = Game.busy
	var original_language := P.language()
	var original_client_id: String = str(ProjectSettings.get_setting("platform/google/web_client_id", ""))
	var gateway := GatewayFixture.new()
	Game.gateway = gateway
	Game.busy = false
	Game.lobby = {"player": {"userId": "owned-localization-fixture"}}
	ProjectSettings.set_setting("platform/google/web_client_id", "")
	var notices: Array = []
	var on_notice := func(value): notices.append(value)
	Game.notice.connect(on_notice)
	var chinese: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/locales/zh-CN.json")).strings
	var english: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/locales/en.json")).strings
	for code in P.languages():
		I18n.set_language(code)
		var prefix := str(code) + ": "
		var pack: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/locales/%s.json" % code)).strings
		for key in KEYS:
			var translated := P.localized(key)
			checks[prefix + key + " authored"] = pack.has(key) and not str(pack[key]).is_empty() and translated != key
			checks[prefix + key + " legacy alias"] = I18n.t(chinese[key]) == translated
			checks[prefix + key + " display stays localized"] = P.localized_text(translated) == translated
			if code not in ["zh-CN", "en"]:
				checks[prefix + key + " no English fallback"] = str(pack[key]) != str(english[key])
			var missing := []
			for character in translated:
				var point := character.unicode_at(0)
				if point > 32 and not P.is_bidi_isolate(point) and (not P.font("body").has_char(point) or not P.font("title").has_char(point)):
					missing.append(point)
			checks[prefix + key + " complete fonts"] = missing.is_empty()
		checks[prefix + "cooling-off period stays seven days"] = P.without_bidi_isolates(P.localized("account_deletion_confirmation")).count("7") == 1
		checks[prefix + "actual unavailable provider reason"] = Game.platform.google_login_unavailable_reason() == P.localized("google_client_id_missing")
		var token_result: Dictionary = await Game.platform.request_google_id_token()
		checks[prefix + "actual unavailable provider request"] = not token_result.ok and token_result.error == P.localized("google_client_id_missing")
		var settings := AudioSettings.new()
		tree.root.add_child(settings)
		var request_count := gateway.requests.size()
		settings._show_account_deletion_confirmation()
		await tree.process_frame
		var dialog: Control = settings.get_node("AccountDeletionConfirmation")
		checks[prefix + "actual deletion dialog localized"] = dialog.get_node("DialogPanel/Title").text == P.localized("account_deletion_request") and dialog.get_node("DialogPanel/Description").text == P.localized("account_deletion_confirmation")
		checks[prefix + "opening dialog sends no deletion"] = gateway.requests.size() == request_count
		dialog.get_node("DialogPanel/CancelButton").pressed.emit()
		await tree.process_frame
		checks[prefix + "cancel preserves account"] = gateway.requests.size() == request_count and settings.get_node_or_null("AccountDeletionConfirmation") == null
		await Game.request_account_deletion()
		checks[prefix + "actual request notice localized"] = notices.back() == P.localized("account_deletion_requested") and gateway.requests.back() == {"path": "/api/v1/account-deletion", "method": HTTPClient.METHOD_POST}
		await Game.cancel_account_deletion()
		checks[prefix + "actual cancellation notice localized"] = notices.back() == P.localized("account_deletion_cancelled") and gateway.requests.back() == {"path": "/api/v1/account-deletion", "method": HTTPClient.METHOD_DELETE}
		settings.queue_free()
		await tree.process_frame
	Game.notice.disconnect(on_notice)
	Game.gateway = original_gateway
	Game.lobby = original_lobby
	Game.busy = original_busy
	ProjectSettings.set_setting("platform/google/web_client_id", original_client_id)
	P.set_language(original_language)
	gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks, "scope": "Eleven-locale authored copy, actual UI cancellation and owned gateway notices; no provider sign-in or account mutation"}
