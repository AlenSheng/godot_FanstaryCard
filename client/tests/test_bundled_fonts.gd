extends RefCounted

func run_test() -> Dictionary:
	var palette = load("res://ui/palette.gd")
	var body: FontFile = palette.font("body")
	var title: FontFile = palette.font("title")
	var numbers: Font = palette.font("number")
	var checks := {"Original bundled files load": body != null and title != null, "System fallback is disabled": not body.allow_system_fallback and not title.allow_system_fallback}
	var sample := "幻境牌旅湮核匣灵棘螨梵弦载岳音效设置静音黄铜纸牌强化金币龘←→×%0123456789"
	var missing := ""
	for character in sample:
		if not body.has_char(character.unicode_at(0)) or not title.has_char(character.unicode_at(0)): missing += character
	checks["Chinese and gameplay symbols have bundled glyphs"] = missing.is_empty()
	var width := numbers.get_string_size("0", HORIZONTAL_ALIGNMENT_LEFT, -1, 48).x
	var equal_width := width > 0
	for digit in "123456789":
		equal_width = equal_width and is_equal_approx(numbers.get_string_size(digit, HORIZONTAL_ALIGNMENT_LEFT, -1, 48).x, width)
	checks["All ten digits have equal advance"] = equal_width
	checks["Body and heading roles stay separate"] = palette.font_for_text("效果说明：火伤 7", 24) == body and palette.font_for_text("卡牌图鉴", 38) == title
	checks["Numbers use the number role"] = palette.font_for_text("70 / 100", 24) == numbers
	return {"ok": not checks.values().has(false), "checks": checks, "message": "Bundled Chinese coverage, font roles and equal-width counters", "missing_glyphs": missing}
