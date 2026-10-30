extends RefCounted

const LEGACY_DATA = preload("res://data/localization_legacy.json")

static var _body_font: FontFile
static var _title_font: FontFile
static var _number_font: FontVariation
static var _fonts_ready := false
static var _scaled_body_font: FontFile
static var _scaled_title_font: FontFile
static var _scaled_number_font: FontVariation
static var _scaled_fonts_ready := false
static var _language := "zh-CN"
static var _locale_config: Dictionary = {}
static var _source_aliases: Dictionary = {}
static var _source_templates: Array[Dictionary] = []
static var _formatted_alias_cache: Dictionary = {}
const LANGUAGE_SETTINGS_PATH := "user://fantasycard_language.cfg"
const LOCALE_REGISTRY_PATH := "res://data/localization_registry.json"
const MIN_FITTED_FONT_SIZE := 20
static var _language_packs: Dictionary = {}
static var _partial_source_regex: RegEx
static var _partial_source_aliases: Dictionary = {}
static var _client_messages: Dictionary = {}
static var _fallback_font_cache: Dictionary = {}
static var _numeric_run_regex: RegEx
const NUMBER_FONT_PATH := "res://assets/fonts/SourceHanSansSC-Regular.otf"

static func clear_runtime_fonts() -> void:
	_body_font = null
	_title_font = null
	_number_font = null
	_fonts_ready = false
	_scaled_body_font = null
	_scaled_title_font = null
	_scaled_number_font = null
	_scaled_fonts_ready = false
	_fallback_font_cache.clear()

const INK := Color("172d35")
const PAPER := Color("efe3c7")
const MUTED := Color("a5bbb7")
const GOLD := Color("d3ae68")
const TEAL := Color("5cb9b0")
const QUALITY := {"White": Color("d0c9b6"), "Green": Color("789a70"), "Blue": Color("558cb8"), "Purple": Color("9979b1"), "Orange": Color("d99b48"), "Red": Color("ce5651")}
const DIRECT_DAMAGE := Color("f6e6b6")
const ELEMENT := {"Fire": Color("f18751"), "Wood": Color("72c878"), "Water": Color("5bc6d3"), "Metal": Color("e8d38a"), "Earth": Color("b69a70"), "None": Color.WHITE}
static var WORDS: Dictionary = LEGACY_DATA.data.words
static var CLASSES: Dictionary = _class_definitions()

static func _class_definitions() -> Dictionary:
	var result: Dictionary = LEGACY_DATA.data.classes.duplicate(true)
	for fields in result.values(): fields[2] = int(fields[2])
	return result
const WORD_KEYS := {
	"priest":"word_priest", "mage":"word_mage", "guardian":"word_guardian", "warrior":"word_warrior", "white":"word_white", "green":"word_green", "blue":"word_blue", "purple":"word_purple", "orange":"word_orange", "red":"word_red", "fire":"word_fire", "wood":"word_wood", "water":"word_water", "metal":"word_metal", "earth":"word_earth", "none":"word_none", "head":"word_head", "helmet":"word_head", "chest":"word_chest", "body":"word_chest", "hands":"word_hands", "gloves":"word_hands", "legs":"word_legs", "feet":"word_feet", "boots":"word_feet", "gold":"word_gold", "goldearned":"word_gold", "equipmentfragments":"word_equipment_fragments", "fragmentpack":"word_equipment_fragments", "warriorsoul":"word_warrior_soul", "classsoul":"word_class_soul", "soulpack":"word_warrior_soul", "classsoulpack":"word_class_soul", "priestsoul":"word_priest_soul", "magesoul":"word_mage_soul", "guardiansoul":"word_guardian_soul", "healthpotion":"word_health_potion", "equipment":"word_equipment", "item":"word_item", "card":"word_card", "cardpack":"word_card_pack", "advancedbag":"word_advanced_bag", "topbag":"word_top_bag", "diamond":"word_diamond", "bulwark":"word_bulwark", "piercing":"word_piercing", "vitality":"word_vitality", "damage":"word_damage", "heal":"word_heal", "support":"word_support", "elementtune":"word_element_coordination", "pve":"word_pve", "pvp":"word_pvp", "choice":"word_choice", "actionbar":"word_action_bar", "extracted":"word_extracted", "pvedeath":"word_pve_death", "pvpdeath":"word_pvp_death", "death":"word_death", "dead":"word_dead"
}
## Legacy source aliases are data; production copy lives in locales/<code>.json.
static var TEXT_KEYS: Dictionary = LEGACY_DATA.data.text_keys
static var EXTRA_TEXT_KEYS: Dictionary = LEGACY_DATA.data.extra_text_keys

