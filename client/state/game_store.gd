extends Node

signal changed
signal notice(message: String)
signal combat_feedback(payload: Dictionary)
signal sound_requested(cue: String)
signal authentication_required(reason: String)

const Gateway = preload("res://network/gateway.gd")
const PlatformService = preload("res://platform/platform_service.gd")
const CATALOG = preload("res://data/catalog.json")
var gateway: Node
var platform: Node
var authentication_reason := ""
var configuration_error := ""
var server_info: Dictionary = {}
var relic_details: Dictionary = {}
var combat_preview: Dictionary = {}
var _preview_request: Dictionary = {}
var _preview_deadline: int = 0
var lobby: Dictionary = {}
var room: Dictionary = {}
var preparation: Dictionary = {}
var ticket: Dictionary = {}
var ready_prompt: Dictionary = {}
var mail: Dictionary = {"items": [], "unreadCount": 0}
var settlement: Dictionary = {}
var hero_class := "Mage"
var selected_cards: Array = []
var busy := false
var _class_switch_cooldown_until_ms: int = 0

func _class_switch_config() -> Dictionary:
	var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://data/ui_config.json"))
	return parsed if parsed is Dictionary else {"class_switch_cooldown_seconds": 2.5, "class_switch_fast_tip": "切换太快，请稍后再试"}
var connection := "未连接"
var _settlement_loading := ""
var _queued_command: Dictionary = {}
var _queue_deadline: int = 0
var _sound_ready := false
var _sound_commands: Dictionary = {}
var _sound_seen: Dictionary = {}
var _sound_terminal_rooms: Dictionary = {}

func _process(_delta: float) -> void:
	if not combat_preview.is_empty() and Time.get_ticks_msec() >= _preview_deadline:
		combat_preview = {}
		_preview_request = {}
		changed.emit()
	if not _queued_command.is_empty() and Time.get_ticks_msec() > _queue_deadline:
		_queued_command = {}
		notice.emit("操作未发出，请在连接恢复后重试")

func _ready() -> void:
	gateway = Gateway.new()
	add_child(gateway)
	gateway.failed.connect(func(message): notice.emit(message))
	gateway.event_received.connect(_on_event)
	gateway.connection_changed.connect(_on_connection_changed)
	gateway.authentication_required.connect(_on_authentication_required)
	platform = PlatformService.new()
	add_child(platform)

func login(address: String, display_name: String) -> void:
	await _login(address, display_name, false)

func login_steam(address: String, display_name: String = "") -> void:
	await _login(address, display_name, true)

func logout() -> void:
	gateway.end_session("已退出登录")

func _clear_authenticated_state() -> void:
	lobby = {}
	room = {}
	preparation = {}
	ticket = {}
	ready_prompt = {}
	mail = {"items": [], "unreadCount": 0}
	settlement = {}
	hero_class = "Mage"
	selected_cards = []
	relic_details = {}
	clear_combat_preview()
	_queued_command = {}
	_settlement_loading = ""
	busy = false
	_sound_ready = false
	_sound_commands.clear()
	_sound_seen.clear()
	_sound_terminal_rooms.clear()

func _on_connection_changed(value: String) -> void:
	connection = value
	_sound_ready = false
	_sound_commands.clear()
	changed.emit()

func _on_authentication_required(reason: String) -> void:
	_clear_authenticated_state()
	if is_instance_valid(platform): platform.release_ticket()
	authentication_reason = reason
	connection = reason
	authentication_required.emit(reason)
	notice.emit(reason)
	changed.emit()

