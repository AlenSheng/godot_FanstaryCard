extends "res://tests/ui_style_extended.gd"

class RecordingGateway extends "res://network/gateway.gd":
	var sent: Array = []
	func new_id() -> String: return "integration-" + str(sent.size())
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload.duplicate(true), "request_id": request_id})
		return true

var target_records: Array[Dictionary] = []

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	await get_tree().create_timer(0.5).timeout
	for locale in ["zh-CN", "en"]:
		Palette.set_language(locale)
		$UI.theme = Palette.theme()
		for resolution in [Vector2i(1920, 1080), Vector2i(1280, 720), Vector2i(960, 540)]:
			get_window().size = resolution
			await get_tree().process_frame
			var suffix := "%s_%s" % [locale, resolution.x]
			# Production extended states provide full three-class passive text,
			# six damage segments, mail/comparison reopening and bounded dialogs.
			await _extended(suffix)
			_reset()
			for hero in ["Priest", "Mage", "Guardian"]:
				Game.hero_class = hero
				$UI.screen = "prep"
				await _take("integration_signature_" + hero.to_lower() + "_" + suffix)
				_check_audit($UI._reference.get_node_or_null("SignatureWeaponFrame") != null, "signature frame " + hero + suffix)
			await _target_switch(suffix)
			_reset()
			$UI.screen = "hall"
			$UI._render()
			await _confirm_reopen("integration_" + suffix)
			var settings = $UI.get_node("AudioSettings")
			for iteration in range(2):
				settings.show_settings()
				await _take("integration_settings_%s_%s" % [iteration, suffix], false)
				_check_audit(settings._popup.visible, "settings open %s %s" % [iteration, suffix])
				settings._popup.hide()
				await get_tree().process_frame
	Palette.set_language(prior_language)
	var report := {"ok": audit_errors.is_empty(), "source_sha": OS.get_environment("FANTASYCARD_SOURCE_SHA"),
		"pr13_sha": "de1157fdf490a5bce3ba888c07519fc957c46782", "ui_sha": "070c7b441ffc5dbd7253aea1dcbc9793b1fef449",
		"captures": captures, "screenshots": captures.size(), "checks": checks, "errors": audit_errors,
		"text_observations": text_observations, "target_records": target_records,
		"limitations": "New native offline integration captures, not historical UI images. Target signals/events use a recording gateway and no external game server. Native settings use Dummy audio."}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify({"ok": report.ok, "screenshots": captures.size(), "checks": checks.size(), "errors": audit_errors}))
	get_tree().quit(0 if report.ok else 1)

func _target_switch(suffix: String) -> void:
	_reset()
	var saved_gateway: Node = Game.gateway
	var recording := RecordingGateway.new()
	recording.persist_session = false
	recording.online = true
	Game.gateway = recording
	Game._pending_commands.clear()
	Game._latest_commands.clear()
	Game._pending_play.clear()
	Game._queued_command.clear()
	Game.room = _room_fixture()
	Game.room.player.phase = "Pve"
	Game.room.allowed_actions.append_array(["battle.play_cards", "battle.select_target"])
	Game.room.pve = {"battle_id": "integration-battle", "current_target_id": "fire-bat", "monsters": [
		{"monster_id": "fire-bat", "hp": 20, "maximum_hp": 20, "shield": 0, "intent_kind": "Damage", "intent_element": "Fire", "intent_value": 9},
		{"monster_id": "murk-snail", "hp": 12, "maximum_hp": 20, "shield": 3, "intent_kind": "Shield", "intent_element": "None", "intent_value": 7}]}
	Game.selected_cards = ["hand-0"]
	Game._refresh_combat_preview()
	await _take("integration_target_initial_" + suffix)
	_check_audit(not Game.combat_preview.is_empty(), "initial local preview " + suffix)
	$UI._reference.get_node("MonsterTarget_murk-snail").pressed.emit()
	await _take("integration_target_pending_" + suffix)
	_check_audit(Game._target_selection_pending() and Game.combat_preview.is_empty(), "manual target invalidates old preview " + suffix)
	Game.play_cards()
	_check_audit(recording.sent.filter(func(row): return row.kind == "battle.play_cards").is_empty(), "pending target blocks old-target play " + suffix)
	Game._latest_commands["battle.select_target"].due = 0
	Game._flush_latest_commands()
	var command: Dictionary = recording.sent.filter(func(row): return row.kind == "battle.select_target").back()
	Game._on_event("battle.target_selected", {"battle_id": "integration-battle", "target_id": "murk-snail", "_request_id": command.request_id, "_event_revision": 9})
	var snapshot: Dictionary = Game.room.duplicate(true)
	snapshot.room_revision = 9
	snapshot.pve.current_target_id = "murk-snail"
	Game._on_event("room.snapshot", snapshot)
	await _take("integration_target_confirmed_" + suffix)
	_check_audit(Game.combat_target_id() == "murk-snail" and not Game._target_selection_pending() and not Game.combat_preview.is_empty(), "snapshot confirms new target and preview " + suffix)
	_check_audit(Game.selected_cards == ["hand-0"], "target change preserves selected cards " + suffix)
	recording.recovering = true
	Game._on_connection_changed("recovering")
	await _take("integration_target_recovering_" + suffix)
	_check_audit(Game.combat_preview.is_empty() and Game.combat_wait_state().reason == "recovering", "recovery clears preview and blocks play " + suffix)
	target_records.append({"capture": suffix, "sent": recording.sent, "target_after_confirmation": Game.combat_target_id(), "selected_cards": Game.selected_cards.duplicate()})
	Game.gateway = saved_gateway
	Game._pending_commands.clear()
	Game._latest_commands.clear()
	Game._pending_play.clear()
	Game._queued_command.clear()
	Game.clear_combat_preview()
	recording.free()