static func word(value: Variant) -> String:
	if value == null: return ""
	var raw := str(value)
	var key: String = WORD_KEYS.get(_word_identifier(raw), "")
	return localized(key) if not key.is_empty() else WORDS.get(raw, raw)

## Display names for shop/catalog product kinds.  Keep this at the
## presentation boundary because the API may send PascalCase, snake_case,
## or legacy ids (for example `health_potion`).
static func product_name(value: Variant) -> String:
	if value == null: return ""
	var raw := str(value)
	var key: String = WORD_KEYS.get(_word_identifier(raw), "")
	return localized(key) if not key.is_empty() else word(raw)

## API/catalog identifiers use both PascalCase (HealthPotion) and snake_case
## (health_potion).  Normalize them before looking up display words so neither
## form can leak into a localized UI.
static func _word_identifier(value: String) -> String:
	return value.to_lower().replace("_", "").replace("-", "").replace(" ", "")

static func font(role: String = "body") -> Font:
	_ensure_locale()
	if not _fonts_ready:
		var body_path := str(_locale_config.languages[_language].fonts.body)
		var title_path := str(_locale_config.languages[_language].fonts.title)
		_body_font = _raster_font(body_path)
		_title_font = _raster_font(title_path)
		_body_font.fallbacks = _fallback_fonts("body", body_path)
		var title_fallbacks := _fallback_fonts("title", title_path)
		title_fallbacks.append(_body_font)
		_title_font.fallbacks = title_fallbacks
		_number_font = FontVariation.new()
		_number_font.base_font = _raster_font(NUMBER_FONT_PATH)
		# Source Han Sans ships equal-width default figures; keep proportional widths off.
		_number_font.opentype_features = {"pwid": 0}
		_fonts_ready = true
	match role:
		"title": return _title_font
		"number": return _number_font
	return _body_font

## Card faces have their own fractional transform in addition to window scaling.
## Distance-field glyphs keep those transformed edges sharp at all grid sizes.
static func scaled_font(role: String = "body") -> Font:
	if not _scaled_fonts_ready:
		_scaled_body_font = _distance_field_font(font("body") as FontFile)
		_scaled_title_font = _distance_field_font(font("title") as FontFile)
		_scaled_body_font.fallbacks = _fallback_fonts("body", str(_locale_config.languages[_language].fonts.body), true)
		var title_fallbacks := _fallback_fonts("title", str(_locale_config.languages[_language].fonts.title), true)
		title_fallbacks.append(_scaled_body_font)
		_scaled_title_font.fallbacks = title_fallbacks
		_scaled_number_font = FontVariation.new()
		_scaled_number_font.base_font = _distance_field_font(_number_font.base_font as FontFile)
		_scaled_number_font.opentype_features = {"pwid": 0}
		_scaled_fonts_ready = true
	match role:
		"title": return _scaled_title_font
		"number": return _scaled_number_font
	return _scaled_body_font

static func _raster_font(path: String) -> FontFile:
	# Keep imported prototypes unchanged so switching languages cannot form a
	# fallback cycle or change fonts still referenced by the previous frame.
	var prototype: FontFile = load(path)
	var result := prototype.duplicate() as FontFile
	result.fallbacks = []
	result.allow_system_fallback = false
	result.antialiasing = TextServer.FONT_ANTIALIASING_GRAY
	result.hinting = TextServer.HINTING_NORMAL
	result.force_autohinter = true
	result.subpixel_positioning = TextServer.SUBPIXEL_POSITIONING_ONE_QUARTER
	result.oversampling = 2.0
	result.generate_mipmaps = true
	return result

static func _fallback_fonts(role: String, primary_path: String, scaled: bool = false) -> Array[Font]:
	var result: Array[Font] = []
	for entry in _locale_config.get("font_fallbacks", {}).get(role, []):
		var path := str(entry)
		if path == primary_path: continue
		var key := path + ("/sdf" if scaled else "/raster")
		if not _fallback_font_cache.has(key):
			var typeface := _raster_font(path)
			_fallback_font_cache[key] = _distance_field_font(typeface) if scaled else typeface
		result.append(_fallback_font_cache[key])
	return result

static func _distance_field_font(source: FontFile) -> FontFile:
	var result := FontFile.new()
	result.data = source.data
	result.allow_system_fallback = false
	result.multichannel_signed_distance_field = true
	result.msdf_size = 96
	result.msdf_pixel_range = 8
	return result

