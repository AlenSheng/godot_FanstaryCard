extends Node

## Headless cloud load-test client.
## Each process owns one isolated local-development account and exercises the
## same REST/WebSocket paths as the client store without rendering the UI.

var base_url := "https://www.relicbound.cn"
var client_id := "probe"
var group_id := 1
var report_path := ""
var stop_file := ""
var started_at_ms := 0
var last_status_at_ms := 0
var stop_requested := false
var finishing := false
var finished := false
var checks: Array = []
var operations: Array = []
var telemetry: Array = []
var events: Dictionary = {}
var errors: Array = []
var listed_ids: Array = []
var own_user_id := ""
var scenario_started := false
var scenario_finished := false
var Game: Node
var legacy_attempted := false

func _ready() -> void:
	Game = get_node("/root/Game")
	base_url = OS.get_environment("FANTASYCARD_SERVER_URL").strip_edges().trim_suffix("/")
	if base_url.is_empty(): base_url = "https://www.relicbound.cn"
	client_id = OS.get_environment("FANTASYCARD_LOAD_CLIENT_ID").strip_edges()
	if client_id.is_empty(): client_id = "probe"
	group_id = int(OS.get_environment("FANTASYCARD_LOAD_GROUP"))
	if group_id <= 0: group_id = 1
	report_path = OS.get_environment("FANTASYCARD_LOAD_REPORT").strip_edges()
	stop_file = OS.get_environment("FANTASYCARD_LOAD_STOP_FILE").strip_edges()
	if report_path.is_empty(): report_path = ProjectSettings.globalize_path("res://evidence/cloud-load/%s.json" % client_id)
	started_at_ms = Time.get_ticks_msec()
	DirAccess.make_dir_recursive_absolute(report_path.get_base_dir())
	Game.gateway.persist_session = false
	Game.gateway.device_id = "load-%s-%s" % [client_id, Game.gateway.new_id()]
	Game.gateway.last_sequence = 0
	Game.gateway.room_id = ""
	Game.gateway.room_revision = 0
	Game.notice.connect(_on_notice)
	Game.gateway.failed.connect(_on_notice)
	Game.gateway.event_received.connect(_on_event)
	Game.network_telemetry.connect(_on_telemetry)
	call_deferred("_run")

func _process(_delta: float) -> void:
	if not stop_requested and not stop_file.is_empty() and FileAccess.file_exists(stop_file):
		stop_requested = true
	if Time.get_ticks_msec() - last_status_at_ms >= 5000:
		last_status_at_ms = Time.get_ticks_msec()
		_write_status()

func _run() -> void:
	await _login()
	if not _check(not Game.lobby.is_empty(), "login_and_bootstrap"):
		await _finish(false, "Login or bootstrap failed")
		return
	own_user_id = str(Game.lobby.get("player", {}).get("userId", ""))
	await _shop_and_market_reads("initial")
	if not stop_requested:
		scenario_started = true
		await _run_expedition()
		await _economy_actions("post_expedition")
		scenario_finished = true
	while not stop_requested:
		await _shop_and_market_reads("steady_state")
		await _try_market_purchase()
		await _wait(15.0)
	await _graceful_cleanup()
	await _finish(true, "Stopped by load-test coordinator")

func _login() -> void:
	var account_name: String = ("L" + client_id + Game.gateway.new_id().left(4)).left(20)
	await Game.login(base_url, account_name)
	# The deployed cloud currently returns 404 for the short-lived ticket route.
	# Let that request finish before attempting the legacy development handshake.
	if not Game.gateway.online and not Game.gateway.token.is_empty(): await _wait(3.0)
	var deadline := Time.get_ticks_msec() + 30000
	while Time.get_ticks_msec() < deadline and (Game.lobby.is_empty() or not Game.gateway.online) and not stop_requested:
		if not Game.gateway.online and not Game.gateway.token.is_empty() and not legacy_attempted:
			_connect_legacy_realtime()
		await _wait(0.25)
	_check(Game.gateway.online, "realtime_connected")