func _login(address: String, display_name: String, steam_login: bool) -> void:
	if busy: return
	display_name = display_name.strip_edges()
	if not steam_login and display_name.is_empty():
		notice.emit("请输入账号名称")
		return
	address = address.strip_edges().trim_suffix("/")
	if not (address.begins_with("http://") or address.begins_with("https://")):
		notice.emit("请输入 http:// 或 https:// 服务器地址")
		return
	if not OS.is_debug_build() and not address.begins_with("https://"):
		notice.emit("正式客户端需要 HTTPS 服务器地址")
		return
	if not steam_login and not platform.local_login_enabled():
		notice.emit("本地账号仅用于开发验证，请使用 Steam 登录")
		return
	if steam_login:
		var unavailable: String = platform.login_unavailable_reason()
		if not unavailable.is_empty():
			authentication_reason = unavailable
			notice.emit(unavailable)
			changed.emit()
			return
	_clear_authenticated_state()
	authentication_reason = ""
	configuration_error = ""
	server_info = {}
	gateway.begin_sign_in(address)
	var generation: int = gateway.session_generation
	busy = true
	changed.emit()
	if await _refresh_server_info():
		var capability := "identity.steam" if steam_login else "identity.local"
		if capability not in server_info.get("capabilities", []):
			authentication_reason = "此服务器未启用 Steam 登录" if steam_login else "此服务器未启用本地开发登录"
			notice.emit(authentication_reason)
		else:
			var health: Dictionary = await gateway.request("/health/ready")
			if health.ok:
				var sign_in := {"deviceId": gateway.device_id, "displayName": display_name}
				var ticket_result: Dictionary = {"ok": true}
				if steam_login:
					ticket_result = await platform.request_login_ticket()
					if ticket_result.ok: sign_in = {"ticket": ticket_result.ticket, "displayName": display_name}
				if generation != gateway.session_generation: return
				if ticket_result.ok:
					var result: Dictionary = await gateway.request("/api/v1/auth/steam" if steam_login else "/api/v1/auth/local", HTTPClient.METHOD_POST, sign_in)
					if steam_login: platform.release_ticket()
					if result.ok and result.data is Dictionary:
						if gateway.accept_session(str(result.data.get("accessToken", "")), str(result.data.get("expiresAt", "")), str(result.data.get("player", {}).get("userId", ""))):
							if not steam_login: gateway.remember_local_account(str(result.data.get("player", {}).get("displayName", "")))
							await refresh_lobby()
							if generation != gateway.session_generation: return
							if not lobby.is_empty() and configuration_error.is_empty(): gateway.connect_realtime()
						else: gateway.end_session("服务器未返回有效登录凭证，请重试")
				else:
					authentication_reason = ticket_result.error
					notice.emit(authentication_reason)
	if generation != gateway.session_generation: return
	busy = false
	changed.emit()

func _refresh_server_info() -> bool:
	var response: Dictionary = await gateway.request("/")
	if not response.ok or not response.data is Dictionary: return false
	server_info = response.data
	return validate_config(str(server_info.get("configVersion", "")), "服务器")

func validate_config(version: String, source: String) -> bool:
	if not version.is_empty() and version == str(CATALOG.data.version): return true
	configuration_error = "%s配置与客户端不一致，请更新客户端后重新登录（客户端 %s，服务器 %s）" % [source, CATALOG.data.version, version if not version.is_empty() else "未提供版本"]
	gateway.end_session(configuration_error)
	return false

func refresh_lobby() -> void:
	var generation: int = gateway.session_generation
	var result: Dictionary = await gateway.request("/api/v1/bootstrap")
	if not result.ok: return
	if not result.data is Dictionary or not validate_config(str(result.data.get("configVersion", "")), "大厅"): return
	lobby = result.data
	await refresh_mail()
	if lobby.player.get("selectedClass") != null: hero_class = lobby.player.selectedClass
	if lobby.get("unfinishedMatch") != null:
		gateway.room_id = lobby.unfinishedMatch.roomId
	elif lobby.get("unfinishedSettlement") != null:
		gateway.room_id = ""
		settlement = lobby.unfinishedSettlement
	elif room.is_empty() and ticket.is_empty():
		gateway.room_id = ""
		gateway.room_revision = 0
		var active: Dictionary = await gateway.request("/api/v1/preparations", HTTPClient.METHOD_GET, null, [404])
		if generation != gateway.session_generation: return
		if active.ok:
			if not _preparation_config_valid(active.data): return
			preparation = active.data
		elif active.status == 404: preparation = {}
	changed.emit()

func refresh_mail() -> void:
	if gateway.token.is_empty(): return
	var result: Dictionary = await gateway.request("/api/v1/mail", HTTPClient.METHOD_GET, null, [404])
	if result.ok and result.data is Dictionary:
		mail = result.data
		changed.emit()
	elif result.status == 404:
		mail = {"items": [], "unreadCount": 0}

func mark_mail_read(id: String, rerender: bool = true) -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/%s/read" % id.uri_encode(), HTTPClient.METHOD_POST, {})
	if not result.ok: return
	if rerender:
		await refresh_mail()
		return
	for index in range(mail.get("items", []).size()):
		var item: Dictionary = mail.items[index]
		if str(item.get("id", item.get("mailId", ""))) == id:
			if not bool(item.get("read", false)):
				item["read"] = true
				mail.items[index] = item
				mail.unreadCount = maxi(0, int(mail.get("unreadCount", 0)) - 1)
			break