static func _ensure_locale() -> void:
	if not _locale_config.is_empty(): return
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(LOCALE_REGISTRY_PATH))
	_locale_config = {"default_language": registry.get("default_language", "zh-CN"), "languages": {}, "font_fallbacks": registry.get("font_fallbacks", {})}
	_load_language_packs()
	_language = str(_locale_config.default_language)
	var saved_language := _load_language()
	if _locale_config.languages.has(saved_language): _language = saved_language
	_build_source_aliases()
	TranslationServer.set_locale(_language.replace("-", "_"))

static func _load_language_packs() -> void:
	var registry: Variant = JSON.parse_string(FileAccess.get_file_as_string(LOCALE_REGISTRY_PATH))
	if not registry is Dictionary: return
	for code in registry.get("languages", {}):
		var entry: Dictionary = registry.languages[code]
		var pack: Variant = JSON.parse_string(FileAccess.get_file_as_string(str(entry.get("path", ""))))
		if not pack is Dictionary: continue
		_language_packs[code] = pack
		_locale_config.languages[code] = {
			"name": str(entry.get("name", code)),
			"fonts": entry.get("fonts", {}),
			"direction": str(entry.get("direction", "ltr")),
			"strings": pack.get("strings", {})
		}

static func language_pack_section(section: String) -> Dictionary:
	_ensure_locale()
	return _language_packs.get(_language, {}).get(section, {})

static func key_for_text(value: String) -> String:
	_ensure_locale()
	return str(_source_aliases.get(value, ""))

static func element_stat(kind: String, element: Variant) -> String:
	var labels: Dictionary = language_pack_section("numerical").get("stat_text", {})
	return str(labels.get(kind, "%s")) % word(element)

static func _render_message(key: String, arguments: Array) -> String:
	var values: Array = []
	for argument in arguments:
		if argument is Dictionary and argument.has("translation_key"):
			values.append(localized(str(argument.translation_key)))
		else:
			values.append(argument)
	return localized(key) % values

## Preserve keys and arguments for client-owned messages cached in model state.
## Opaque values, including server versions, must not be translated as words.
static func message(key: String, arguments: Array) -> String:
	_ensure_locale()
	var result := _render_message(key, arguments)
	if _client_messages.size() >= 128: _client_messages.erase(_client_messages.keys()[0])
	_client_messages[result] = {"key": key, "arguments": arguments.duplicate(true)}
	return result

static func _build_source_aliases() -> void:
	_source_aliases.clear()
	_source_templates.clear()
	_formatted_alias_cache.clear()
	var letters := RegEx.new()
	letters.compile("\\p{L}")
	for language_config in _locale_config.get("languages", {}).values():
		var strings: Dictionary = language_config.get("strings", {})
		for key in strings:
			var source := str(strings[key])
			if source.length() < 2 or source == str(key) or letters.search(source) == null: continue
			# Accept display text authored in either language. This keeps legacy
			# screens localizable while they migrate from text to stable keys.
			if not _source_aliases.has(source): _source_aliases[source] = str(key)
	_partial_source_aliases = TEXT_KEYS.duplicate()
	_partial_source_aliases.merge(EXTRA_TEXT_KEYS)
	for code in ["zh-CN", "en"]:
		var authored_strings: Dictionary = _locale_config.languages[code].get("strings", {})
		for key in authored_strings:
			var source := str(authored_strings[key])
			if source.length() >= 2 and letters.search(source) != null and not _partial_source_aliases.has(source):
				_partial_source_aliases[source] = str(key)
	var phrases: Array = _partial_source_aliases.keys()
	phrases.sort_custom(func(left, right): return str(left).length() > str(right).length())
	var patterns: Array[String] = []
	for raw_phrase in phrases:
		var phrase := str(raw_phrase)
		if phrase.length() < 2: continue
		var escaped := ""
		for character in phrase:
			if character in "\\.^$|?*+()[]{}": escaped += "\\"
			escaped += character
		# Latin words must not match the prefix of a translated word (for
		# example Equip inside Equipo). Substitute original input only once.
		if phrase.left(1) in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz": escaped = "(?<![\\p{L}\\p{N}_])" + escaped
		if phrase.right(1) in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz": escaped += "(?![\\p{L}\\p{N}_])"
		patterns.append(escaped)
	_partial_source_regex = RegEx.new()
	if _partial_source_regex.compile("|".join(patterns)) != OK: _partial_source_regex = null
	var chinese: Dictionary = _locale_config.get("languages", {}).get("zh-CN", {}).get("strings", {})
	var english: Dictionary = _locale_config.get("languages", {}).get("en", {}).get("strings", {})
	for key in chinese:
		if not english.has(key): continue
		var source := str(chinese[key])
		var target := str(english[key])
		if not source.contains("%") or source == target or letters.search(source) == null: continue
		var prefix := source.get_slice("%", 0)
		if prefix.length() < 2 and source.length() < 5: continue
		var compiled := RegEx.new()
		var pattern := _format_pattern(source)
		if compiled.compile(pattern) != OK: continue
		_source_templates.append({"regex": compiled, "prefix": prefix, "key": str(key)})

