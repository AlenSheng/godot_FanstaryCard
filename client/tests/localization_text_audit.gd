extends RefCounted

## Test-only source-copy oracle. Japanese legitimately uses Han characters;
## recognize its authored vocabulary while retaining a Chinese-source check.
var _locale: String
var _target_han: Dictionary = {}
var _source_han: Dictionary = {}
var _forbidden_fragments: RegEx

func _init(locale: String, chinese: Dictionary, target: Dictionary) -> void:
	_locale = locale
	if locale != "ja": return
	var target_leaves: Array[String] = []
	_collect_strings(target, target_leaves)
	var target_corpus := "\n".join(target_leaves)
	for character in target_corpus:
		if _is_han(character.unicode_at(0)): _target_han[character] = true
	var source_leaves: Array[String] = []
	_collect_strings(chinese, source_leaves)
	var han_runs := RegEx.new()
	han_runs.compile("[\\x{3400}-\\x{9fff}]{2,}")
	var fragments := {}
	for source in source_leaves:
		for character in source:
			if _is_han(character.unicode_at(0)): _source_han[character] = true
		for matched in han_runs.search_all(source):
			var fragment := matched.get_string()
			if not target_corpus.contains(fragment): fragments[fragment] = true
	if fragments.is_empty(): return
	var ordered: Array = fragments.keys()
	ordered.sort_custom(func(a, b): return str(a).length() > str(b).length())
	_forbidden_fragments = RegEx.new()
	assert(_forbidden_fragments.compile("|".join(ordered)) == OK)

func unexpected_han(value: String) -> Array[String]:
	var result: Array[String] = []
	if _locale in ["zh-CN", "zh-TW"]: return result
	for character in value:
		if not _is_han(character.unicode_at(0)): continue
		if _locale != "ja" or (_source_han.has(character) and not _target_han.has(character)):
			if not result.has(character): result.append(character)
	if _locale == "ja" and _forbidden_fragments != null:
		for matched in _forbidden_fragments.search_all(value):
			var fragment := matched.get_string()
			if not result.has(fragment): result.append(fragment)
	return result

static func _is_han(codepoint: int) -> bool:
	return codepoint >= 0x3400 and codepoint <= 0x9fff

static func _collect_strings(value: Variant, result: Array[String]) -> void:
	if value is String:
		result.append(value)
	elif value is Dictionary:
		for child in value.values(): _collect_strings(child, result)
	elif value is Array:
		for child in value: _collect_strings(child, result)
