extends RefCounted

const P = preload("res://ui/palette.gd")
const Fixture = preload("res://tests/test_combat_wait_state.gd")

func run_test() -> Dictionary:
	var saved := {"room": Game.room, "selected_cards": Game.selected_cards, "combat_preview": Game.combat_preview,
		"pending": Game._pending_commands, "latest": Game._latest_commands, "queued": Game._queued_command,
		"pending_play": Game._pending_play, "gateway": Game.gateway,
		"configuration_error": Game.configuration_error, "language": P.language()}
	var host = preload("res://ui/main.gd").new()
	# The command-line regression entry runs before autoload _ready. Own the
	# controlled gateway instead of depending on a live session being present.
	var test_gateway: Node = Fixture.RecordingGateway.new()
	test_gateway.persist_session = false
	Game.gateway = test_gateway
	var checks := {}
	var observations: Array = []
	Game.gateway.online = true
	Game.configuration_error = ""
	Game.selected_cards = []
	Game.combat_preview = {}
	Game._queued_command = {}
	Game._pending_play = {}
	for language in ["zh-CN", "en"]:
		P.set_language(language)
		for scenario in ["manual_target", "death_fallback", "submitted", "recovering"]:
			Game.room = Fixture.new().snapshot()
			Game.room.player.hand = []
			Game._pending_commands = {}
			Game._latest_commands = {}
			Game.gateway.recovering = false
			var expected_key := "battle_wait_drawing"
			match scenario:
				"manual_target":
					Game.command("battle.select_target", {"battle_id": "battle", "target_id": "murk-snail"})
					expected_key = "battle_wait_target_confirming"
				"death_fallback":
					Game.room.pve.monsters[0].hp = 0
					Game._sync_pve_target()
				"submitted":
					Game._pending_commands["submitted"] = {"action": "battle.play_cards", "payload": {}}
					expected_key = "battle_wait_confirming"
				"recovering":
					Game.gateway.recovering = true
					expected_key = "battle_wait_recovering"
			var view = preload("res://ui/reference_ui.gd").new()
			view.host = host
			view.theme = P.theme()
			(Engine.get_main_loop() as SceneTree).root.add_child(view)
			preload("res://ui/exploration_view.gd")._battle(view, host, Game.room)
			var label: Label = view.get_node_or_null("CombatWaitReason")
			var expected_text: String = P.localized(expected_key)
			var localized: bool = label != null and label.text == expected_text and expected_text != expected_key
			checks[language + "_" + scenario] = localized
			observations.append({"language": language, "scenario": scenario, "visible_text": label.text if label != null else "missing", "expected_key": expected_key, "passed": localized})
			view.free()
	host.free()
	Game.room = saved.room
	Game.selected_cards = saved.selected_cards
	Game.combat_preview = saved.combat_preview
	Game._pending_commands = saved.pending
	Game._latest_commands = saved.latest
	Game._queued_command = saved.queued
	Game._pending_play = saved.pending_play
	Game.gateway = saved.gateway
	test_gateway.free()
	Game.configuration_error = saved.configuration_error
	P.set_language(saved.language)
	return {"ok": not checks.values().has(false), "checks": checks, "observations": observations,
		"scope": "Actual UI component text construction in native headless Godot; no rendered-frame or full LIVE claim"}
