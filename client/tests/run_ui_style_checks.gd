extends SceneTree

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var results: Dictionary = {}
	var successful := true
	var palette = load("res://ui/palette.gd")
	var prior_language: String = palette.language()
	for test_name in ["test_native_scripts", "test_art", "test_item_visual", "test_card_view", "test_bounded_bar", "test_bundled_fonts", "test_localization", "test_card_localization", "test_class_selection", "test_confirmation_modal", "test_tips_overlay", "test_equipment_compare", "test_card_description_levels", "ui_integration_boxspirit_instances", "test_battle_targets", "test_combat_preview_state", "test_confirmation_snapshot", "test_class_switch", "test_target_confirmation_contract"]:
		palette.set_language("zh-CN")
		var script = load("res://tests/%s.gd" % test_name)
		var result: Dictionary = await script.new().run_test()
		results[test_name] = result
		successful = successful and result.get("ok", false)
		print("%s: %s" % [test_name, result.get("ok", false)])
	palette.set_language(prior_language)
	var output := OS.get_environment("FANTASYCARD_UI_CHECKS")
	if not output.is_empty():
		FileAccess.open(output, FileAccess.WRITE).store_string(JSON.stringify({"ok": successful, "tests": results}, "  "))
	quit(0 if successful else 1)
