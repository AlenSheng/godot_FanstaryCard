extends RefCounted

const TipsOverlay = preload("res://ui/tips_overlay.gd")

func run_test() -> Dictionary:
	var overlay := TipsOverlay.new()
	overlay.label.text = "短提示"
	overlay._layout_at_start()
	var short_width := overlay.panel.size.x
	var short_height := overlay.panel.size.y
	overlay.label.text = "这是一条明显更长、用于检查提示底框是否根据多语言文本长度自动扩展的消息"
	overlay._layout_at_start()
	var long_width := overlay.panel.size.x
	var background: StyleBoxFlat = overlay.panel.get_theme_stylebox("panel")
	var checks := {
		"Tips use an independent overlay layer": overlay.layer > 100 and overlay.panel.name == "TipsPanel",
		"Bright yellow text stays readable on a dark background": overlay.label.get_theme_color("font_color").r > 0.9 and background.bg_color.get_luminance() < 0.1,
		"The backing panel adapts to localized text length": long_width > short_width and long_width <= 1920.0 * TipsOverlay.MAX_WIDTH_RATIO,
		"A single-line backing panel only slightly exceeds text height": short_height <= overlay.label.get_theme_font("font").get_height(overlay.label.get_theme_font_size("font_size")) + TipsOverlay.VERTICAL_PADDING + 1.0,
		"Animation lasts about two seconds and rises visibly": is_equal_approx(TipsOverlay.DISPLAY_DURATION, 2.0) and TipsOverlay.RISE_DISTANCE >= 40.0,
		"Tips appear above screen center": overlay.start_position().y < 1080.0 * 0.5,
	}
	overlay.free()
	return {"ok": not checks.values().has(false), "checks": checks, "message": JSON.stringify(checks)}
