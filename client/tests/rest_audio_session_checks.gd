extends RefCounted

class SessionGateway extends "res://network/gateway.gd":
	var responses: Array = []
	var paths: Array = []
	func request(path: String, _method: int = HTTPClient.METHOD_GET, _data: Variant = null, _quiet_statuses: Array = []) -> Dictionary:
		paths.append(path)
		var response: Dictionary = responses.pop_front() if not responses.is_empty() else {"result": {"ok": false, "status": 401, "stale_session": true}}
		await (Engine.get_main_loop() as SceneTree).process_frame
		if response.get("advance_generation", false): session_generation += 1
		return response.result

func run_test(host: Control) -> Dictionary:
	var original_gateway: Node = Game.gateway
	var original_busy: bool = Game.busy
	var original_owned: Array = host.owned
	var original_ready: bool = host._codex_ready
	var original_mutating: bool = host._codex_mutating
	var original_screen: String = host.screen
	var original_sound := {"muted": Sound.muted, "volume": Sound.volume, "persist": Sound.persist_settings}
	var fake := SessionGateway.new()
	fake.persist_session = false
	fake.online = true
	Game.gateway = fake
	host.screen = "hall"
	host.owned = [{"cardId": "C01", "craftCost": 1, "copyCount": 2, "version": 1}]
	host._codex_ready = true
	Sound.persist_settings = false
	Sound.set_muted(false)
	Sound.set_volume(0.65, false)
	Sound.stop_all()
	var checks := {"REST session test uses audible mixer": Sound.play_cue("ui_click")}
	Sound.stop_all()
	var heard: Array = []
	var listener := func(cue): heard.append(cue)
	Sound.cue_started.connect(listener)
	for action in ["card_upgrade", "deck_save", "purchase", "deck_refresh_switch"]:
		fake.paths.clear()
		fake.responses = [{"result": {"ok": false, "status": 401, "stale_session": true}}]
		if action == "deck_refresh_switch":
			fake.responses = [{"result": {"ok": true, "status": 200, "data": {}}}, {"advance_generation": true, "result": {"ok": false, "status": 401, "stale_session": true}}]
		Game.busy = false
		host._codex_mutating = false
		heard.clear()
		Sound.stop_all()
		match action:
			"card_upgrade": await host._card_action("C01", "upgrade")
			"deck_save", "deck_refresh_switch": await host._save_deck()
			"purchase": await host._mutate("/shop/purchases", HTTPClient.METHOD_POST, {"productId": "fixture", "quantity": 1})
		checks["Stale REST audio stays silent: " + action] = heard.is_empty()
		var expected: Array = ["/api/v1/cards/C01/upgrade"] if action == "card_upgrade" else (["/api/v1/shop/purchases"] if action == "purchase" else ["/api/v1/decks/" + Game.hero_class])
		if action == "deck_refresh_switch": expected.append("/api/v1/bootstrap")
		checks["Stale REST stops follow-up requests: " + action] = fake.paths == expected
	Sound.cue_started.disconnect(listener)
	Sound.stop_all()
	Game.gateway = original_gateway
	Game.busy = original_busy
	host.owned = original_owned
	host._codex_ready = original_ready
	host._codex_mutating = original_mutating
	host.screen = original_screen
	Sound.set_volume(float(original_sound.volume), false)
	Sound.set_muted(bool(original_sound.muted))
	Sound.persist_settings = bool(original_sound.persist)
	fake.free()
	host._render()
	return {"ok": not checks.values().has(false), "checks": checks, "message": "Real UI mutations suppress stale-session sounds and stop refresh chains; gateway and sound settings restored"}
