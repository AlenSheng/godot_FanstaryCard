extends "res://tests/art_preview.gd"

const Fixture = preload("res://tests/test_combat_wait_state.gd")
const P = preload("res://ui/palette.gd")
var observations: Array = []
var frame_errors: Array = []

func reset_battle() -> void:
	Game.room = Fixture.new().snapshot()
	Game.room["match_id"] = "wait-match"
	Game.room["config_version"] = Game.CATALOG.data.version
	Game.selected_cards = ["card"]
	Game.clear_combat_preview()
	Game._pending_commands = {}
	Game._latest_commands = {}
	Game._pending_play = {}
	Game._queued_command = {}
	Game.gateway.online = true
	Game.gateway.recovering = false
	Game.configuration_error = ""
	Game.busy = false
	Game.ready_prompt = {}
	Game.settlement = {}

func present() -> void:
	$UI._render()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	Game.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway: Node = Fixture.RecordingGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	var old_language: String = P.language()
	get_window().mode = Window.MODE_WINDOWED
	for language in ["zh-CN", "en"]:
		P.set_language(language)
		for resolution in [Vector2i(1920,1080), Vector2i(1280,720), Vector2i(960,540)]:
			get_window().size = resolution
			for scenario in ["manual_queued", "manual_inflight", "fallback_queued", "fallback_inflight", "unrelated_read", "play_submitted", "stunned", "recovering"]:
				reset_battle()
				gateway.sent = []
				var expected_reason := "available"
				var expected_legal := true
				match scenario:
					"manual_queued", "manual_inflight":
						Game.command("battle.select_target", {"battle_id":"battle", "target_id":"murk-snail"})
						expected_reason = "target_confirming"
						expected_legal = false
						if scenario == "manual_inflight":
							Game._latest_commands["battle.select_target"].due = 0
							Game._flush_latest_commands()
					"fallback_queued", "fallback_inflight":
						Game.room.pve.monsters[0].hp = 0
						Game._sync_pve_target()
						if scenario == "fallback_inflight":
							Game._latest_commands["battle.select_target"].due = 0
							Game._flush_latest_commands()
					"unrelated_read": Game._pending_commands["read"] = {"action":"relic.read", "payload":{}}
					"play_submitted":
						Game.play_cards()
						expected_reason = "confirming"
						expected_legal = false
					"stunned":
						Game.room.player["stun_remaining_ms"] = 1500
						Game.room.allowed_actions.erase("battle.play_cards")
						expected_reason = "stunned"
						expected_legal = false
					"recovering":
						gateway.recovering = true
						expected_reason = "recovering"
						expected_legal = false
				await present()
				var waiting: Dictionary = Game.combat_wait_state()
				var label: Label = $UI._reference.get_node_or_null("CombatWaitReason")
				var play: Button = $UI._reference.get_node_or_null("PlayCardsButton")
				var bounds := get_viewport().get_visible_rect()
				var expected_text: String = P.localized("battle_wait_" + expected_reason) if expected_reason != "available" else ""
				var label_ok: bool = label == null if expected_reason == "available" else label != null and label.text == expected_text and label.is_visible_in_tree() and label.get_visible_line_count() > 0 and bounds.encloses(label.get_global_rect())
				var play_ok: bool = play != null and play.is_visible_in_tree() and bounds.encloses(play.get_global_rect()) and play.disabled != expected_legal
				var actual_size := get_window().size
				# Image dimensions describe the actual sampled pixels. Under canvas
				# stretching ViewportTexture's reported size can differ from them.
				var frame_image := get_viewport().get_texture().get_image()
				var pixel_size := frame_image.get_size()
				var resolution_ok: bool = actual_size == resolution and pixel_size == resolution
				var ok: bool = label_ok and play_ok and resolution_ok and waiting.reason == expected_reason and waiting.legal_opportunity == expected_legal
				var screenshot := ""
				if language == "en" and resolution.x == 960:
					screenshot = scenario + "_en_960.png"
					var error := frame_image.save_png(output + "/" + screenshot)
					if error != OK:
						ok = false
						frame_errors.append({"scenario":scenario, "screenshot_error":error})
				observations.append({"language":language, "resolution":[resolution.x,resolution.y], "scenario":scenario,
					"actual_window_size":[actual_size.x,actual_size.y], "actual_pixel_size":[pixel_size.x,pixel_size.y], "resolution_matches":resolution_ok,
					"expected_reason":expected_reason, "waiting":waiting, "actual_text":label.text if label != null else "",
					"label_visible_and_inside_viewport":label_ok, "play_button_matches_existing_permission":play_ok,
					"frame_number":Engine.get_frames_drawn(), "screenshot":screenshot, "passed":ok})
				if not ok: frame_errors.append(observations.back())
	P.set_language(old_language)
	Game.gateway = old_gateway
	gateway.free()
	var driver := DisplayServer.get_name()
	var result := {"ok":observations.size() == 48 and frame_errors.is_empty() and driver != "headless",
		"observations":observations, "errors":frame_errors, "display_driver":driver,
		"adapter":RenderingServer.get_video_adapter_name(), "frames_drawn":Engine.get_frames_drawn(),
		"scope":"Actual rendered UI frames with controlled gateway and authority fixtures; software GPU is allowed and reported; no LIVE, human, capacity or FPS performance claim"}
	FileAccess.open(output + "/native-result.json", FileAccess.WRITE).store_string(JSON.stringify(result))
	print(JSON.stringify({"ok":result.ok, "observations":observations.size(), "failed":frame_errors.size(), "display_driver":driver}))
	get_tree().quit(0 if result.ok else 1)