static func _format_pattern(source: String) -> String:
	var pattern := "^"
	var index := 0
	while index < source.length():
		var character := source.substr(index, 1)
		if character == "%":
			if index + 1 < source.length() and source.substr(index + 1, 1) == "%":
				pattern += "%"
				index += 2
				continue
			var end := index + 1
			while end < source.length() and source.substr(end, 1) in "0123456789.-+": end += 1
			if end < source.length() and source.substr(end, 1) in "sdf":
				pattern += "(.+?)"
				index = end + 1
				continue
		if character in "\\.^$|?*+()[]{}": pattern += "\\"
		pattern += character
		index += 1
	return pattern + "$"

static func _fill_format(template: String, matches: RegExMatch) -> String:
	var result := ""
	var index := 0
	var argument := 1
	while index < template.length():
		var character := template.substr(index, 1)
		if character == "%":
			if index + 1 < template.length() and template.substr(index + 1, 1) == "%":
				result += "%"
				index += 2
				continue
			var end := index + 1
			while end < template.length() and template.substr(end, 1) in "0123456789.-+": end += 1
			if end < template.length() and template.substr(end, 1) in "sdf":
				if argument >= matches.get_group_count() + 1: return ""
				result += matches.get_string(argument)
				argument += 1
				index = end + 1
				continue
		result += character
		index += 1
	return result if argument == matches.get_group_count() + 1 else ""

static func _localized_format_alias(value: String) -> String:
	if _language == "zh-CN": return ""
	if _formatted_alias_cache.has(value): return str(_formatted_alias_cache[value])
	for entry in _source_templates:
		if not value.begins_with(str(entry.prefix)): continue
		var matched: RegExMatch = entry.regex.search(value)
		if matched == null: continue
		var translated := _fill_format(localized(str(entry.key)), matched)
		if translated.is_empty(): continue
		_formatted_alias_cache[value] = translated
		return translated
	return ""

static func language() -> String:
	_ensure_locale()
	return _language

static func set_language(value: String) -> void:
	_ensure_locale()
	if not _locale_config.get("languages", {}).has(value): return
	if _language == value: return
	_language = value
	_fonts_ready = false
	_scaled_fonts_ready = false
	_formatted_alias_cache.clear()
	TranslationServer.set_locale(_language.replace("-", "_"))
	_save_language()

static func _save_language() -> void:
	var settings := ConfigFile.new()
	settings.set_value("ui", "language", _language)
	settings.save(LANGUAGE_SETTINGS_PATH)

static func _load_language() -> String:
	var settings := ConfigFile.new()
	if settings.load(LANGUAGE_SETTINGS_PATH) != OK: return ""
	return str(settings.get_value("ui", "language", ""))

static func localized(key: String) -> String:
	_ensure_locale()
	var language_config: Dictionary = _locale_config.get("languages", {}).get(_language, {})
	var strings: Dictionary = language_config.get("strings", {})
	if strings.has(key): return str(strings[key])
	return str(language_config.get("mail_strings", {}).get(key, key))

static func localized_text(value: String) -> String:
	if value.is_empty(): return value
	_ensure_locale()
	if _client_messages.has(value):
		var cached: Dictionary = _client_messages[value]
		return _render_message(str(cached.key), cached.arguments)
	if _locale_config.languages[_language].get("strings", {}).has(value): return localized(value)
	var localized_identifier := word(value)
	if localized_identifier != value: return localized_identifier
	var aliases := TEXT_KEYS.duplicate()
	aliases.merge(EXTRA_TEXT_KEYS)
	aliases.merge(_source_aliases)
	aliases.merge(LEGACY_DATA.data.inline_aliases)
	if aliases.has(value): return localized(aliases[value])
	var formatted := _localized_format_alias(value)
	if not formatted.is_empty(): return formatted
	if _partial_source_regex == null: return value
	var result := ""
	var cursor := 0
	for matched in _partial_source_regex.search_all(value):
		result += value.substr(cursor, matched.get_start() - cursor)
		var phrase: String = matched.get_string()
		var key := str(_partial_source_aliases.get(phrase, ""))
		var translated := localized(key)
		result += phrase if translated == key else translated
		cursor = matched.get_end()
	result += value.substr(cursor)
	return result

