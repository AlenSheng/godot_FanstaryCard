extends SceneTree

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	OS.set_environment("FANTASYCARD_SERVER_URL","http://127.0.0.1:1")
	var game = root.get_node("Game")
	game.set_process(false)
	game.gateway.end_session("",false)
	game.gateway.base_url = "http://127.0.0.1:1"
	var sound = root.get_node("Sound")
	sound.set_process(false)
	sound.set_music_context("")
	sound.stop_all()
	sound.stop_music()
	var ok := true
	for test in ["test_protobuf", "test_play_retry", "test_rejected_command_state", "test_ack_entry_observation", "test_confirmation_snapshot", "test_pending_timeout_recovery", "test_pending_timeout_wire", "test_room_store", "test_audio_events", "test_session_platform", "test_class_selection", "test_account_cache", "test_preparation_return", "test_settlement_return", "test_settlement_polling", "test_terminal_room_actions", "test_terminal_command_context", "test_art", "test_item_visual", "test_equipment_name", "test_equipment_compare", "test_combat_preview_state", "test_client_hot_paths", "test_combat_wait_state", "test_combat_wait_ui", "test_active_battle_observation", "test_command_state_hand_trace","test_command_state_observation","test_ready_pending_confirmation"]:
		var suite = load("res://tests/" + test + ".gd").new()
		var result: Dictionary = await suite.run_test()
		suite = null
		print(test, ": ", JSON.stringify(result))
		ok = ok and result.get("ok", false)
		await process_frame
	sound.stop_all()
	sound.stop_music()
	await create_timer(.35).timeout
	quit(0 if ok else 1)
