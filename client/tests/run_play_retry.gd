extends SceneTree

func _initialize() -> void:
	var ok := true
	for test in ["test_protobuf", "test_play_retry", "test_room_store", "test_audio_events", "test_session_platform", "test_account_cache", "test_preparation_return", "test_settlement_return", "test_settlement_polling", "test_art", "test_item_visual", "test_equipment_name", "test_equipment_compare", "test_combat_preview_state", "test_client_hot_paths"]:
		var result: Dictionary = load("res://tests/" + test + ".gd").new().run_test()
		print(test, ": ", result)
		ok = ok and result.get("ok", false)
	quit(0 if ok else 1)