func claim_mail(id: String) -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/%s/claim" % id.uri_encode(), HTTPClient.METHOD_POST, {})
	if result.ok:
		notice.emit("邮件附件已领取")
		await refresh_lobby()

func claim_all_mail() -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/claim-all", HTTPClient.METHOD_POST, {})
	if result.ok:
		notice.emit("邮件附件已全部领取")
		await refresh_lobby()

func mark_all_mail_read() -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/read-all", HTTPClient.METHOD_POST, {})
	if result.ok: await refresh_mail()

func delete_mail(id: String) -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/%s" % id.uri_encode(), HTTPClient.METHOD_DELETE, {})
	if result.ok:
		notice.emit("邮件已删除")
		await refresh_mail()

func delete_read_mail() -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/read", HTTPClient.METHOD_DELETE, {})
	if result.ok:
		notice.emit("已读邮件已清理")
		await refresh_mail()

func select_class(value: String) -> void:
	if busy or not room.is_empty() or not preparation.is_empty() or not ticket.is_empty(): return
	var now := Time.get_ticks_msec()
	if now < _class_switch_cooldown_until_ms:
		var config := _class_switch_config()
		notice.emit(str(config.get("class_switch_fast_tip", "切换太快，请稍后再试")))
		return
	busy = true
	var generation: int = gateway.session_generation
	var result: Dictionary = await gateway.request("/api/v1/players/me", HTTPClient.METHOD_PUT, {"displayName": lobby.player.displayName, "selectedClass": value, "expectedVersion": lobby.player.version})
	if generation != gateway.session_generation: return
	if result.ok:
		hero_class = value
		lobby.player = result.data
		_class_switch_cooldown_until_ms = Time.get_ticks_msec() + int(float(_class_switch_config().get("class_switch_cooldown_seconds", 2.5)) * 1000.0)
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
	if busy or deck().is_empty() or not configuration_error.is_empty(): return
	busy = true
	var generation: int = gateway.session_generation
	if not await _refresh_server_info():
		if generation != gateway.session_generation: return
		busy = false
		changed.emit()
		return
	var safe: Array = []
	if tier == "Advanced": safe = [27]
	if tier == "Top": safe = [33, 34, 35]
	var result: Dictionary = await gateway.request("/api/v1/preparations", HTTPClient.METHOD_POST, {
		"heroClass": hero_class, "deckVersion": deck().version, "equipmentIds": loadout().get("equipmentIds", [null, null, null, null, null]),
		"backpackTier": tier, "safeSlotIndexes": safe, "potionCount": potion_count, "difficulty": "Standard"})
	if generation != gateway.session_generation: return
	if result.ok and _preparation_config_valid(result.data): preparation = result.data
	busy = false
	changed.emit()

func enqueue() -> void:
	if busy or preparation.is_empty() or not gateway.online or not configuration_error.is_empty(): return
	busy = true
	var generation: int = gateway.session_generation
	if not await _refresh_server_info() or not _preparation_config_valid(preparation):
		if generation != gateway.session_generation: return
		busy = false
		changed.emit()
		return
	var result: Dictionary = await gateway.request("/api/v1/matches/enqueue", HTTPClient.METHOD_POST, {"preparationId": preparation.preparationId})
	if generation != gateway.session_generation: return
	if result.ok: ticket = result.data
	busy = false
	changed.emit()

func _preparation_config_valid(value: Dictionary) -> bool:
	return validate_config(str(value.get("snapshot", {}).get("configVersion", "")), "准备")

func cancel_preparation() -> void:
	if busy: return
	busy = true
	var generation: int = gateway.session_generation
	var path := "/api/v1/matches/tickets/" + str(ticket.get("ticketId", "")) if not ticket.is_empty() else "/api/v1/preparations/" + str(preparation.get("preparationId", ""))
	var result: Dictionary = await gateway.request(path, HTTPClient.METHOD_DELETE)
	if generation != gateway.session_generation: return
	if result.ok:
		ticket = {}
		preparation = {}
		await refresh_lobby()
	if generation != gateway.session_generation: return
	busy = false
	changed.emit()

func allowed(action: String) -> bool:
	var aliases := {"reward.choice.refresh": "choice.refresh", "reward.choice.claim": "choice.pick"}
	return configuration_error.is_empty() and gateway.online and not gateway.recovering and (action in room.get("allowed_actions", []) or aliases.get(action, "") in room.get("allowed_actions", []))

