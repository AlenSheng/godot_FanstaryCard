extends Node

signal language_changed(locale: String)

const P = preload("res://ui/palette.gd")
const CARD_TEXT = preload("res://data/card_descriptions.json")
const UI_TEXT = preload("res://data/ui_text.json")
static var locale: String:
	get:
		return "zh" if P.language() == "zh-CN" else P.language()
	set(value):
		P.set_language("zh-CN" if value == "zh" else value)
static var _ui: Dictionary = UI_TEXT.data.get("locales", {})

func _ready() -> void:
	var configured: Dictionary = UI_TEXT.data.get("locales", {})
	if not configured.is_empty(): _ui = configured
	var config := ConfigFile.new()
	if not FileAccess.file_exists(P.LANGUAGE_SETTINGS_PATH) and config.load("user://settings.cfg") == OK:
		locale = str(config.get_value("display", "locale", "zh"))

static func t(value: String) -> String:
	if value.is_empty(): return value
	var translation_key := P.key_for_text(value)
	if translation_key.is_empty(): translation_key = str(P.LEGACY_DATA.data.inline_aliases.get(value, ""))
	if not translation_key.is_empty(): return P.localized(translation_key)
	if _ui.get(locale, {}).has(value): return _ui[locale][value]
	var current := P.localized_text(value)
	if current != value: return current
	if locale == "en":
		var keys: Array = _ui["zh"].keys()
		keys.sort_custom(func(a, b): return str(a).length() > str(b).length())
		for key in keys:
			var source := str(key)
			if not source.is_empty() and value.contains(source): value = value.replace(source, str(_ui["en"].get(source, source)))
	return value

static func card_text(key: String) -> String:
	var table: Dictionary = CARD_TEXT.data.get(locale, CARD_TEXT.data.get("zh", {}))
	return str(table.get(key, CARD_TEXT.data.get("zh", {}).get(key, "")))

func set_language(value: String) -> void:
	var canonical := "zh-CN" if value == "zh" else value
	if not P.languages().has(canonical) or value == locale: return
	locale = value
	var config := ConfigFile.new()
	config.set_value("display", "locale", locale)
	config.save("user://settings.cfg")
	language_changed.emit(locale)
	Game.changed.emit()

static func locale_name(value: String) -> String:
	var canonical := "zh-CN" if value == "zh" else value
	return str(P.languages().get(canonical, {}).get("name", value))
