extends Node

signal language_changed(locale: String)

const CARD_TEXT = preload("res://data/card_descriptions.json")
const UI_TEXT = preload("res://data/ui_text.json")
const LOCALES := {"zh": "简体中文", "en": "English"}
static var locale := "zh"
static var _ui := {
	"zh": {"设置": "设置", "音效设置": "音效设置", "音效": "音效", "音量": "音量", "静音": "静音", "返回": "返回", "试听 · 黄铜与纸牌": "试听 · 黄铜与纸牌", "语言": "语言", "退出登录": "退出登录", "确认退出登录？": "确认退出登录？", "确认": "确认", "取消": "取消", "幻境牌旅": "幻境牌旅", "金币": "金币", "未连接": "未连接", "正在读取…": "正在读取…", "卡组": "卡组", "图鉴": "图鉴", "卡牌": "卡牌", "卡组为空，点击左侧卡牌加入": "卡组为空，点击左侧卡牌加入", "当前卡组": "当前卡组", "容量": "容量", "点击移除一张": "点击移除一张", "辅助效果": "辅助效果"},
	"en": {"设置": "Settings", "音效设置": "Audio Settings", "音效": "Audio", "音量": "Volume", "静音": "Mute", "返回": "Back", "试听 · 黄铜与纸牌": "Preview · Brass and Cards", "语言": "Language", "退出登录": "Log out", "确认退出登录？": "Log out now?", "确认": "Confirm", "取消": "Cancel", "幻境牌旅": "Fantasy Card", "金币": "Gold", "未连接": "Disconnected", "正在读取…": "Loading…", "卡组": "Deck", "图鉴": "Codex", "卡牌": "Cards", "卡组为空，点击左侧卡牌加入": "Deck is empty. Click a card on the left to add it.", "当前卡组": "Current deck", "容量": "Capacity", "点击移除一张": "Click to remove one copy", "辅助效果": "Support effect"}
}

func _ready() -> void:
	var configured: Dictionary = UI_TEXT.data.get("locales", {})
	if not configured.is_empty(): _ui = configured
	var config := ConfigFile.new()
	if config.load("user://settings.cfg") == OK:
		locale = str(config.get_value("display", "locale", "zh"))
	if not _ui.has(locale): locale = "zh"

static func t(value: String) -> String:
	if value.is_empty(): return value
	if not _ui.has(locale): return value
	if _ui[locale].has(value): return _ui[locale][value]
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
	if not _ui.has(value) or value == locale: return
	locale = value
	var config := ConfigFile.new()
	config.set_value("display", "locale", locale)
	config.save("user://settings.cfg")
	language_changed.emit(locale)

static func locale_name(value: String) -> String:
	return str(LOCALES.get(value, value))