static func localized_word(value: Variant) -> String:
	var keys := {"gold": "word_gold", "equipmentfragments": "word_equipment_fragments", "fragmentpack": "word_equipment_fragments", "healthpotion": "word_health_potion", "warriorsoul": "word_warrior_soul", "classsoul": "word_warrior_soul", "soulpack": "word_warrior_soul", "classsoulpack": "word_warrior_soul", "priestsoul": "word_priest_soul", "magesoul": "word_mage_soul", "guardiansoul": "word_guardian_soul", "equipment": "word_equipment", "item": "word_equipment", "card": "word_card", "cardpack": "word_card", "advancedbag": "word_advanced_bag", "topbag": "word_top_bag", "diamond": "word_diamond", "white": "word_white", "green": "word_green", "blue": "word_blue", "purple": "word_purple", "orange": "word_orange", "red": "word_red", "fire": "word_fire", "wood": "word_wood", "water": "word_water", "metal": "word_metal", "earth": "word_earth", "head": "word_head", "helmet": "word_head", "chest": "word_chest", "body": "word_chest", "hands": "word_hands", "gloves": "word_hands", "legs": "word_legs", "feet": "word_feet", "boots": "word_feet", "none": "word_equipment"}
	var key: String = keys.get(_word_identifier(str(value)), "")
	return localized(key) if not key.is_empty() else word(value)

## Server-side validation details are not localization keys.  Use this only at
## presentation boundaries (such as transient tips) to avoid exposing English
## diagnostics in the Simplified Chinese client.
static func is_unlocalized_english_sentence(value: String) -> bool:
	if language() != "zh-CN": return false
	var letters := 0
	var has_sentence_separator := false
	for character in value:
		if character.to_lower() != character.to_upper(): letters += 1
		if character in " .,!?:;": has_sentence_separator = true
	return letters >= 3 and has_sentence_separator

static func languages() -> Dictionary:
	_ensure_locale()
	return _locale_config.get("languages", {})

static func font_for_text(value: String, size: int = 24, scaled: bool = false) -> Font:
	var numeric := is_numeric_text(value)
	var role := "number" if numeric else ("title" if size >= 32 and value.length() <= 26 and not value.contains("\n") else "body")
	return scaled_font(role) if scaled else font(role)

static func is_numeric_text(value: String) -> bool:
	if value.is_empty(): return false
	for character in value:
		if is_bidi_isolate(character.unicode_at(0)): continue
		if character not in "0123456789+-−.,:%/ ×|→←()\n\t": return false
	return true

static func is_bidi_isolate(codepoint: int) -> bool:
	return codepoint >= 0x2066 and codepoint <= 0x2069

static func system_display_text(value: String) -> String:
	# Only call for locally composed system copy, never authored remote text.
	# Isolates affect visual ordering; locale tables, wire values and tooltips
	# retain their original text. In particular, -5 and 4 / 10 stay LTR in Arabic.
	if str(languages()[language()].get("direction", "ltr")) != "rtl": return value
	var lri := String.chr(0x2066)
	var fsi := String.chr(0x2068)
	var pdi := String.chr(0x2069)
	if value.contains(lri) or value.contains(fsi): return value
	if _numeric_run_regex == null:
		_numeric_run_regex = RegEx.new()
		_numeric_run_regex.compile("[+−-]?[0-9]+(?:[.,][0-9]+)?%?(?:[ \\t]*(?:[/|→←×x])[ \\t]*[+−-]?[0-9]+(?:[.,][0-9]+)?%?)*")
	var paragraphs := PackedStringArray()
	for paragraph in value.split("\n", true):
		if paragraph.contains(" | "):
			var cells := PackedStringArray()
			for cell in paragraph.split(" | ", true): cells.append(fsi + cell + pdi)
			paragraphs.append(lri + " | ".join(cells) + pdi)
			continue
		if is_numeric_text(paragraph):
			paragraphs.append(lri + paragraph + pdi)
			continue
		var formatted := ""
		var cursor := 0
		for matched in _numeric_run_regex.search_all(paragraph):
			formatted += paragraph.substr(cursor, matched.get_start() - cursor) + lri + matched.get_string() + pdi
			cursor = matched.get_end()
		paragraphs.append(formatted + paragraph.substr(cursor))
	return "\n".join(paragraphs)

