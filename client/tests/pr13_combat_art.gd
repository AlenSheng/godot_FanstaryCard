extends "res://tests/art_preview.gd"

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	Game.gateway.socket.close()
	Game.configuration_error = ""
	Game.busy = false
	for resolution in [Vector2i(1920, 1080), Vector2i(1280, 720)]:
		get_window().size = resolution
		var suffix := "_%s" % resolution.x
		Game.room = {"room_id": "pr13-art", "allowed_actions": ["battle.play_cards", "battle.select_target"],
			"player": {"player_id": "preview-player", "hero_class": "Guardian", "phase": "Pve", "weapon_level": 2,
				"combat": {"hp": 98, "maximum_hp": 100, "shield": 48}, "draw_charge": "0.55", "hand": [],
				"battle_status": {"bonuses": []}},
			"pve": {"battle_id": "preview", "current_target_id": "metal-guard", "monsters": [
				{"monster_id": "metal-guard", "hp": 24, "maximum_hp": 200, "shield": 8, "intent_kind": "Shield", "intent_element": "None", "intent_value": 12}]}}
		for id in ["C01", "C06", "C09", "C15", "GUA-06"]: Game.room.player.hand.append({"instance_id": id, "card_id": id})
		Game.selected_cards = ["C01", "C06", "C09", "C15", "GUA-06"]
		Game.combat_preview = Game._calculate_combat_preview(Game.selected_cards)
		await _capture("preview_caps" + suffix)
		var panel: Control = $UI._reference.get_node_or_null("CombatPreview")
		if panel == null: layout_errors.append("Missing preview panel")
		# Include the maximum segment count and simultaneous recovery in layout QA.
		Game.combat_preview.damage_segments = []
		for kind in ["Fire", "Water", "Wood", "Earth", "Metal", "Direct"]:
			Game.combat_preview.damage_segments.append({"kind": kind, "amount": 19})
		Game.combat_preview.heal = 9
		Game.combat_preview.shield_gain = 8
		await _capture("preview_six_segments" + suffix)
		for label in $UI._reference.find_children("*", "Label", true, false):
			if label.position.y == 578 and label.position.x >= 460 and label.position.x + label.size.x > 1840:
				layout_errors.append("Preview label outside panel: " + label.text)
		Game.selected_cards = []
		Game.combat_preview = {}
		for reason in ["drawing", "draw_blocked", "stunned", "recovering", "full_hand"]:
			Game.gateway.recovering = reason == "recovering"
			Game.room.player.stun_remaining_ms = 1800 if reason == "stunned" else 0
			Game.room.player.draw_block_remaining_ms = 2200 if reason == "draw_blocked" else 0
			Game.room.player.hand = [] if reason != "full_hand" else [{"instance_id": "1", "card_id": "C01"}, {"instance_id": "2", "card_id": "C02"}, {"instance_id": "3", "card_id": "C03"}, {"instance_id": "4", "card_id": "C04"}, {"instance_id": "5", "card_id": "C05"}]
			await _capture("wait_" + reason + suffix)
			var label: Label = $UI._reference.get_node_or_null("CombatWaitReason")
			if label == null or label.text.is_empty(): layout_errors.append("Missing wait reason: " + reason)
		Game.gateway.recovering = false
	var result := {"ok": layout_errors.is_empty(), "screenshots": screenshot_count, "errors": layout_errors, "kind": "real_renderer_synthetic_ui_fixtures"}
	var file := FileAccess.open(output + "/report.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(result, "  "))
	print(JSON.stringify(result))
	get_tree().quit(0 if result.ok else 1)
