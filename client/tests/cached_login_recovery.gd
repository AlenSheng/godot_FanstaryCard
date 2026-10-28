extends SceneTree

# Explicit opt-in: this logs into the remembered account on the launcher's
# server and can replace another client. It does not play or acknowledge loot.
func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	if OS.get_environment("FANTASYCARD_TEST_CACHED_LOGIN") != "1":
		push_error("Set FANTASYCARD_TEST_CACHED_LOGIN=1 to test the remembered account.")
		quit(2)
		return
	var game = root.get_node("Game")
	game.gateway.persist_session = false
	if game.gateway.local_account_name.is_empty():
		push_error("No remembered account is available.")
		quit(2)
		return
	await game.login(game.gateway.base_url, game.gateway.local_account_name)
	var login_ok: bool = await _wait_for_recovery(game)
	print(JSON.stringify({"step": "cached_login", "ok": login_ok, "state": _state(game)}))
	await game.reconnect()
	var reconnect_ok: bool = await _wait_for_recovery(game)
	print(JSON.stringify({"step": "reconnect", "ok": reconnect_ok, "state": _state(game)}))
	quit(0 if login_ok and reconnect_ok else 1)

func _wait_for_recovery(game: Node) -> bool:
	var deadline := Time.get_ticks_msec() + 12000
	while Time.get_ticks_msec() < deadline:
		if game.gateway.online and not game.lobby.is_empty():
			if not game.room.is_empty() or not game.settlement.is_empty() or game.lobby.get("unfinishedMatch") == null:
				return true
		await create_timer(0.1).timeout
	return false

func _state(game: Node) -> Dictionary:
	return {"connected": game.gateway.online, "room_restored": not game.room.is_empty(), "settlement_restored": not game.settlement.is_empty(), "unfinished_match": game.lobby.get("unfinishedMatch") != null, "connection": game.connection}
