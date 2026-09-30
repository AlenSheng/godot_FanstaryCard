extends "res://tests/ui_integration_art_preview.gd"

const P = preload("res://ui/palette.gd")
const Details = preload("res://ui/card_details.gd")
const IDS := ["M-FIREBAT", "M-THORNMITE", "M-MUDHYDRA", "M-SANDLIZARD", "M-RUSTRAT", "M-GOLDGUARD", "M-FIREREAVER", "M-SWAMPMOTHER", "M-STONEGUARD", "M-THORNGUARD", "M-VOIDCORE", "M-BOXSPIRIT"]
const SPECIES := ["fire-bat", "thorn-mite", "murk-snail", "sand-lizard", "rust-rat", "metal-guard", "fire-herald", "marsh-mother", "stone-guard", "thorn-guard", "annihilation-core", "box-spirit"]
var captures: Array[Dictionary] = []
var title_metrics: Array[Dictionary] = []
var pixel_checks: Array[Dictionary] = []

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output + "/pixels"))
	for locale in ["zh-CN", "en"]:
		P.set_language(locale)
		$UI.theme = P.theme()
		for resolution in [Vector2i(1920, 1080), Vector2i(1280, 720), Vector2i(960, 540)]:
			get_window().size = resolution
			await get_tree().process_frame
			Game.room = {"allowed_actions": ["battle.play_cards", "battle.select_target"],
				"player": {"player_id": "preview-player", "hero_class": "Mage", "phase": "Pve", "combat": {"hp": 48, "maximum_hp": 70, "shield": 6}, "draw_charge": "0.55", "hand": []},
				"pve": {"battle_id": "preview", "current_target_id": "fire-bat", "monsters": []}}
			for pair in range(6):
				Game.room.player.hand = []
				Game.room.pve.monsters = []
				for offset in range(2):
					var index: int = pair * 2 + offset
					Game.room.player.hand.append({"instance_id": IDS[index], "card_id": IDS[index]})
					Game.room.pve.monsters.append({"monster_id": SPECIES[index], "hp": 24, "maximum_hp": 44, "shield": 0, "intent_kind": "Attack", "intent_element": "Earth" if offset == 0 else "Water", "intent_value": 6, "boss_phase": 1})
				Game.room.pve.current_target_id = SPECIES[pair * 2]
				Game.selected_cards = [IDS[pair * 2]]
				var suffix := "%s_%s" % [locale, resolution.x]
				var capture_name := "monsters_%s_%s" % [pair + 1, suffix]
				await _capture(capture_name)
				captures.append({"file": capture_name + ".png", "locale": locale, "pixels": [resolution.x, resolution.y], "ids": [IDS[pair * 2], IDS[pair * 2 + 1]]})
				await _review_titles(pair, suffix)
	var report := {"ok": layout_errors.is_empty(), "source_sha": OS.get_environment("FANTASYCARD_SOURCE_SHA"),
		"phase": OS.get_environment("FANTASYCARD_TITLE_PHASE"), "screenshots": screenshot_count,
		"captures": captures, "title_metrics": title_metrics, "pixel_checks": pixel_checks, "errors": layout_errors,
		"scope": "All 12 real monster cards in the production battle hand; two languages, three physical window sizes. Native title pixels are compared with an independent unwrapped Label at identical font, size, color and rectangle. References do not change production text or runtime artwork."}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify({"ok": report.ok, "screenshots": screenshot_count, "title_samples": title_metrics.size(), "pixel_comparisons": pixel_checks.size(), "errors": layout_errors.size()}))
	get_tree().quit(0 if report.ok else 1)

