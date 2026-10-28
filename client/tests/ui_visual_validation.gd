extends Node

func _ready() -> void:
	call_deferred("_validate")

func _validate() -> void:
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	Sound.persist_settings = false
	var rows: Array = []
	var valid := DisplayServer.get_name() == "headless"
	for path in ["res://ui/card_view.gd", "res://ui/audio_settings.gd", "res://tests/test_card_view.gd", "res://tests/ui_typography_probe.gd", "res://tests/equipment_compare_preview.gd"]:
		var script: Script = load(path)
		var passed := script != null and script.can_instantiate()
		rows.append({"path": path, "compiled": passed})
		valid = valid and passed
	for path in ["res://ui/palette.gd", "res://ui/main.gd", "res://ui/reference_ui.gd", "res://ui/card_grid_view.gd", "res://ui/codex_view.gd", "res://ui/deck_builder_view.gd", "res://ui/exploration_view.gd", "res://tests/codex_preview.gd", "res://tests/deck_builder_preview.gd", "res://tests/ui_visual_review.gd"]:
		var script: Script = load(path)
		var passed := script != null and script.can_instantiate()
		rows.append({"path": path, "compiled": passed})
		valid = valid and passed
	if OS.get_environment("FANTASYCARD_REVIEW_CARD_REGRESSION") == "1":
		var regression: Dictionary = load("res://tests/test_card_view.gd").new().run_test()
		rows.append({"card_view_regression": regression})
		valid = valid and bool(regression.get("ok", false))
	var output := OS.get_environment("FANTASYCARD_ART_EVIDENCE")
	if output.is_empty():
		get_tree().quit(2)
		return
	DirAccess.make_dir_recursive_absolute(output)
	var file := FileAccess.open(output.path_join("headless-script-review.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify({"ok": valid, "mode": DisplayServer.get_name(), "scripts": rows, "actual_game_matches": 0}, "  "))
	file.close()
	load("res://ui/palette.gd").clear_runtime_fonts()
	Sound.stop_all()
	get_tree().quit(0 if valid else 1)
