extends Node

signal changed
signal notice(message: String)
signal combat_feedback(payload: Dictionary)

const Gateway = preload("res://network/gateway.gd")
var gateway: Node
var lobby: Dictionary = {}
var room: Dictionary = {}
var preparation: Dictionary = {}
var ticket: Dictionary = {}
var ready_prompt: Dictionary = {}
var settlement: Dictionary = {}
var hero_class := "Mage"
var selected_cards: Array = []
var busy := false
var connection := "未连接"
var _settlement_loading := ""
var _queued_command: Dictionary = {}
var _queue_deadline: int = 0

func _process(_delta: float) -> void:
	if not _queued_command.is_empty() and Time.get_ticks_msec() > _queue_deadline:
		_queued_command = {}
		notice.emit("操作未发出，请在连接恢复后重试")

func _ready() -> void:
	gateway = Gateway.new()
	add_child(gateway)
	gateway.failed.connect(func(message): notice.emit(message))
	gateway.event_received.connect(_on_event)
	gateway.connection_changed.connect(func(value): connection = value; changed.emit())

func login(address: String, display_name: String) -> void:
	if busy: return
	if not (address.begins_with("http://") or address.begins_with("https://")):
		notice.emit("请输入 http:// 或 https:// 服务器地址")
		return
	busy = true
	changed.emit()
	gateway.base_url = address.trim_suffix("/")
	var health: Dictionary = await gateway.request("/health/ready")
	if health.ok:
		var result: Dictionary = await gateway.request("/api/v1/auth/local", HTTPClient.METHOD_POST, {"deviceId": gateway.device_id, "displayName": display_name})
		if result.ok:
			gateway.token = result.data.accessToken
			await refresh_lobby()
			if not lobby.is_empty(): gateway.connect_realtime()
	busy = false
	changed.emit()

func refresh_lobby() -> void:
	var result: Dictionary = await gateway.request("/api/v1/bootstrap")
	if not result.ok: return
	lobby = result.data
	if lobby.player.get("selectedClass") != null: hero_class = lobby.player.selectedClass
	if lobby.get("unfinishedMatch") != null:
		gateway.room_id = lobby.unfinishedMatch.roomId
	elif lobby.get("unfinishedSettlement") != null:
		settlement = lobby.unfinishedSettlement
	elif room.is_empty() and ticket.is_empty():
		var active: Dictionary = await gateway.request("/api/v1/preparations", HTTPClient.METHOD_GET, null, [404])
		if active.ok: preparation = active.data
		elif active.status == 404: preparation = {}
	changed.emit()

func select_class(value: String) -> void:
	if busy or not room.is_empty() or not preparation.is_empty() or not ticket.is_empty(): return
	busy = true
	var result: Dictionary = await gateway.request("/api/v1/players/me", HTTPClient.METHOD_PUT, {"displayName": lobby.player.displayName, "selectedClass": value, "expectedVersion": lobby.player.version})
	if result.ok:
		hero_class = value
		lobby.player = result.data
	busy = false
	changed.emit()

func deck() -> Dictionary:
	for value in lobby.get("decks", []):
		if value.heroClass == hero_class: return value
	return {}

func loadout() -> Dictionary:
	for value in lobby.get("equippedLoadouts", []):
		if value.heroClass == hero_class: return value
	return {}

func prepare(tier: String, potion_count: int) -> void:
	if busy or deck().is_empty(): return
	busy = true
	var safe: Array = []
	if tier == "Advanced": safe = [27]
	if tier == "Top": safe = [33, 34, 35]
	var result: Dictionary = await gateway.request("/api/v1/preparations", HTTPClient.METHOD_POST, {
		"heroClass": hero_class, "deckVersion": deck().version, "equipmentIds": loadout().get("equipmentIds", [null, null, null, null, null]),
		"backpackTier": tier, "safeSlotIndexes": safe, "potionCount": potion_count, "difficulty": "Standard"})
	if result.ok: preparation = result.data
	busy = false
	changed.emit()

func enqueue() -> void:
	if busy or preparation.is_empty() or not gateway.online: return
	busy = true
	var result: Dictionary = await gateway.request("/api/v1/matches/enqueue", HTTPClient.METHOD_POST, {"preparationId": preparation.preparationId})
	if result.ok: ticket = result.data
	busy = false
	changed.emit()

func cancel_preparation() -> void:
	if busy: return
	busy = true
	var path := "/api/v1/matches/tickets/" + str(ticket.get("ticketId", "")) if not ticket.is_empty() else "/api/v1/preparations/" + str(preparation.get("preparationId", ""))
	var result: Dictionary = await gateway.request(path, HTTPClient.METHOD_DELETE)
	if result.ok:
		ticket = {}
		preparation = {}
		await refresh_lobby()
	busy = false
	changed.emit()

