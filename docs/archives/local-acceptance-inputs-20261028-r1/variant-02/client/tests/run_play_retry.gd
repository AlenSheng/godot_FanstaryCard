extends SceneTree

func _initialize() -> void:
	var ok := true
	for test in ["test_protobuf", "test_play_retry", "test_rejected_command_state", "test_ack_entry_observation", "test_confirmation_snapshot", "test_pending_timeout_recovery", "test_pending_timeout_wire", "test_room_store", "test_audio_events", "test_session_platform", "test_class_selection", "test_account_cache", "test_preparation_return", "test_settlement_return", "test_settlement_polling", "test_terminal_room_actions", "test_terminal_command_context", "test_art", "test_item_visual", "test_equipment_name", "test_equipment_compare", "test_combat_preview_state", "test_client_hot_paths", "test_combat_wait_state", "test_combat_wait_ui", "test_active_battle_observation"]:
		var result: Dictionary = await load("res://tests/" + test + ".gd").new().run_test()
		print(test, ": ", JSON.stringify(result))
		ok = ok and result.get("ok", false)
	quit(0 if ok else 1)