func command(action: String, payload: Dictionary = {}) -> bool:
	if not allowed(action) or not _queued_command.is_empty(): return false
	if action == "relic.read": return gateway.send(action, payload)
	# Room revisions advance with the 100 ms server tick. Refresh immediately
	# before submitting the user's intent, without guessing a future revision.
	_queued_command = {"action": action, "payload": payload.duplicate(true)}
	_queue_deadline = Time.get_ticks_msec() + 3000
	if not gateway.send("room.snapshot.read"):
		_queued_command = {}
		return false
	return true

func toggle_card(instance_id: String) -> void:
	if not allowed("battle.play_cards"): return
	if not room.get("player", {}).get("hand", []).any(func(card): return card.get("instance_id", "") == instance_id): return
	if instance_id in selected_cards: selected_cards.erase(instance_id)
	else: selected_cards.append(instance_id)
	sound_requested.emit("card_select")
	clear_combat_preview()
	request_combat_preview(selected_cards)
	changed.emit()

func clear_combat_preview() -> void:
	combat_preview = {}
	_preview_request = {}
	_preview_deadline = 0

func _preview_context(ids: Array) -> Dictionary:
	var battle: Dictionary = room.get("duel", room.get("pve", {}))
	return {"room_id": room.get("room_id", ""), "battle_id": battle.get("duel_id", battle.get("battle_id", "")), "target_id": battle.get("opponent_id", battle.get("current_target_id", "")), "card_instance_ids": ids.duplicate()}

func request_combat_preview(ids: Array) -> void:
	if not gateway.EVENTS.has("combat.previewed"): return
	if ids.is_empty() or not allowed("battle.play_cards"):
		clear_combat_preview()
		return
	var context := _preview_context(ids)
	if not _intent_valid("battle.play_cards", context):
		clear_combat_preview()
		return
	if _preview_request.get("context") == context and Time.get_ticks_msec() < _preview_deadline: return
	clear_combat_preview()
	var request_id: String = gateway.new_id()
	if gateway.send("room.snapshot.read"):
		_preview_request = {"request_id": request_id, "context": context, "revision": -1, "awaiting_snapshot": true}
		_preview_deadline = Time.get_ticks_msec() + 1000

func _dispatch_combat_preview() -> void:
	if _preview_request.is_empty() or not _preview_request.get("awaiting_snapshot", false): return
	if Time.get_ticks_msec() >= _preview_deadline or not allowed("battle.play_cards"):
		clear_combat_preview()
		return
	var context: Dictionary = _preview_request.context
	if context != _preview_context(selected_cards):
		clear_combat_preview()
		return
	_preview_request.revision = gateway.room_revision
	_preview_request.awaiting_snapshot = false
	if not gateway.send("combat.preview", {"battle_id": context.battle_id, "target_id": context.target_id, "card_instance_ids": context.card_instance_ids}, _preview_request.request_id): clear_combat_preview()

func _accept_combat_preview(payload: Dictionary) -> void:
	if _preview_request.is_empty() or payload.get("_request_id", "") != _preview_request.request_id: return
	if Time.get_ticks_msec() >= _preview_deadline or _preview_request.context != _preview_context(selected_cards): return
	if not allowed("battle.play_cards"): return
	var revision: int = int(payload.get("_room_revision", -1))
	if revision < int(_preview_request.revision) or revision < int(room.get("room_revision", 0)): return
	combat_preview = payload.duplicate(true)
	combat_preview["source_revision"] = revision

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

func _feedback_is_current(payload: Dictionary) -> bool:
	if gateway.recovering or payload.get("_replayed", false): return false
	var battle: Dictionary = room.get("duel", room.get("pve", {}))
	var battle_id: String = battle.get("duel_id", battle.get("battle_id", ""))
	if battle_id.is_empty() or payload.get("battle_id", "") != battle_id: return false
	var target_id: String = payload.get("target_id", "")
	if target_id.is_empty(): return false
	if target_id == room.get("player", {}).get("player_id", ""): return true
	if room.has("duel"): return target_id == battle.get("opponent_id", "")
	return battle.get("monsters", []).any(func(monster): return monster.get("monster_id", "") == target_id)

func _sound_is_live(payload: Dictionary) -> bool:
	return _sound_ready and gateway.online and not gateway.recovering and not payload.get("_replayed", false) and not room.is_empty()

