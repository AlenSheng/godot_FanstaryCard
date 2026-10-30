extends RefCounted

const P = preload("res://ui/palette.gd")
const RemoteCopy = preload("res://ui/remote_copy.gd")
const SEEDS := ["seed_gold", "seed_souls", "seed_white_fire", "seed_green_water", "seed_blue_earth", "seed_purple_wood", "seed_orange_metal", "seed2_mixed_set", "seed2_fragments"]

func run_test() -> Dictionary:
	var saved_locale := P.language()
	var errors: Array = []
	var checked := 0
	for locale in P.languages():
		P.set_language(locale)
		for id in SEEDS:
			var seed := {"template_id": id, "template_args": [], "title": "legacy title", "body": "legacy body", "sender": "System", "sender_role": "system"}
			for field_name in ["title", "body"]:
				checked += 1
				if RemoteCopy.field(seed, field_name) != P.localized("mail_" + id + "_" + field_name): errors.append([locale, id, field_name])
			checked += 1
			if RemoteCopy.field(seed, "sender") != P.localized("system_sender"): errors.append([locale, id, "sender"])
		var reason := "  Fire / 装备 {amount} / {kind} / 100%\nraw reason  "
		var args := {"kind": "Gold", "amount": "7", "reason": reason}
		var item := {"template_id": "item_reclamation", "template_args": args, "title": "legacy title", "body": "legacy body", "sender_role": "admin", "sender": "Game Admin"}
		var expected := P.localized("mail_item_reclamation_body").replace("{kind}", P.product_name("Gold")).replace("{amount}", "7").replace("{reason}", reason)
		checked += 4
		if RemoteCopy.field(item, "body") != expected: errors.append([locale, "opaque_reason"])
		if not RemoteCopy.field(item, "body").ends_with(reason): errors.append([locale, "reason_whitespace"])
		if RemoteCopy.field(item, "title") != P.localized("mail_item_reclamation_title"): errors.append([locale, "reclamation_title"])
		if RemoteCopy.field(item, "sender") != P.localized("admin_sender"): errors.append([locale, "admin_role"])
		item.template_args = [{"key": "reason", "value": reason}, {"key": "amount", "value": "7"}, {"key": "kind", "value": "Gold"}]
		checked += 1
		if RemoteCopy.field(item, "body") != expected: errors.append([locale, "wire_argument_entries"])
		for invalid in [[{"key": "kind", "value": "Gold"}, {"key": "kind", "value": "7"}], [{"key": "kind", "value": 7}], {"kind": "Gold"}]:
			item.template_args = invalid
			checked += 1
			if RemoteCopy.field(item, "body") != "legacy body": errors.append([locale, "invalid_arguments_fallback", invalid])
		checked += 5
		if RemoteCopy.display_name({"owner_name": "旅人", "owner_name_is_fallback": true}, "owner_name") != P.localized("traveler_default_name"): errors.append([locale, "system_name"])
		if RemoteCopy.display_name({"owner_name": "旅人", "owner_name_is_fallback": false}, "owner_name") != "旅人": errors.append([locale, "real_same_name"])
		if RemoteCopy.display_name({"opponent_name": null}, "opponent_name") != P.localized("traveler_default_name"): errors.append([locale, "missing_name"])
		if RemoteCopy.field({"title": reason, "template_id": "unknown_template"}, "title") != reason.strip_edges(): errors.append([locale, "unknown_template_fallback"])
		item.translations = {locale: {"body": reason}}
		if RemoteCopy.field(item, "body") != reason.strip_edges(): errors.append([locale, "explicit_authored_translation"])
		var problem := {"title": "Invalid deck", "detail": "Opaque diagnostics: Fire / Gold / {amount}", "code": "http_400"}
		var original_problem := problem.duplicate(true)
		checked += 4
		if RemoteCopy.http_error(problem, 400) != P.localized("deck_invalid"): errors.append([locale, "http_fixed_title"])
		if problem != original_problem: errors.append([locale, "http_diagnostics_changed"])
		if RemoteCopy.http_error({"title": "Account banned", "detail": ""}, 403) != P.localized("ui_account_banned"): errors.append([locale, "empty_detail_ban"])
		if RemoteCopy.http_error({"title": "unknown", "detail": reason}, 503) != P.localized("server_unavailable"): errors.append([locale, "unknown_http_fallback"])
		var payload := {"code": "STALE_RELIC", "detail": reason}
		checked += 2
		if RemoteCopy.command_error(payload) != P.localized("relic_changed"): errors.append([locale, "rt_code"])
		if payload.detail != reason: errors.append([locale, "rt_diagnostics_changed"])
	P.set_language(saved_locale)
	return {"ok": errors.is_empty(), "checked": checked, "errors": errors}
