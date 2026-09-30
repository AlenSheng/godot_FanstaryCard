extends "res://tests/ui_style_audit.gd"

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	await get_tree().create_timer(0.5).timeout
	for locale in ["zh-CN", "en"]:
		Palette.set_language(locale)
		$UI.theme = Palette.theme()
		for resolution in [Vector2i(1280, 720), Vector2i(960, 540)]:
			get_window().size = resolution
			await get_tree().process_frame
			_reset()
			# Use the production lobby bootstrap, which starts the virtual card pool.
			Game.lobby["cards"] = $UI.owned
			$UI._clear_card_page_cache()
			$UI._codex_scroll = 0
			$UI._quality = ""
			$UI.screen = "cards"
			Game.changed.emit()
			await get_tree().process_frame
			await get_tree().process_frame
			await _wait_grid()
			var suffix := "%s_%s" % [locale, resolution.x]
			await _take("codex_ready_" + suffix, false)
			var selected_id := ""
			var longest := -1
			for id in $UI.cards:
				if not $UI.cards[id].get("is_codex", false): continue
				var length: int = $UI._card_text(id, 5).length() + preload("res://ui/card_details.gd").localized_name(id, $UI.cards[id]).length()
				if length > longest:
					longest = length
					selected_id = id
			for entry in $UI.owned:
				if entry.cardId == selected_id:
					entry.unlocked = true
					entry.copyCount = 1
					entry.level = 5
			$UI._clear_card_page_cache()
			$UI._render()
			var search: LineEdit = $UI._reference.get_node("CodexSearch")
			search.text = preload("res://ui/card_details.gd").localized_name(selected_id, $UI.cards[selected_id])
			search.text_changed.emit(search.text)
			await _wait_grid()
			var grid: Control = $UI._reference.get_node("CodexScroll/CardGrid")
			var card: Button = grid.find_child("Card_" + selected_id, true, false)
			_check_audit(card != null, "actual longest card mounted " + suffix)
			if card == null: continue
			for iteration in range(2):
				card.pressed.emit()
				await get_tree().process_frame
				var modal: Control = $UI._reference.get_node_or_null("CardDetails")
				_check_audit(modal != null and $UI._codex_card == selected_id, "actual detail open %s %s" % [iteration, suffix])
				if modal == null: continue
				await _take("codex_long_detail_%s_%s" % [iteration, suffix], false)
				_check_audit(modal.get_node("DetailCard").is_visible_in_tree(), "detail card visible %s %s" % [iteration, suffix])
				if iteration == 0:
					var effect_scroll: ScrollContainer = modal.get_node("CardEffectScroll")
					effect_scroll.scroll_vertical = 10000
					await _take("codex_long_detail_bottom_" + suffix, false)
					_check_audit(effect_scroll.scroll_vertical > 0 or effect_scroll.get_v_scroll_bar().max_value <= effect_scroll.get_v_scroll_bar().page, "full effect reachable " + suffix)
				modal.get_node("CloseCardDetails").pressed.emit()
				await get_tree().process_frame
				_check_audit($UI._codex_card.is_empty() and $UI._reference.get_node_or_null("CardDetails") == null, "detail closed %s %s" % [iteration, suffix])
			await _take("codex_closed_" + suffix, false)
	Palette.set_language(prior_language)
	var report := {"ok": audit_errors.is_empty(), "fixture_only": true, "source_sha": OS.get_environment("FANTASYCARD_SOURCE_SHA"), "primary_matrix_ui_sha": "14540e8e69fc00572bd5697f4a5e6802ee4bb992", "captures": captures, "screenshots": captures.size(), "checks": checks, "errors": audit_errors, "text_observations": text_observations, "limitations": "Supplement corrects an invalid GW08/cache-only detail fixture; actual production card button and close signals, no craft/upgrade transaction."}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify({"ok": report.ok, "screenshots": captures.size(), "errors": audit_errors}))
	get_tree().quit(0 if report.ok else 1)

func _wait_grid() -> void:
	for iteration in range(120):
		await get_tree().process_frame
		var grid: Control = $UI._reference.get_node("CodexScroll/CardGrid")
		if not grid._waiting_for_pool and grid.find_children("Card_*", "Button", true, false).size() > 0: return
	_check_audit(false, "visible grid mounts within 120 frames")
