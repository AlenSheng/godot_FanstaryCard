extends RefCounted

const Details = preload("res://ui/card_details.gd")
const CardView = preload("res://ui/card_view.gd")
const Catalog = preload("res://data/catalog_index.gd")
const P = preload("res://ui/palette.gd")

func run_test() -> Dictionary:
	var errors: Array[String] = []
	var language := P.language()
	P.set_language("zh-CN")
	for level in range(6):
		if Details.face_description("C01", level) != "火伤%s" % (8 + level):
			errors.append("Fire damage did not follow upgrade level %s" % level)
	if Details.face_description("PRI-10", 5) != "治疗13·盾13·抽1·晕1.6秒":
		errors.append("Multi-effect upgrades must change heal, shield and duration without changing draw count")
	if Details.face_description("MAG-07", 5) != "抽牌加快15%/8.4秒":
		errors.append("Duration upgrades must not change the draw speed percentage")
	if Details.face_description("ET-FIRE-P", 5) != "火调伤12·抽牌加快35%/10.4秒":
		errors.append("Element tuning must retain its damage type and upgraded duration")
	if Details.face_description("GO08", 5) != "连放倍率+1档":
		errors.append("Non-scaling special effects must keep their rules")
	var ui = load("res://ui/main.gd").new()
	var baseline: String = ui._card_text("C01", 0)
	var upgraded: String = ui._card_text("C01", 5)
	if baseline == upgraded or not "火伤13" in upgraded or ui._card_text("C01", 0) != baseline:
		errors.append("Cached descriptions must distinguish upgrade levels")
	if ui.card_description("MAG-10", "full").length() <= ui.card_description("MAG-10", "face").length():
		errors.append("Full card details must retain the complete explanation")
	ui.free()
	var card := CardView.new()
	card.theme = P.theme()
	(Engine.get_main_loop() as SceneTree).root.add_child(card)
	card.size = Vector2(218, 376)
	var panel := Rect2(24, 303, 170, 54)
	var checked := 0
	for locale in ["zh-CN", "en"]:
		P.set_language(locale)
		for info in Catalog.cards().values():
			if not info.get("is_codex", false): continue
			for level in range(6):
				card.configure(str(info.id), info, "", false, {"collection": true, "copy_count": 1, "level": level})
				var title: Label = card.get_node("CardName")
				var effect: Label = card.get_node("CardEffect")
				if effect.text.is_empty() or effect.get_visible_line_count() != 1 or effect.get_theme_font_size("font_size") < 12:
					errors.append("Missing or unreadable summary: %s +%s %s" % [info.id, level, locale])
				if not panel.encloses(title.get_rect()) or not panel.encloses(effect.get_rect()) or title.get_rect().end.y > effect.position.y:
					errors.append("Card text escaped its panel: %s +%s %s" % [info.id, level, locale])
				checked += 1
	card.free()
	P.set_language(language)
	return {"ok": errors.is_empty(), "checked": checked, "errors": errors}