static func without_bidi_isolates(value: String) -> String:
	var result := ""
	for character in value:
		if not is_bidi_isolate(character.unicode_at(0)): result += character
	return result

static func apply_text_direction(control: Control) -> void:
	# A neutral numeric paragraph must keep current/max and signed deltas in
	# source order. Natural language paragraphs retain automatic BiDi shaping.
	if control is Label or control is Button or control is LineEdit:
		control.text_direction = Control.TEXT_DIRECTION_LTR if is_numeric_text(str(control.get("text"))) else Control.TEXT_DIRECTION_AUTO

static func fit_font_size(typeface: Font, requested: int, height: float, width: float = -1.0, value: String = "") -> int:
	var fitted := requested
	# Keep the authored rectangles stable; reduce only the text size when a translation is wider.
	# Never hide a layout failure by reducing translated copy to a few pixels.
	# Compact, explicitly authored annotations retain their authored size.
	var minimum := mini(requested, MIN_FITTED_FONT_SIZE)
	while fitted > minimum:
		if height > 0.0 and ceilf(typeface.get_height(fitted)) > height:
			fitted -= 1
			continue
		if width > 0.0 and not value.is_empty():
			var longest := 0.0
			for line in value.split("\n"):
				longest = maxf(longest, typeface.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1.0, fitted).x)
			if longest > width:
				fitted -= 1
				continue
		break
	return fitted

static func fit_control_font(control: Control, typeface: Font, requested: int, horizontal_padding: float = 0.0) -> void:
	if not is_instance_valid(control): return
	var update := func() -> void:
		if not is_instance_valid(control): return
		apply_text_direction(control)
		# Containers allocate their children after insertion. Fitting the initial
		# zero-width rectangle shrinks the font and therefore its minimum size,
		# trapping labels at one pixel before layout can give them room.
		if control.size.x <= horizontal_padding + 1.0:
			if control.get_theme_font_size("font_size") != requested:
				control.add_theme_font_size_override("font_size", requested)
			return
		var value := str(control.get("text"))
		var width := maxf(1.0, control.size.x - horizontal_padding)
		# A container-managed label's height comes from its font, rather than an
		# authored text box. Keep that minimum height independent of font fitting.
		var height := -1.0 if control.get_parent() is Container else control.size.y
		# Wrapping container labels grow vertically; fitting their whole paragraph
		# on one line would make translated help text unnecessarily tiny.
		var wrapping_container_label: bool = control is Label and control.get_parent() is Container and control.autowrap_mode != TextServer.AUTOWRAP_OFF
		var fitted: int = requested if wrapping_container_label else fit_font_size(typeface, requested, height, width, value)
		if control.get_theme_font_size("font_size") != fitted:
			control.add_theme_font_size_override("font_size", fitted)
	control.resized.connect(update)
	# Resized will refit after layout. The initial size is already available
	# here; deferring a lambda can retain a card that was returned to the pool.
	update.call()

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
	var tooltip_panel := StyleBoxFlat.new()
	tooltip_panel.bg_color = Color("101b21")
	tooltip_panel.border_color = Color("d3ae68")
	tooltip_panel.set_border_width_all(2)
	tooltip_panel.set_corner_radius_all(8)
	tooltip_panel.content_margin_left = 20
	tooltip_panel.content_margin_right = 20
	tooltip_panel.content_margin_top = 14
	tooltip_panel.content_margin_bottom = 14
	result.set_stylebox("panel", "TooltipPanel", tooltip_panel)
	result.set_font("font", "TooltipLabel", font("body"))
	result.set_font_size("font_size", "TooltipLabel", 22)
	result.set_color("font_color", "TooltipLabel", PAPER)
	result.set_color("font_outline_color", "TooltipLabel", Color(0, 0, 0, 1))
	result.set_constant("outline_size", "TooltipLabel", 3)
	result.set_constant("separation", "VBoxContainer", 18)
	result.set_constant("separation", "HBoxContainer", 20)
	result.set_constant("h_separation", "GridContainer", 16)
	result.set_constant("v_separation", "GridContainer", 16)
	return result
