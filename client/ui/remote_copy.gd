extends RefCounted

const P = preload("res://ui/palette.gd")
const ERROR_CATALOG = preload("res://data/server_error_catalog.json")

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

## Explicit translations and system template metadata are resolved before the
## legacy original/English fallback. Opaque authored text never enters aliases.
static func field(record: Dictionary, name: String) -> String:
	var original := str(record.get(name, "")).strip_edges()
	var translations: Variant = record.get("translations", {})
	if translations is Dictionary:
		var localized: Variant = translations.get(P.language(), {})
		if localized is Dictionary:
			var value := str(localized.get(name, "")).strip_edges()
			if not value.is_empty(): return value
	if name == "sender":
		var role := str(record.get("sender_role", record.get("senderRole", "")))
		if role == "system": return P.localized("system_sender")
		if role == "admin": return P.localized("admin_sender")
	if name in ["title", "body"]:
		var template_id := str(record.get("template_id", record.get("templateId", "")))
		if not template_id.is_empty():
			var key := "mail_" + template_id + "_" + name
			var template := P.localized(key)
			if template != key:
				var arguments: Variant = record.get("template_args", record.get("templateArgs", {}))
				if arguments is Array: arguments = _argument_dictionary(arguments)
				if arguments is Dictionary:
					var rendered := _render_template(template, arguments)
					if rendered.get("valid", false): return str(rendered.value)
	var system_aliases: Dictionary = P.LEGACY_DATA.data.get("system_content_aliases", {})
	if name == "sender" and original in system_aliases.get("sender", []): return P.localized("system_mail")
	if P.language() != "zh-CN":
		var translated := str(record.get(name + "En", record.get(name + "_en", ""))).strip_edges()
		if not translated.is_empty(): return translated
		if name == "title" and original in system_aliases.get("title", []): return P.localized("system_mail")
	return original

static func display_name(record: Dictionary, name: String, fallback_key: String = "traveler_default_name") -> String:
	var original: Variant = record.get(name, "")
	var value := "" if original == null else str(original)
	if bool(record.get(name + "_is_fallback", false)) or value.is_empty(): return P.localized(fallback_key)
	return value

static func http_error(problem: Dictionary, status: int) -> String:
	var catalog: Dictionary = ERROR_CATALOG.data
	var title := str(problem.get("title", "")).strip_edges()
	var key := str(catalog.get("http_titles", {}).get(title, ""))
	if key.is_empty(): key = str(catalog.get("http_statuses", {}).get(str(status), catalog.get("default_http", "server_unavailable")))
	return P.message(key, [])

static func command_error(payload: Dictionary) -> String:
	var catalog: Dictionary = ERROR_CATALOG.data
	var detail := str(payload.get("detail", ""))
	var key := str(catalog.get("command_details", {}).get(detail, ""))
	if key.is_empty(): key = str(catalog.get("command_codes", {}).get(str(payload.get("code", "")), catalog.get("default_command", "operation_rejected")))
	return P.message(key, [])

static func _argument_dictionary(entries: Array) -> Variant:
	var arguments := {}
	for entry in entries:
		if not entry is Dictionary: return null
		var key := str(entry.get("key", ""))
		if key.is_empty() or arguments.has(key) or not entry.get("value") is String: return null
		arguments[key] = entry.value
	return arguments

static func _render_template(template: String, arguments: Dictionary) -> Dictionary:
	var tokens := RegEx.new()
	tokens.compile("\\{([a-z_][a-z_0-9]*)\\}")
	var result := ""
	var cursor := 0
	# Read tokens only from the original template. Parameter text, especially an
	# administrator's reason, must not be reinterpreted as another placeholder.
	for token in tokens.search_all(template):
		var key := token.get_string(1)
		if not arguments.has(key): return {"valid": false}
		var value := str(arguments[key])
		if key == "kind": value = P.product_name(value)
		result += template.substr(cursor, token.get_start() - cursor) + value
		cursor = token.get_end()
	return {"valid": true, "value": result + template.substr(cursor)}
