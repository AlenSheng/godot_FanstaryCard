extends SceneTree

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var P = load("res://ui/palette.gd")
	var View = load("res://ui/card_view.gd")
	var cases: Array[Dictionary] = []
	var errors: Array[String] = []
	for locale in ["en", "zh-CN"]:
		P.set_language(locale)
		for value in (["Stoneplate Guard", "Ancient Annihilation Core of the Thorn Guardians"] if locale == "en" else ["远古荆棘守卫", "远古深渊荆棘遗迹守卫者的毁灭核心"]):
			var card := Button.new()
			card.set_script(View)
			card.theme = P.theme()
			root.add_child(card)
			card.size = Vector2(218, 376)
			card._monster_text("M-TITLE-FALLBACK", {"name": value}, "", false)
			await process_frame
			var title: Label = card.get_node("MonsterName")
			var size: int = title.get_theme_font_size("font_size")
			var row := {"locale": locale, "input": value, "text": title.text, "font_size": size,
				"species_preserved": title.text.ends_with(value), "tooltip_preserved": card.tooltip_text.begins_with(P.localized("monster") + " " + value),
				"single_line": title.get_line_count() == 1, "safe_ellipsis": title.text_overrun_behavior == TextServer.OVERRUN_TRIM_ELLIPSIS}
			cases.append(row)
			if size < 16 or not row.species_preserved or not row.tooltip_preserved or not row.single_line or not row.safe_ellipsis:
				errors.append(locale + ": " + value)
			card.free()
	var result := {"ok": errors.is_empty(), "source_sha": OS.get_environment("FANTASYCARD_SOURCE_SHA"), "cases": cases, "errors": errors,
		"scope": "Headless localized overflow guard, supplemental to the 12-species native pixel matrix. Does not claim synthetic text was a live catalog name."}
	FileAccess.open(OS.get_environment("FANTASYCARD_FALLBACK_RESULTS"), FileAccess.WRITE).store_string(JSON.stringify(result, "  "))
	print(JSON.stringify(result))
	quit(0 if result.ok else 1)