func _sound_once(kind: String, payload: Dictionary) -> bool:
	var identity: String = str(payload.get("_request_id", ""))
	if identity.is_empty(): identity = str(payload.get("_sequence", 0))
	if identity == "0": return true
	var key := kind + ":" + identity
	if _sound_seen.has(key): return false
	_sound_seen[key] = true
	if _sound_seen.size() > 128: _sound_seen.erase(_sound_seen.keys()[0])
	return true

func _sound_terminal(result: String, audible: bool) -> void:
	if result not in ["Dead", "Extracted"]: return
	var room_id: String = room.get("room_id", "")
	if room_id.is_empty() or _sound_terminal_rooms.has(room_id): return
	_sound_terminal_rooms[room_id] = true
	if _sound_terminal_rooms.size() > 64: _sound_terminal_rooms.erase(_sound_terminal_rooms.keys()[0])
	if audible: sound_requested.emit("death" if result == "Dead" else "extract_success")

func _sound_snapshot(snapshot: Dictionary, payload: Dictionary) -> void:
	var same_room: bool = not room.is_empty() and room.get("room_id", "") == snapshot.get("room_id", "")
	var live := same_room and _sound_is_live(payload)
	var before_battle: Dictionary = room.get("duel", room.get("pve", {}))
	var after_battle: Dictionary = snapshot.get("duel", snapshot.get("pve", {}))
	var before_id: String = before_battle.get("duel_id", before_battle.get("battle_id", ""))
	var after_id: String = after_battle.get("duel_id", after_battle.get("battle_id", ""))
	if live and not before_id.is_empty() and before_id == after_id:
		var before_hand: Array = room.get("player", {}).get("hand", []).map(func(card): return card.get("instance_id", ""))
		if snapshot.get("player", {}).get("hand", []).any(func(card): return not str(card.get("instance_id", "")).is_empty() and card.instance_id not in before_hand):
			sound_requested.emit("card_draw")
	room = snapshot
	# A first or recovered terminal snapshot establishes a silent baseline.
	_sound_terminal(str(room.get("player", {}).get("phase", "")), live)
	_sound_ready = gateway.online and not gateway.recovering and not payload.get("_replayed", false)
	if not same_room: _sound_commands.clear()

func _sound_combat(kind: String, payload: Dictionary) -> void:
	if not _sound_is_live(payload) or not _sound_once(kind, payload): return
	if kind == "battle.combo_resolved" and payload.get("attacker_id", "") == room.get("player", {}).get("player_id", "") and not payload.get("card_instance_ids", []).is_empty():
		sound_requested.emit("card_play")
	var largest := 0
	var damage_kind := "direct"
	for segment in payload.get("damage_segments", []):
		if int(segment.get("amount", 0)) > largest:
			largest = int(segment.amount)
			damage_kind = str(segment.get("kind", "Direct")).to_lower()
	if int(payload.get("damage", 0)) > 0:
		if damage_kind not in ["direct", "fire", "water", "wood", "metal", "earth"]: damage_kind = "direct"
		sound_requested.emit("hit_" + damage_kind)
	if int(payload.get("heal", 0)) > 0: sound_requested.emit("heal")
	if int(payload.get("shield_gain", 0)) > 0: sound_requested.emit("shield")

func _sound_event(kind: String, payload: Dictionary) -> void:
	if not _sound_is_live(payload): return
	var request_id: String = payload.get("_request_id", "")
	var command_info: Dictionary = _sound_commands.get(request_id, {})
	var command_action: String = command_info.get("action", "") if command_info.get("room_id", "") == room.get("room_id", "") else ""
	var expected := {"reward.choice_claimed": "reward.choice.claim", "reward.choice.claimed": "reward.choice.claim", "relic.taken": "relic.take", "relic.replaced": "relic.replace", "action.potion_used": "action.potion", "room.moved": "room.move", "action.extract_started": "action.extract"}
	if expected.has(kind) or kind == "inventory.changed":
		var action: String = payload.get("action", "") if kind == "inventory.changed" else expected[kind]
		if action.is_empty() or command_action != action: return
		_sound_commands.erase(request_id)
		if not _sound_once(kind, payload): return
		match kind:
			"reward.choice_claimed", "reward.choice.claimed", "relic.taken", "relic.replaced": sound_requested.emit("reward")
			"action.potion_used": sound_requested.emit("potion")
			"room.moved": sound_requested.emit("move")
			"action.extract_started": sound_requested.emit("extract_start")
			"inventory.changed":
				if action in ["inventory.equip", "inventory.unequip"]: sound_requested.emit("equip")
		return
	if kind == "error.command_rejected":
		if not command_action.is_empty():
			_sound_commands.erase(request_id)
			sound_requested.emit("error")
		return
	# Transitions have no request ID; current revision/player/match and the
	# terminal-room latch prevent stale completion and snapshot/event double audio.
	if int(payload.get("_event_revision", -1)) >= 0 and int(payload._event_revision) < int(room.get("room_revision", 0)): return
	if kind == "player.died" and payload.get("player_id", "") == room.get("player", {}).get("player_id", ""):
		var duel_id: String = payload.get("duel_id", "")
		if duel_id.is_empty() or duel_id == room.get("duel", {}).get("duel_id", ""): _sound_terminal("Dead", true)
	elif kind == "action.extract_completed" and payload.get("status", "") == "Completed":
		_sound_terminal("Extracted", true)
	elif kind in ["settlement.ready", "match.settled"] and payload.get("match_id", "") == room.get("match_id", "") and not str(payload.get("match_id", "")).is_empty():
		_sound_terminal(str(payload.get("result", "")), true)
	elif kind == "action.spring_completed" and payload.get("status", "") == "Completed" and _sound_once(kind, payload):
		sound_requested.emit("heal")

