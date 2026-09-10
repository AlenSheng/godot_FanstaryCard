extends RefCounted

static var _body_font: FontFile = preload("res://assets/fonts/SourceHanSansSC-Regular.otf")
static var _title_font: FontFile = preload("res://assets/fonts/SourceHanSerifSC-SemiBold.otf")
static var _number_font: FontVariation
static var _fonts_ready := false

const INK := Color("172d35")
const PAPER := Color("efe3c7")
const MUTED := Color("a5bbb7")
const GOLD := Color("d3ae68")
const TEAL := Color("5cb9b0")
const QUALITY := {"White": Color("d0c9b6"), "Green": Color("789a70"), "Blue": Color("558cb8"), "Purple": Color("9979b1"), "Orange": Color("d99b48"), "Red": Color("ce5651")}
const ELEMENT := {"Fire": Color("f18751"), "Wood": Color("72c878"), "Water": Color("5bc6d3"), "Metal": Color("e8d38a"), "Earth": Color("b69a70"), "None": Color.WHITE}
const WORDS := {"Priest": "牧", "Mage": "法", "Guardian": "盾", "White": "白", "Green": "绿", "Blue": "蓝", "Purple": "紫", "Orange": "橙", "Red": "红", "Fire": "火", "Wood": "木", "Water": "水", "Metal": "金", "Earth": "土", "None": "直伤", "Head": "头部", "Helmet": "头部", "Chest": "胸甲", "Body": "胸甲", "Hands": "手部", "Gloves": "手部", "Legs": "腿部", "Feet": "鞋子", "Boots": "鞋子", "Gold": "金币", "EquipmentFragments": "装备碎片", "WarriorSoul": "勇士之魂", "ClassSoul": "职业之魂", "HealthPotion": "生命药剂", "Equipment": "装备", "CardPack": "卡包", "SoulPack": "勇士之魂包", "FragmentPack": "碎片包", "ClassSoulPack": "职业之魂包", "AdvancedBag": "高级背包", "TopBag": "顶级背包", "Card": "卡牌", "Bulwark": "载壁", "Piercing": "破击", "Vitality": "生息", "Damage": "伤害", "Heal": "回复", "Support": "辅助", "Pve": "交战", "Pvp": "决斗", "Choice": "战利品", "ActionBar": "探索", "Extracted": "撤离成功", "PveDeath": "探索失利", "PvpDeath": "决斗失利", "Death": "探索失利", "Dead": "探索失利"}
const CLASSES := {"Priest": ["潮听 · 临", "临渊杖", 80, "潮汐将至，听见生机。", "残血治疗 / 控场"], "Mage": ["余烬 · 凯", "焚弦薪", 70, "让最后一簇火，照亮归途。", "元素连携 / 快攻"], "Guardian": ["载山 · 敦", "载岳盾", 100, "山岳不移，守住每次归来。", "满血护盾 / 坚守"]}

static func word(value: Variant) -> String:
	if value == null: return ""
	return WORDS.get(str(value), str(value))

static func font(role: String = "body") -> Font:
	if not _fonts_ready:
		_body_font.allow_system_fallback = false
		_title_font.allow_system_fallback = false
		_title_font.fallbacks = [_body_font]
		_number_font = FontVariation.new()
		_number_font.base_font = _body_font
		# Source Han Sans ships equal-width default figures; keep proportional widths off.
		_number_font.opentype_features = {"pwid": 0}
		_fonts_ready = true
	match role:
		"title": return _title_font
		"number": return _number_font
	return _body_font

static func font_for_text(value: String, size: int = 24) -> Font:
	var numeric := not value.is_empty()
	for character in value:
		if character not in "0123456789+-−.,:%/ ×":
			numeric = false
			break
	if numeric: return font("number")
	return font("title") if size >= 32 and value.length() <= 26 and not value.contains("\n") else font("body")

static func fit_font_size(typeface: Font, requested: int, height: float) -> int:
	var fitted := requested
	# Fixed reference rectangles must accommodate at least one full CJK line.
	while fitted > 1 and ceilf(typeface.get_height(fitted)) > height:
		fitted -= 1
	return fitted

static func box(color: Color = INK, border: Color = Color("47626a"), width: int = 2) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.border_color = border
	style.set_border_width_all(width)
	style.set_corner_radius_all(12)
	style.content_margin_left = 24
	style.content_margin_right = 24
	style.content_margin_top = 16
	style.content_margin_bottom = 16
	return style

static func theme() -> Theme:
	var result := Theme.new()
	result.default_font = font("body")
	result.default_font_size = 24
	result.set_font("font", "Button", font("title"))
	result.set_font("font", "LineEdit", font("body"))
	result.set_font("font", "TextEdit", font("body"))
	result.set_font("normal_font", "RichTextLabel", font("body"))
	result.set_color("font_color", "Label", PAPER)
	result.set_color("font_color", "Button", PAPER)
	result.set_color("font_hover_color", "Button", Color.WHITE)
	result.set_color("font_disabled_color", "Button", Color("73837f"))
	result.set_stylebox("normal", "Button", box())
	result.set_stylebox("hover", "Button", box(Color("254650"), GOLD))
	result.set_stylebox("pressed", "Button", box(Color("38615f"), TEAL, 3))
	result.set_stylebox("focus", "Button", box(Color(0, 0, 0, 0), GOLD, 3))
	result.set_stylebox("disabled", "Button", box(Color("1e3034"), Color("33464b")))
	result.set_stylebox("normal", "LineEdit", box(Color("10272e")))
	result.set_stylebox("panel", "PanelContainer", box())
	result.set_constant("separation", "VBoxContainer", 18)
	result.set_constant("separation", "HBoxContainer", 20)
	result.set_constant("h_separation", "GridContainer", 16)
	result.set_constant("v_separation", "GridContainer", 16)
	return result
