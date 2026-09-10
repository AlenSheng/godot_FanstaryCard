extends Node

var checks: Array = []
var events: Dictionary = {}
var phase_seen: Dictionary = {}
var visited: Dictionary = {}
var frame_number := 0
var record_frames := false
var frame_clock := 0.0
var output := "res://evidence/live"
var started_at: int
var last_snapshot: Dictionary = {}
var reported := false
var errors: Array = []

func _ready() -> void:
	started_at = Time.get_ticks_msec()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output + "/frames"))
	Game.gateway.persist_session = false
	Game.gateway.device_id = "godot-ui-test-" + Game.gateway.new_id()
	Game.gateway.last_sequence = 0
	Game.gateway.room_id = ""
	Game.gateway.room_revision = 0
	Game.gateway.event_received.connect(func(kind, payload): events[kind] = int(events.get(kind, 0)) + 1; _capture_event(kind, payload))
	Game.notice.connect(func(message): errors.append(message); print("INTEGRATION notice: ", message))
	_run.call_deferred()

func _process(delta: float) -> void:
	if Time.get_ticks_msec() - started_at > 390000 and not reported:
		_finish(false, "Integration timed out")
	if record_frames:
		frame_clock += delta
		if frame_clock >= 0.5:
			frame_clock = 0.0
			RenderingServer.force_draw(false)
			var frame := get_viewport().get_texture().get_image()
			frame.resize(960, 540)
			frame.save_png(output + "/frames/%04d.png" % frame_number)
			frame_number += 1

func _capture_event(kind: String, payload: Dictionary) -> void:
	if kind == "room.snapshot": last_snapshot = payload

func _check(condition: bool, name: String) -> bool:
	checks.append({"name": name, "passed": condition})
	print("INTEGRATION ", "PASS " if condition else "FAIL ", name)
	return condition

func _wait(seconds: float) -> void:
	await get_tree().create_timer(seconds).timeout

func _capture(name: String) -> void:
	await _wait(0.35)
	RenderingServer.force_draw(false)
	var frame := get_viewport().get_texture().get_image()
	frame.resize(1920, 1080, Image.INTERPOLATE_LANCZOS)
	frame.save_png(output + "/" + name + ".png")