func _connect_legacy_realtime() -> void:
	legacy_attempted = true
	errors.append({"at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0), "message": "legacy_ws_attempt"})
	Game.gateway.reconnect_enabled = true
	Game.gateway.online = false
	Game.gateway.recovering = false
	Game.gateway.socket.close()
	Game.gateway.socket = WebSocketPeer.new()
	Game.gateway.socket.inbound_buffer_size = 65536
	Game.gateway.socket.outbound_buffer_size = 32768
	var url: String = base_url.replace("https://", "wss://").replace("http://", "ws://")
	var result: Error = Game.gateway.socket.connect_to_url(url + "/ws/v1/session?access_token=" + str(Game.gateway.token).uri_encode())
	if result != OK: errors.append({"at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0), "message": "legacy_ws_connect_error=" + str(result)})

func _shop_and_market_reads(label: String) -> void:
	await _rest(label + ":shop_context", "/api/v1/shop/context")
	await _rest(label + ":market_context", "/api/v1/market/context")
	await _rest(label + ":inventory", "/api/v1/inventory")

func _economy_actions(label: String) -> void:
	if Game.lobby.is_empty(): return
	var shop_result: Dictionary = await _rest(label + ":shop_context", "/api/v1/shop/context")
	if shop_result.ok and shop_result.data is Dictionary:
		var shop: Dictionary = shop_result.data.get("shop", shop_result.data)
		var gold := int(Game.lobby.get("wallet", {}).get("gold", 0))
		for product in shop.get("products", []):
			if not product is Dictionary: continue
			if bool(product.get("alreadyOwned", false)): continue
			if int(product.get("purchased", 0)) >= int(product.get("limit", 0)): continue
			if int(product.get("priceGold", 0)) > gold: continue
			var purchase: Dictionary = await _rest(label + ":shop_purchase", "/api/v1/shop/purchases", HTTPClient.METHOD_POST, {"productId": str(product.get("productId", "")), "quantity": 1})
			if purchase.ok:
				gold -= int(product.get("priceGold", 0))
			break

	var market_result: Dictionary = await _rest(label + ":market_context", "/api/v1/market/context")
	if not market_result.ok or not market_result.data is Dictionary: return
	var inventory: Dictionary = market_result.data.get("inventory", {})
	var equipment := _find_equipment(inventory.get("items", []))
	if not equipment.is_empty():
		var item_id: String = str(equipment.get("instanceId", equipment.get("itemId", "")))
		if not item_id.is_empty() and item_id not in listed_ids:
			var listed: Dictionary = await _rest(label + ":market_list", "/api/v1/market/listings", HTTPClient.METHOD_POST, {"equipmentId": item_id, "priceGold": 100})
			if listed.ok and listed.data is Dictionary:
				listed_ids.append(item_id)
				await _wait(1.0)
				var listing_id: String = str(listed.data.get("listingId", ""))
				if not listing_id.is_empty():
					await _rest(label + ":market_cancel", "/api/v1/market/listings/" + listing_id, HTTPClient.METHOD_DELETE)

func _try_market_purchase() -> void:
	var result: Dictionary = await _rest("steady_state:market_context", "/api/v1/market/context")
	if not result.ok or not result.data is Dictionary: return
	var listings: Array = result.data.get("listings", [])
	var gold := int(Game.lobby.get("wallet", {}).get("gold", 0))
	for listing in listings:
		if not listing is Dictionary: continue
		if str(listing.get("sellerId", "")) == own_user_id: continue
		if int(listing.get("priceGold", 0)) > gold: continue
		var listing_id: String = str(listing.get("listingId", ""))
		if listing_id.is_empty(): continue
		await _rest("steady_state:market_purchase", "/api/v1/market/" + listing_id + "/purchase?expectedVersion=" + str(int(listing.get("version", 1))), HTTPClient.METHOD_POST)
		break

func _run_expedition() -> void:
	await Game.prepare("Free", 0)
	if not _check(not Game.preparation.is_empty(), "create_free_preparation"): return
	await Game.enqueue()
	if not _check(not Game.ticket.is_empty(), "enqueue_match"): return
	var deadline := Time.get_ticks_msec() + 60000
	while Game.ready_prompt.is_empty() and Game.room.is_empty() and Time.get_ticks_msec() < deadline and not stop_requested:
		await _wait(0.25)
	if not Game.ready_prompt.is_empty():
		Game.gateway.send("room.ready")
	deadline = Time.get_ticks_msec() + 30000
	while Game.room.is_empty() and Time.get_ticks_msec() < deadline and not stop_requested:
		await _wait(0.25)
	if not _check(not Game.room.is_empty(), "room_started"): return
	deadline = Time.get_ticks_msec() + 240000
	var visited := {}
	while Game.settlement.is_empty() and Time.get_ticks_msec() < deadline and not stop_requested:
		if not Game.room.is_empty():
			var pve: Dictionary = Game.room.get("pve", {})
			var current_dead: bool = pve.get("monsters", []).any(func(monster): return str(monster.get("monster_id", "")) == str(pve.get("current_target_id", "")) and int(monster.get("hp", 0)) <= 0)
			if current_dead and Game.allowed("battle.select_target"):
				for monster in pve.get("monsters", []):
					if int(monster.get("hp", 0)) > 0:
						Game.command("battle.select_target", {"battle_id": pve.get("battle_id", ""), "target_id": monster.get("monster_id", "")})
						break
			elif Game.allowed("battle.play_cards"):
				var hand: Array = Game.room.get("player", {}).get("hand", [])
				if not hand.is_empty():
					Game.selected_cards.clear()
					for card in hand: Game.toggle_card(str(card.get("instance_id", "")))
					Game.play_cards()
			elif Game.allowed("reward.choice.claim"):
				var options: Array = Game.room.get("reward_choice", {}).get("options", [])
				if not options.is_empty(): Game.command("reward.choice.claim", {"option_id": options[-1].get("option_id", "")})
			elif Game.allowed("action.extract"):
				Game.command("action.extract")
			elif Game.allowed("action.spring"):
				Game.command("action.spring")
			elif Game.allowed("room.move"):
				var moves: Array = Game.room.get("legal_moves", []).duplicate()
				if not moves.is_empty():
					var move: Dictionary = moves[0]
					var move_key: String = str(move.get("row", 0)) + ":" + str(move.get("column", 0))
					visited[move_key] = true
					Game.command("room.move", move)
		await _wait(0.4)
	if Game.settlement.is_empty() and not Game.room.is_empty() and Game.allowed("action.extract"):
		Game.command("action.extract")
		await _wait(8.0)
	if not Game.settlement.is_empty():
		await Game.acknowledge_settlement()
		_check(Game.room.is_empty(), "settlement_acknowledged")

func _graceful_cleanup() -> void:
	if not Game.settlement.is_empty():
		await Game.acknowledge_settlement()
	elif not Game.room.is_empty() and Game.allowed("action.extract"):
		Game.command("action.extract")
		await _wait(5.0)
		if not Game.settlement.is_empty(): await Game.acknowledge_settlement()
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()

func _find_equipment(items: Array) -> Dictionary:
	for item in items:
		if item is Dictionary and str(item.get("kind", "")) == "Equipment": return item
	return {}

func _rest(label: String, path: String, method: int = HTTPClient.METHOD_GET, data: Variant = null) -> Dictionary:
	var started := Time.get_ticks_msec()
	var result: Dictionary = await Game.gateway.request(path, method, data)
	var entry: Dictionary = {"at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0), "label": label, "path": path, "method": method, "duration_ms": Time.get_ticks_msec() - started, "status": int(result.get("status", 0)), "ok": bool(result.get("ok", false))}
	operations.append(entry)
	if operations.size() > 200: operations.pop_front()
	return result

func _on_telemetry(sample: Dictionary) -> void:
	var copy: Dictionary = sample.duplicate(true)
	copy["at_unix_ms"] = int(Time.get_unix_time_from_system() * 1000.0)
	telemetry.append(copy)
	if telemetry.size() > 300: telemetry.pop_front()

func _on_event(kind: String, _payload: Dictionary) -> void:
	events[kind] = int(events.get(kind, 0)) + 1

func _on_notice(message: String) -> void:
	if message.is_empty(): return
	errors.append({"at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0), "message": message})
	if errors.size() > 100: errors.pop_front()

func _check(passed: bool, name: String) -> bool:
	checks.append({"name": name, "passed": passed, "at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0)})
	return passed

func _wait(seconds: float) -> void:
	await get_tree().create_timer(seconds).timeout

func _write_status() -> void:
	var status: Dictionary = {"client_id": client_id, "group": group_id, "pid": OS.get_process_id(), "started_at_unix_ms": int((Time.get_unix_time_from_system() - float(Time.get_ticks_msec() - started_at_ms) / 1000.0) * 1000.0), "now_unix_ms": int(Time.get_unix_time_from_system() * 1000.0), "online": Game.gateway.online, "socket_state": Game.gateway.socket.get_ready_state(), "room": not Game.room.is_empty(), "scenario_started": scenario_started, "scenario_finished": scenario_finished, "checks": checks, "operations": operations, "telemetry": telemetry, "events": events, "errors": errors}
	var file := FileAccess.open(report_path + ".status.json", FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(status))
		file.close()

func _finish(ok: bool, message: String) -> void:
	if finished: return
	finished = true
	var report: Dictionary = {"ok": ok, "message": message, "client_id": client_id, "group": group_id, "pid": OS.get_process_id(), "user_id": own_user_id, "started_at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0) - (Time.get_ticks_msec() - started_at_ms), "ended_at_unix_ms": int(Time.get_unix_time_from_system() * 1000.0), "elapsed_ms": Time.get_ticks_msec() - started_at_ms, "checks": checks, "operations": operations, "telemetry": telemetry, "events": events, "errors": errors}
	var file := FileAccess.open(report_path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report, "\t"))
		file.close()
	_write_status()
	get_tree().quit(0 if ok else 1)
