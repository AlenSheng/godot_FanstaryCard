extends RefCounted

const P = preload("res://ui/palette.gd")

static func account_ban(reason: String) -> Dictionary:
	var prefixes: Array = [str(P.LEGACY_DATA.data.get("protocol_prefixes", {}).get("account_banned", ""))]
	for language_config in P.languages().values():
		prefixes.append(str(language_config.get("strings", {}).get("ui_account_banned", "")))
	for prefix in prefixes:
		if str(prefix).is_empty() or not reason.begins_with(str(prefix)): continue
		var detail := reason.trim_prefix(str(prefix)).strip_edges()
		for separator in P.LEGACY_DATA.data.get("protocol_separators", []):
			detail = detail.trim_prefix(str(separator)).strip_edges()
		return {"reason": detail}
	return {}

## Admin-authored text is stored in both languages. Legacy records have only
## title/body; keep those readable until an English version is published.
static func field(record: Dictionary, name: String) -> String:
	var original := str(record.get(name, "")).strip_edges()
	var translations: Variant = record.get("translations", {})
	if translations is Dictionary:
		var localized: Variant = translations.get(P.language(), {})
		if localized is Dictionary:
			var value := str(localized.get(name, "")).strip_edges()
			if not value.is_empty(): return value
	var system_aliases: Dictionary = P.LEGACY_DATA.data.get("system_content_aliases", {})
	if name == "sender" and original in system_aliases.get("sender", []): return P.localized("system_mail")
	if P.language() != "zh-CN":
		var translated := str(record.get(name + "En", record.get(name + "_en", ""))).strip_edges()
		if not translated.is_empty(): return translated
		if name == "title" and original in system_aliases.get("title", []): return P.localized("system_mail")
	return original