func _send_queued_command(queued: Dictionary) -> void:
	var request_id: String = gateway.new_id()
	if gateway.send(queued.action, queued.payload, request_id):
		_sound_commands[request_id] = {"action": queued.action, "room_id": room.get("room_id", "")}
		if _sound_commands.size() > 64: _sound_commands.erase(_sound_commands.keys()[0])

func _on_event(kind: String, payload: Dictionary) -> void:
	if kind == "pong": return
	if kind in ["room.snapshot", "room.started"]:
		var snapshot: Dictionary = payload.get("snapshot", {}) if kind == "room.started" else payload
		if (not gateway.token.is_empty() or snapshot.has("config_version")) and not validate_config(str(snapshot.get("config_version", "")), "房间"): return
	_sound_event(kind, payload)
	match kind:
		"room.snapshot":
			if room.get("room_id", "") != payload.get("room_id", ""): relic_details = {}
			_sound_snapshot(payload, payload)
			var hand: Array = room.get("player", {}).get("hand", []).map(func(card): return card.instance_id)
			selected_cards = selected_cards.filter(func(id): return id in hand)
			if not combat_preview.is_empty() and int(room.get("room_revision", 0)) > int(combat_preview.get("source_revision", -1)): clear_combat_preview()
			if not _preview_request.is_empty() and _preview_request.context != _preview_context(selected_cards): clear_combat_preview()
			if _preview_request.get("awaiting_snapshot", false): _dispatch_combat_preview()
			elif not selected_cards.is_empty(): request_combat_preview(selected_cards)
			ready_prompt = {}
			if not _queued_command.is_empty():
				var queued: Dictionary = _queued_command
				_queued_command = {}
				if allowed(queued.action) and _intent_valid(queued.action, queued.payload): _send_queued_command(queued)
				else: notice.emit("当前状态已改变，请重新选择操作")
		"room.started":
			clear_combat_preview()
			_sound_snapshot(payload.get("snapshot", {}), payload)
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
		"battle.combo_resolved", "combat.hit":
			if _feedback_is_current(payload):
				combat_feedback.emit(payload)
				_sound_combat(kind, payload)
			return
		"combat.previewed": _accept_combat_preview(payload)
		"combat.preview_rejected":
			if payload.get("_request_id", "") == _preview_request.get("request_id", ""): clear_combat_preview()
		"inventory.changed": gateway.send("room.snapshot.read")
		"relic.contents": relic_details[str(payload.get("pile_id", ""))] = payload
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
	var generation: int = gateway.session_generation
	var result: Dictionary = await gateway.request("/api/v1/settlements/" + id)
	if generation != gateway.session_generation: return
	if result.ok: settlement = result.data
	_settlement_loading = ""
	changed.emit()

func acknowledge_settlement() -> void:
	if settlement.is_empty() or busy: return
	busy = true
	var generation: int = gateway.session_generation
	var result: Dictionary = await gateway.request("/api/v1/settlements/" + settlement.settlementId + "/acknowledge", HTTPClient.METHOD_POST, {})
	if generation != gateway.session_generation: return
	if result.ok:
		settlement = {}
		room = {}
		relic_details = {}
		clear_combat_preview()
		preparation = {}
		ticket = {}
		gateway.room_id = ""
		gateway.room_revision = 0
		await refresh_lobby()
	if generation != gateway.session_generation: return
	busy = false
	changed.emit()