func allowed(action: String) -> bool:
	var aliases := {"reward.choice.refresh": "choice.refresh", "reward.choice.claim": "choice.pick"}
	return gateway.online and not gateway.recovering and (action in room.get("allowed_actions", []) or aliases.get(action, "") in room.get("allowed_actions", []))

func command(action: String, payload: Dictionary = {}) -> bool:
	if not allowed(action) or not _queued_command.is_empty(): return false
	# Room revisions advance with the 100 ms server tick. Refresh immediately
	# before submitting the user's intent, without guessing a future revision.
	_queued_command = {"action": action, "payload": payload.duplicate(true)}
	_queue_deadline = Time.get_ticks_msec() + 3000
	if not gateway.send("room.snapshot.read"):
		_queued_command = {}
		return false
	return true

func toggle_card(instance_id: String) -> void:
	if instance_id in selected_cards: selected_cards.erase(instance_id)
	else: selected_cards.append(instance_id)
	changed.emit()

func play_cards() -> void:
	if selected_cards.is_empty(): return
	var battle: Dictionary = room.get("duel", room.get("pve", {}))
	if not target_alive(battle.get("opponent_id", battle.get("current_target_id", ""))):
		notice.emit("请先选择存活目标")
		return
	var payload := {"battle_id": battle.get("duel_id", battle.get("battle_id", "")), "target_id": battle.get("opponent_id", battle.get("current_target_id", "")), "card_instance_ids": selected_cards.duplicate()}
	command("battle.play_cards", payload)

func target_alive(target_id: String) -> bool:
	if room.has("duel"):
		return not target_id.is_empty() and target_id == room.duel.get("opponent_id", "")
	return room.get("pve", {}).get("monsters", []).any(func(monster): return monster.get("monster_id", "") == target_id and int(monster.get("hp", 0)) > 0)

func _on_event(kind: String, payload: Dictionary) -> void:
	if kind == "pong": return
	match kind:
		"room.snapshot":
			room = payload
			var hand: Array = room.get("player", {}).get("hand", []).map(func(card): return card.instance_id)
			selected_cards = selected_cards.filter(func(id): return id in hand)
			ready_prompt = {}
			if not _queued_command.is_empty():
				var queued: Dictionary = _queued_command
				_queued_command = {}
				if allowed(queued.action) and _intent_valid(queued.action, queued.payload): gateway.send(queued.action, queued.payload)
				else: notice.emit("当前状态已改变，请重新选择操作")
		"room.started":
			room = payload.get("snapshot", {})
			ready_prompt = {}
			gateway.room_id = payload.room_id
			gateway.room_revision = room.get("room_revision", 0)
			gateway.send("room.snapshot.read")
		"match.found", "room.ready_required", "room.ready_accepted": ready_prompt = payload
		"room.ready_removed":
			ready_prompt = {}
			ticket = {}
			preparation = {}
			notice.emit("确认超时，席位已释放")
		"settlement.ready", "match.settled": _load_settlement(payload.settlement_id)
		"battle.combo_resolved": combat_feedback.emit(payload)
	changed.emit()

func _intent_valid(action: String, payload: Dictionary) -> bool:
	if action == "battle.play_cards":
		var battle: Dictionary = room.get("duel", room.get("pve", {}))
		if payload.get("battle_id") != battle.get("duel_id", battle.get("battle_id", "")): return false
		if not target_alive(payload.get("target_id", "")): return false
		var ids: Array = room.get("player", {}).get("hand", []).map(func(card): return card.instance_id)
		var cards: Array = payload.get("card_instance_ids", [])
		return not cards.is_empty() and cards.all(func(id): return id in ids)
	if action == "battle.select_target":
		return payload.get("battle_id") == room.get("pve", {}).get("battle_id", "") and target_alive(payload.get("target_id", ""))
	if action == "reward.choice.claim":
		return room.get("reward_choice", {}).get("options", []).any(func(option): return option.option_id == payload.get("option_id"))
	return true

func _load_settlement(id: String) -> void:
	if settlement.get("settlementId", "") == id or _settlement_loading == id: return
	_settlement_loading = id
	var result: Dictionary = await gateway.request("/api/v1/settlements/" + id)
	if result.ok: settlement = result.data
	_settlement_loading = ""
	changed.emit()

func acknowledge_settlement() -> void:
	if settlement.is_empty() or busy: return
	busy = true
	var result: Dictionary = await gateway.request("/api/v1/settlements/" + settlement.settlementId + "/acknowledge", HTTPClient.METHOD_POST, {})
	if result.ok:
		settlement = {}
		room = {}
		preparation = {}
		ticket = {}
		gateway.room_id = ""
		gateway.room_revision = 0
		await refresh_lobby()
	busy = false
	changed.emit()
