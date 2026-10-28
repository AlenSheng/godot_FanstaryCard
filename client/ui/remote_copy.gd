extends RefCounted

const P = preload("res://ui/palette.gd")

## Admin-authored text is stored in both languages. Legacy records have only
## title/body; keep those readable until an English version is published.
static func field(record: Dictionary, name: String) -> String:
	var original := str(record.get(name, "")).strip_edges()
	if P.language() == "en":
		var translated := str(record.get(name + "En", record.get(name + "_en", ""))).strip_edges()
		if not translated.is_empty(): return translated
		if name == "title" and original == "系统通知": return P.localized("system_mail")
	return original
