extends RefCounted

const Targets = preload("res://state/battle_targets.gd")

class TargetGateway extends "res://network/gateway.gd":
	var sent: Array = []
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload.duplicate(true), "request_id": request_id})
		return true

func _snapshot() -> Dictionary:
	return {"room_id": "room", "room_revision": 1, "allowed_actions": ["battle.play_cards", "battle.select_target"],
		"player": {"player_id": "player", "hero_class": "Mage", "phase": "Pve", "combat": {"hp": 50, "maximum_hp": 70}, "hand": [{"instance_id": "card", "card_id": "C11"}], "battle_status": {}},
		"pve": {"battle_id": "battle", "current_target_id": "fire-bat", "monsters": [
			{"monster_id": "fire-bat", "hp": 20, "maximum_hp": 20, "intent_element": "Fire"},
			{"monster_id": "murk-snail", "hp": 20, "maximum_hp": 20, "intent_element": "Water"}]}}

func run_test() -> Dictionary:
	var checks := {}
	var store = load("res://state/game_store.gd").new()
	var gateway := TargetGateway.new()
	gateway.persist_session = false
	gateway.online = true
	store.gateway = gateway
	store.selected_cards = ["card"]
	store._on_event("room.snapshot", _snapshot())
	checks["Keep a living selected target"] = store.combat_target_id() == "fire-bat" and store._latest_commands.is_empty()
	var snapshot := _snapshot()
	snapshot.pve.monsters[0].hp = 0
	store._on_event("room.snapshot", snapshot)
	checks["Select the sole survivor immediately"] = store.combat_target_id() == "murk-snail" and store.selected_cards == ["card"]
	checks["Preview uses survivor HP"] = int(store.combat_preview.get("hp_damage", 0)) == 6 and store._preview_context(["card"]).target_id == "murk-snail"
	checks["Queue target synchronization"] = store._latest_commands.get("battle.select_target", {}).get("payload", {}).get("target_id", "") == "murk-snail"
	if store._latest_commands.has("battle.select_target"):
		var due: int = store._latest_commands["battle.select_target"].due
		store._on_event("room.snapshot", snapshot)
		checks["Snapshots do not postpone selection"] = store._latest_commands["battle.select_target"].due == due
		store._latest_commands["battle.select_target"].due = 0
		store._flush_latest_commands()
	store._on_event("room.snapshot", snapshot)
	checks["No duplicate synchronization while pending"] = store._latest_commands.is_empty() and gateway.sent.size() == 1
	store.play_cards()
	checks["Play targets survivor without waiting for acknowledgement"] = gateway.sent.back().kind == "battle.play_cards" and gateway.sent.back().payload.target_id == "murk-snail"
	store._latest_commands["battle.select_target"] = {"payload": {"battle_id": "battle", "target_id": "fire-bat"}, "due": 0}
	var sent_count: int = gateway.sent.size()
	store._flush_latest_commands()
	checks["Discard queued clicks on defeated enemies"] = gateway.sent.size() == sent_count and store._latest_commands.is_empty()
	snapshot.pve.monsters[1].hp = 0
	store._on_event("room.snapshot", snapshot)
	checks["No target after all monsters die"] = store.combat_target_id().is_empty() and store._latest_commands.is_empty()
	store.room = {"duel": {"opponent_id": "opponent"}}
	checks["PvP target unchanged"] = store.combat_target_id() == "opponent"
	store.free()
	gateway.free()
	_check_ui(checks)
	return {"ok": not checks.values().has(false), "checks": checks}

func _check_ui(checks: Dictionary) -> void:
	var saved_room := Game.room
	var saved_selection := Game.selected_cards
	var saved_preview := Game.combat_preview
	var saved_online: bool = Game.gateway.online
	var saved_latest: Dictionary = Game._latest_commands.duplicate(true)
	Game.gateway.online = true
	Game.selected_cards = []
	Game.combat_preview = {}
	var host = load("res://ui/main.gd").new()
	var cases := {"single": [20], "two": [20, 20], "last": [0, 20], "all_dead": [0, 0], "three": [20, 20, 20], "two_after_kill": [0, 20, 20]}
	for scenario in cases:
		Game.room = _snapshot()
		Game.room.player.hand = []
		Game.room.pve.monsters = []
		var hit_points: Array = cases[scenario]
		for i in range(hit_points.size()):
			Game.room.pve.monsters.append({"monster_id": ["fire-bat", "murk-snail", "rust-rat"][i], "hp": hit_points[i], "maximum_hp": 20, "intent_element": "Fire"})
		var view = load("res://ui/reference_ui.gd").new()
		view.host = host
		view.theme = load("res://ui/palette.gd").theme()
		(Engine.get_main_loop() as SceneTree).root.add_child(view)
		load("res://ui/exploration_view.gd")._battle(view, host, Game.room)
		var buttons: Array = view.find_children("MonsterTarget_*", "Button", true, false)
		var live_count := Targets.living(Game.room.pve).size()
		checks[scenario + " target button count"] = buttons.size() == (live_count if live_count > 1 else 0)
		for button in buttons:
			checks[scenario + " raised button " + str(button.name)] = button.position.y + button.size.y <= 562 and button.position.x + button.size.x <= 1880
			checks[scenario + " living button " + str(button.name)] = Game.target_alive(str(button.name).trim_prefix("MonsterTarget_"))
		if scenario == "two":
			view.get_node("MonsterTarget_murk-snail").pressed.emit()
			checks["Manual selection remains functional"] = Game._latest_commands.get("battle.select_target", {}).get("payload", {}).get("target_id", "") == "murk-snail"
		view.free()
	host.free()
	Game.room = saved_room
	Game.selected_cards = saved_selection
	Game.combat_preview = saved_preview
	Game.gateway.online = saved_online
	Game._latest_commands = saved_latest