func _run() -> void:
	await _capture("00_login")
	await Game.login("http://127.0.0.1:5080", "联调旅人-" + Game.gateway.new_id().left(12))
	if not _check(not Game.lobby.is_empty(), "real local login and bootstrap"):
		_finish(false, "Login failed")
		return
	_check(Game.lobby.decks.size() == 3 and Game.deck().cardIds.size() == 20, "three real decks, twenty cards")
	await _capture("01_hall")
	for key in ["Priest", "Guardian", "Mage"]:
		await Game.select_class(key)
		_check(Game.hero_class == key, "select class " + key)
	var ui = $UI
	for view in ["cards", "gear", "shop", "market", "prep"]:
		await ui._navigate(view)
		await _capture("02_" + view)
	_check(ui.owned.size() >= 51, "read owned card catalog")
	_check(not ui.inventory.is_empty(), "read real equipment inventory")
	_check(ui.shop.get("products", []).size() > 0, "read gold shop")
	await Game.prepare("Free", 0)
	if not _check(not Game.preparation.is_empty(), "free preparation created"):
		_finish(false, "Preparation failed")
		return
	await Game.cancel_preparation()
	_check(Game.preparation.is_empty(), "preparation cancellation releases assets")
	await Game.prepare("Free", 0)
	await _wait(0.5)
	if not _check(Game.gateway.online, "protobuf websocket connected"):
		_finish(false, "WebSocket failed")
		return
	await Game.enqueue()
	if not _check(not Game.ticket.is_empty(), "match ticket enqueued"):
		_finish(false, "Matchmaking failed")
		return
	await _capture("03_matching")
	var deadline := Time.get_ticks_msec() + 45000
	while Game.ready_prompt.is_empty() and Game.room.is_empty() and Time.get_ticks_msec() < deadline:
		await _wait(0.25)
	if not Game.ready_prompt.is_empty():
		await _capture("04_ready")
		Game.gateway.send("room.ready")
	deadline = Time.get_ticks_msec() + 18000
	while Game.room.is_empty() and Time.get_ticks_msec() < deadline: await _wait(0.25)
	if not _check(not Game.room.is_empty(), "ready confirmation enters private room"):
		_finish(false, "No room snapshot")
		return
	_check(Game.room.get("map", []).size() == 36, "6x6 public map projection")
	record_frames = true
	await _capture("05_battle")
	var next_sync := Time.get_ticks_msec() + 1500
	var reconnected := false
	deadline = Time.get_ticks_msec() + 300000
	while Time.get_ticks_msec() < deadline and Game.settlement.is_empty():
		if not Game.room.is_empty():
			var phase: String = Game.room.get("player", {}).get("phase", "")
			if not phase_seen.has(phase):
				phase_seen[phase] = true
				await _capture("phase_" + phase)
			var pve: Dictionary = Game.room.get("pve", {})
			var current_dead: bool = pve.get("monsters", []).any(func(monster): return monster.monster_id == pve.get("current_target_id") and int(monster.hp) <= 0)
			if current_dead and Game.allowed("battle.select_target"):
				for monster in pve.get("monsters", []):
					if int(monster.hp) > 0:
						Game.command("battle.select_target", {"battle_id": pve.battle_id, "target_id": monster.monster_id})
						break
			elif Game.allowed("battle.play_cards"):
				var hand: Array = Game.room.get("player", {}).get("hand", [])
				if hand.size() >= 3:
					Game.selected_cards.clear()
					for card in hand: Game.toggle_card(card.instance_id)
					Game.play_cards()
			elif Game.allowed("reward.choice.claim"):
				var options: Array = Game.room.get("reward_choice", {}).get("options", [])
				if not options.is_empty():
					Game.command("reward.choice.claim", {"option_id": options[-1].option_id})
			elif Game.allowed("action.extract"):
				Game.command("action.extract")
			elif Game.allowed("action.spring"):
				Game.command("action.spring")
			elif Game.allowed("room.move"):
				var moves: Array = Game.room.get("legal_moves", []).duplicate()
				moves.sort_custom(func(a, b): return _move_score(a) < _move_score(b))
				if not moves.is_empty():
					var move: Dictionary = moves[0]
					visited[str(move.row) + ":" + str(move.column)] = true
					Game.command("room.move", move)
		if not reconnected and events.get("battle.combo_resolved", 0) > 0:
			reconnected = true
			Game.gateway.socket.close()
			await _wait(2.0)
		if Time.get_ticks_msec() >= next_sync:
			Game.gateway.send("room.snapshot.read")
			next_sync = Time.get_ticks_msec() + 1500
		await _wait(0.4)
	record_frames = false
	_check(events.get("battle.combo_resolved", 0) > 0, "real combo resolved")
	_check(reconnected and Game.gateway.online and not Game.gateway.recovering, "disconnect and snapshot recovery")
	if not Game.settlement.is_empty():
		await _capture("06_settlement")
		_check(true, "authoritative settlement received")
		await Game.acknowledge_settlement()
		_check(Game.settlement.is_empty() and Game.room.is_empty(), "acknowledge settlement returns to lobby")
	else:
		_check(false, "authoritative settlement received")
	_finish(checks.all(func(check): return check.passed), "Live integration ended")

func _move_score(move: Dictionary) -> int:
	var layer: int = mini(mini(int(move.row), int(move.column)), mini(5 - int(move.row), 5 - int(move.column)))
	return layer * 10 + (100 if visited.has(str(move.row) + ":" + str(move.column)) else 0)

func _finish(ok: bool, message: String) -> void:
	if reported: return
	reported = true
	var file := FileAccess.open(output + "/report.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"ok": ok, "message": message, "checks": checks, "events": events, "phases": phase_seen.keys(), "errors": errors, "last_snapshot": last_snapshot, "frames": frame_number, "elapsed_ms": Time.get_ticks_msec() - started_at}, "\t"))
	file.close()
	print("INTEGRATION COMPLETE ", ok)
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	get_tree().quit(0 if ok else 1)
