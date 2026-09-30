extends "res://tests/ui_pr13_integration.gd"

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	for locale in ["zh-CN", "en"]:
		Palette.set_language(locale)
		$UI.theme = Palette.theme()
		for resolution in [Vector2i(1280, 720), Vector2i(960, 540)]:
			get_window().size = resolution
			await get_tree().process_frame
			var suffix := "%s_%s" % [locale, resolution.x]
			await _target_switch(suffix)
			_reset()
			$UI.screen = "hall"
			$UI._render()
			await _confirm_reopen("final_" + suffix)
			_reset()
			for hero in ["Priest", "Mage", "Guardian"]:
				Game.hero_class = hero
				$UI.screen = "prep"
				await _take("final_signature_" + hero.to_lower() + "_" + suffix)
				_check_audit($UI._reference.get_node_or_null("SignatureWeaponFrame") != null, "signature frame " + hero + suffix)
			await _full_passives(suffix)
	Palette.set_language(prior_language)
	var report := {"ok": audit_errors.is_empty(), "source_sha": OS.get_environment("FANTASYCARD_SOURCE_SHA"),
		"pr13_sha": "f812879e4518fd09bf22656451cb563d62940298", "ui_sha": "d76d7165c915c94732ca7087af4e22876afc76e5",
		"captures": captures, "screenshots": captures.size(), "checks": checks, "errors": audit_errors,
		"text_observations": text_observations, "target_records": target_records,
		"limitations": "New native local-state render of the final fixed inputs. Target click/snapshot/recovery uses a recording Gateway. Full passive bodies and six-segment layout are fixture data, not live gameplay or pressure acceptance. Real READY/STOP/ACK/HTTP proofs are reported separately."}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify({"ok": report.ok, "screenshots": captures.size(), "checks": checks.size(), "errors": audit_errors}))
	get_tree().quit(0 if report.ok else 1)

func _full_passives(suffix: String) -> void:
	for hero in ["Priest", "Mage", "Guardian"]:
		Game.room = _room_fixture()
		Game.room.player.hero_class = hero
		Game.room.player.phase = "Pve"
		Game.room.player.battle_status = _status_fixture({"Priest": "LinYuan", "Mage": "FenXian", "Guardian": "ZaiYue"}[hero])
		Game.room.player.battle_status.combo = 5
		Game.room.player.battle_status.charge_level = 5
		Game.room.player.battle_status.bonuses.append_array([{"key": "passive_heal", "value": "0.36"}, {"key": "passive_control", "value": "0.27"}])
		Game.room.allowed_actions += ["battle.play_cards", "battle.select_target"]
		Game.room.player.hand = []
		Game.selected_cards = []
		for id in ["C01", "C06", "C09", "C15", {"Priest": "PRI-06", "Mage": "MAG-06", "Guardian": "GUA-06"}[hero]]:
			Game.room.player.hand.append({"instance_id": id, "card_id": id})
			Game.selected_cards.append(id)
		Game.room.pve = {"battle_id": "full-passive-preview", "current_target_id": "metal-guard", "monsters": [{"monster_id": "metal-guard", "hp": 24, "maximum_hp": 200, "shield": 8, "intent_kind": "Shield", "intent_element": "None", "intent_value": 12}]}
		Game.combat_preview = Game._calculate_combat_preview(Game.selected_cards)
		Game.combat_preview.damage_segments = []
		for kind in ["Fire", "Water", "Wood", "Earth", "Metal", "Direct"]: Game.combat_preview.damage_segments.append({"kind": kind, "amount": 19})
		Game.combat_preview.heal = 9
		Game.combat_preview.shield_gain = 8
		await _take("passive_six_" + hero.to_lower() + "_" + suffix)
		if OS.get_environment("FANTASYCARD_UI_ASSERT_FIXES") == "1":
			var passive_panel: Control = $UI._reference.get_node("PlayerPassive_" + hero)
			var preview_panel: Control = $UI._reference.get_node("CombatPreview")
			_check_audit(not passive_panel.get_global_rect().intersects(preview_panel.get_global_rect()), "passive_preview_separate_" + hero + "_" + suffix)
			for node_name in ["PlayerPassivePrefix", "PlayerPassiveTitle", "PlayerPassiveDescription"]:
				var label: Label = $UI._reference.get_node(node_name)
				_check_audit(not label.text.is_empty() and label.get_line_count() == label.get_visible_line_count() and label.get_theme_font_size("font_size") >= 16 and passive_panel.get_global_rect().encloses(label.get_global_rect()), node_name + "_" + hero + "_" + suffix)