func _review_titles(pair: int, suffix: String) -> void:
	var originals: Array[Label] = []
	var references: Array[Label] = []
	var rectangles: Array[Rect2i] = []
	RenderingServer.force_draw(false)
	var actual := get_viewport().get_texture().get_image()
	var transform := get_viewport().get_stretch_transform()
	for offset in range(2):
		var id: String = IDS[pair * 2 + offset]
		var card: Button = $UI._reference.get_node("Card_" + id)
		var label: Label = card.get_node("MonsterName")
		var species_name: String = Details.localized_name(id, $UI.cards[id])
		var complete: String = P.localized("monster") + " " + species_name
		var typeface: Font = label.get_theme_font("font")
		var font_size: int = label.get_theme_font_size("font_size")
		var width: float = typeface.get_string_size(label.text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, font_size).x
		var fits: bool = width <= label.size.x - 8.0 + 0.5 and typeface.get_height(font_size) <= label.size.y
		var single_line: bool = label.get_line_count() == 1 and label.get_visible_line_count() == 1
		var full_species: bool = label.text == complete or (label.text == species_name and card.tooltip_text.contains(complete))
		var policy: bool = label.max_lines_visible == 1 and label.autowrap_mode == TextServer.AUTOWRAP_OFF and label.text_overrun_behavior == TextServer.OVERRUN_TRIM_ELLIPSIS
		var key := id + "_" + suffix
		title_metrics.append({"key": key, "text": label.text, "complete_title": complete, "species_name": species_name,
			"font_resource": typeface.resource_path, "font_size": font_size, "measured_width": width, "available_width": label.size.x - 8.0,
			"lines": label.get_line_count(), "visible_lines": label.get_visible_line_count(), "fits": fits,
			"single_line": single_line, "full_species": full_species, "single_line_ellipsis_policy": policy,
			"font_is_themed_title": typeface == P.font("title"), "rect": str(label.get_global_rect())})
		if not fits: layout_errors.append(key + ": actual title font exceeds safe title area")
		if not single_line: layout_errors.append(key + ": wrapped or hidden title line")
		if not full_species: layout_errors.append(key + ": complete species name unavailable")
		if font_size < 14: layout_errors.append(key + ": title font below readable floor")
		if not policy: layout_errors.append(key + ": title lacks safe single-line ellipsis policy")
		var rect := Rect2i(transform * label.get_global_rect()).intersection(Rect2i(Vector2i.ZERO, actual.get_size()))
		rectangles.append(rect)
		actual.get_region(rect).save_png(output + "/pixels/" + key + "_actual.png")
		# Independent native rendering of the entire current text, with wrapping
		# and ellipsis disabled. Geometry/font remain identical for comparison.
		var reference := Label.new()
		reference.text = label.text
		reference.horizontal_alignment = label.horizontal_alignment
		reference.vertical_alignment = label.vertical_alignment
		reference.autowrap_mode = TextServer.AUTOWRAP_OFF
		reference.max_lines_visible = 1
		reference.clip_text = true
		reference.text_overrun_behavior = TextServer.OVERRUN_NO_TRIMMING
		reference.mouse_filter = Control.MOUSE_FILTER_IGNORE
		reference.add_theme_font_override("font", typeface)
		reference.add_theme_font_size_override("font_size", font_size)
		reference.add_theme_color_override("font_color", label.get_theme_color("font_color"))
		card.add_child(reference)
		reference.position = label.position
		reference.size = label.size
		label.hide()
		originals.append(label)
		references.append(reference)
	await get_tree().process_frame
	RenderingServer.force_draw(false)
	var unwrapped := get_viewport().get_texture().get_image()
	for offset in range(originals.size()):
		var key: String = IDS[pair * 2 + offset] + "_" + suffix
		var actual_crop := actual.get_region(rectangles[offset])
		var reference_crop := unwrapped.get_region(rectangles[offset])
		var equal: bool = actual_crop.get_data() == reference_crop.get_data()
		reference_crop.save_png(output + "/pixels/" + key + "_reference.png")
		pixel_checks.append({"key": key, "equal": equal, "pixels": [rectangles[offset].size.x, rectangles[offset].size.y],
			"actual": "pixels/" + key + "_actual.png", "reference": "pixels/" + key + "_reference.png"})
		if not equal: layout_errors.append(key + ": native title pixels differ from complete single-line reference")
		originals[offset].show()
		references[offset].free()
