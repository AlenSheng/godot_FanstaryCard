extends Node

signal changed
signal notice(message: String)
signal combat_feedback(payload: Dictionary)
signal sound_requested(cue: String)
signal authentication_required(reason: String)

const Gateway = preload("res://network/gateway.gd")
const PlatformService = preload("res://platform/platform_service.gd")
const CardDetails = preload("res://ui/card_details.gd")
const CATALOG = preload("res://data/catalog.json")
var gateway: Node
var platform: Node
var authentication_reason := ""
var configuration_error := ""
var server_info: Dictionary = {}
var _client_info_socket := WebSocketPeer.new()
var _client_info_retry_at := 0
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
var _class_switch_request_active := false
var _pending_class := ""
var connection := "未连接"
var _settlement_loading := ""
var _queued_command: Dictionary = {}
var _queue_deadline: int = 0
var _sound_ready := false
var _sound_commands: Dictionary = {}
var _sound_seen: Dictionary = {}
var _sound_terminal_rooms: Dictionary = {}

func _process(_delta: float) -> void:
	_process_client_info()
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
	call_deferred("_refresh_server_info")

func _process_client_info() -> void:
	_client_info_socket.poll()
	if _client_info_socket.get_ready_state() == WebSocketPeer.STATE_OPEN:
		while _client_info_socket.get_available_packet_count() > 0:
			var message: Variant = JSON.parse_string(_client_info_socket.get_packet().get_string_from_utf8())
			if message is Dictionary:
				_apply_server_info(message)
	elif _client_info_socket.get_ready_state() == WebSocketPeer.STATE_CLOSED and Time.get_ticks_msec() >= _client_info_retry_at:
		_client_info_retry_at = Time.get_ticks_msec() + 5000
		var url := gateway.base_url.replace("https://", "wss://").replace("http://", "ws://")
		_client_info_socket = WebSocketPeer.new()
		_client_info_socket.connect_to_url(url + "/ws/v1/client-info")

func _apply_server_info(info: Dictionary) -> void:
	if info == server_info: return
	server_info = info
	if lobby.is_empty(): changed.emit()

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
		_reject_login("请输入账号名称")
		return
	address = address.strip_edges().trim_suffix("/")
	if not (address.begins_with("http://") or address.begins_with("https://")):
		_reject_login("请输入 http:// 或 https:// 服务器地址")
		return
	if not OS.is_debug_build() and not address.begins_with("https://"):
		_reject_login("正式客户端需要 HTTPS 服务器地址")
		return
	if not steam_login and not platform.local_login_enabled():
		_reject_login("本地账号仅用于开发验证，请使用 Steam 登录")
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

func _reject_login(reason: String) -> void:
	authentication_reason = reason
	connection = reason
	notice.emit(reason)
	changed.emit()

func _refresh_server_info() -> bool:
	var response: Dictionary = await gateway.request("/api/v1/client-info")
	if not response.ok or not response.data is Dictionary: return false
	_apply_server_info(response.data)
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
	if value not in ["Priest", "Mage", "Guardian"]: return
	if value == hero_class and (_pending_class.is_empty() or _pending_class == value): return
	# Update the hall immediately. Persistence happens in the background so network
	# latency never blocks portrait/card feedback.
	hero_class = value
	_pending_class = value
	changed.emit()
	if not _class_switch_request_active: _commit_class_selection()

func _commit_class_selection() -> void:
	_class_switch_request_active = true
	var needs_render := false
	while not _pending_class.is_empty():
		var value := _pending_class
		_pending_class = ""
		if lobby.is_empty() or not lobby.has("player"):
			break
		var generation: int = gateway.session_generation
		var result: Dictionary = await gateway.request("/api/v1/players/me", HTTPClient.METHOD_PUT, {"displayName": lobby.player.displayName, "selectedClass": value, "expectedVersion": lobby.player.version})
		if generation != gateway.session_generation:
			_pending_class = ""
			break
		if result.ok:
			lobby.player = result.data
			# A newer click remains visually authoritative until its own save completes.
			if _pending_class.is_empty():
				var confirmed := str(result.data.get("selectedClass", value))
				if hero_class != confirmed:
					hero_class = confirmed
					needs_render = true
		else:
			_pending_class = ""
			var confirmed := str(lobby.player.get("selectedClass", hero_class))
			if hero_class != confirmed:
				hero_class = confirmed
				needs_render = true
			break
	_class_switch_request_active = false
	if needs_render: changed.emit()

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
	combat_preview = _calculate_combat_preview(selected_cards)
	changed.emit()

func clear_combat_preview() -> void:
	combat_preview = {}
	_preview_request = {}
	_preview_deadline = 0

# Kept as a compatibility boundary for older offline tests and replay tools;
# live selection no longer calls the network preview command.
func _preview_context(ids: Array) -> Dictionary:
	var battle: Dictionary = room.get("duel", room.get("pve", {}))
	return {"room_id": room.get("room_id", ""), "battle_id": battle.get("duel_id", battle.get("battle_id", "")), "target_id": battle.get("opponent_id", battle.get("current_target_id", "")), "card_instance_ids": ids.duplicate()}

func _accept_combat_preview(payload: Dictionary) -> void:
	if _preview_request.is_empty() or payload.get("_request_id", "") != _preview_request.get("request_id", ""): return
	if Time.get_ticks_msec() >= _preview_deadline or _preview_request.get("context", {}) != _preview_context(selected_cards): return
	var revision := int(payload.get("_room_revision", -1))
	if revision < int(_preview_request.get("revision", -1)) or revision < int(room.get("room_revision", 0)): return
	combat_preview = payload.duplicate(true)
	combat_preview["source_revision"] = revision

func _status_bonuses(status: Dictionary) -> Dictionary:
	var result := {}
	for entry in status.get("bonuses", []): result[str(entry.get("key", ""))] = float(entry.get("value", 0))
	return result

func _counter(attacker: String, target: String) -> bool:
	return [["Water", "Fire"], ["Fire", "Metal"], ["Metal", "Wood"], ["Wood", "Earth"], ["Earth", "Water"]].any(func(pair): return pair[0] == attacker and pair[1] == target)

func _generated(element: String) -> String:
	return {"Wood": "Fire", "Fire": "Earth", "Earth": "Metal", "Metal": "Water", "Water": "Wood"}.get(element, "None")

func _target_resistance(element: String, battle: Dictionary) -> float:
	if battle.has("opponent_status"): return _status_bonuses(battle.opponent_status).get("resistance_" + element, 0.0)
	var monster: Dictionary = battle.get("monsters", []).filter(func(value): return value.get("monster_id", "") == battle.get("current_target_id", "")).front()
	var main := str(monster.get("intent_element", "None"))
	if main == "None": return 0.0
	var id := str(monster.get("monster_id", ""))
	if id == "annihilation-core":
		var boss_main := "Fire" if int(monster.get("boss_phase", 1)) == 1 else "Metal"
		var neighbor := "Wood" if boss_main == "Fire" else "Earth"
		if element == boss_main: return 0.35
		if element == neighbor: return 0.20
		if _counter(element, boss_main): return -0.30
		if _counter(boss_main, element): return 0.30
		return 0.0
	var elite := id in ["metal-guard", "fire-herald", "marsh-mother", "stone-guard", "thorn-guard"]
	if element == main: return 0.25 if elite else 0.15
	if elite and element == _generated(main): return 0.15
	if _counter(element, main): return -0.30
	if _counter(main, element): return 0.25
	return 0.0

func _calculate_combat_preview(ids: Array) -> Dictionary:
	if ids.is_empty() or not allowed("battle.play_cards"): return {}
	var battle: Dictionary = room.get("duel", room.get("pve", {}))
	var hand: Array = room.get("player", {}).get("hand", [])
	var cards: Array = []
	for id in ids:
		var instance: Dictionary = hand.filter(func(value): return value.get("instance_id", "") == id).front()
		if instance.is_empty(): return {}
		var definition: Dictionary = {}
		for row in CATALOG.data.tables.Cards:
			if row.id == instance.get("card_id", ""): definition = row; break
		if definition.is_empty(): return {}
		cards.append(CardDetails.with_element(CardDetails.at_level(definition, int(instance.get("level", 0))), str(instance.get("element_override", ""))))
	var status := _status_bonuses(room.get("player", {}).get("battle_status", {}))
	var elemental: Array = cards.filter(func(card): return int(card.get("elemental_damage", 0)) > 0 and str(card.get("element", "None")) != "None" and int(card.get("secondary_elemental_damage", 0)) == 0)
	var counts := {}
	for card in elemental: counts[card.element] = int(counts.get(card.element, 0)) + 1
	var core := ""
	var core_count := 0
	for element in counts:
		if int(counts[element]) > core_count: core = element; core_count = int(counts[element])
	var reveal_element: String = str({"Mage": "Fire", "Priest": "Water"}.get(room.get("player", {}).get("hero_class", ""), "Earth"))
	var reveal := cards.any(func(card): return bool(card.get("is_class_reveal", false)))
	var bases: Array = []
	for card in cards:
		var same := int(counts.get(card.get("element", "None"), 0)) - 1
		var value := float(card.get("elemental_damage", 0)) + int(card.get("same_element_bonus", 0)) * maxi(0, same - 2)
		if reveal and card.get("element", "None") == reveal_element: value = floor(value * 1.3)
		bases.append(value)
	var segments := {}
	var resonance := 1.0
	var conflict_pairs := 0
	var cancellation := 0.0
	if not core.is_empty():
		for pair in [["Wood", "Earth"], ["Earth", "Water"], ["Water", "Fire"], ["Fire", "Metal"], ["Metal", "Wood"]]:
			if pair[0] in counts and pair[1] in counts and (pair[0] == core or pair[1] == core): conflict_pairs += mini(int(counts[pair[0]]), int(counts[pair[1]]))
		var resonance_count := core_count + (1 if cards.any(func(card): return int(card.get("resonance_bonus", 0)) > 0) else 0)
		resonance = 3.5 if core_count == 5 and resonance_count > core_count else ([1.0, 1.2, 1.5, 2.0, 3.0][mini(resonance_count, 5) - 1])
		cancellation = minf(0.80, minf(0.65, 0.20 * conflict_pairs) + cards.map(func(card): return float(card.get("conflict_cancel_bonus", 0))).max()) if conflict_pairs > 0 else 0.0
		var core_base := 0.0
		for i in cards.size():
			if cards[i].get("element", "None") == core and int(cards[i].get("secondary_elemental_damage", 0)) == 0: core_base += bases[i]
		var elemental_damage: float = floor(core_base * resonance * (1.0 + float(status.get("damage_" + core, 0.0))) * (1.0 - _target_resistance(core, battle)) * (1.0 - cancellation))
		if elemental_damage > 0: segments[core] = int(elemental_damage)
	var total := int(segments.values().reduce(func(a, b): return a + b, 0))
	var direct := 0
	for i in cards.size():
		var card: Dictionary = cards[i]
		if int(card.get("secondary_elemental_damage", 0)) > 0:
			var secondary := int(card.get("secondary_elemental_damage", 0))
			if reveal and card.get("secondary_element", "None") == reveal_element: secondary = int(floor(secondary * 1.3))
			for pair in [[str(card.get("element", "None")), int(bases[i])], [str(card.get("secondary_element", "None")), secondary]]:
				var value := int(floor(pair[1] * (1.0 + status.get("damage_" + pair[0], 0.0)) * (1.0 - _target_resistance(pair[0], battle))))
				if value > 0: segments[pair[0]] = int(segments.get(pair[0], 0)) + value; total += value
		direct += int(card.get("direct_damage", 0))
		direct += int(floor((bases[i] + int(card.get("secondary_elemental_damage", 0)) + int(card.get("direct_damage", 0))) * float(status.get("piercing", 0.0))))
		direct += int(card.get("direct_damage", 0))
	if direct > 0: segments["Direct"] = direct; total += direct
	var target_shield := int((battle.get("opponent", {}) if battle.has("opponent") else battle.get("monsters", []).filter(func(value): return value.get("monster_id", "") == battle.get("current_target_id", "")).front()).get("shield", 0))
	var actual := mini(total, target_shield + int((battle.get("opponent", {}) if battle.has("opponent") else battle.get("monsters", []).filter(func(value): return value.get("monster_id", "") == battle.get("current_target_id", "")).front()).get("hp", 0)))
	var visible_segments: Array = []
	var remaining := actual
	for kind in segments:
		var amount := mini(int(segments[kind]), remaining)
		if amount > 0: visible_segments.append({"kind": kind, "amount": amount})
		remaining -= amount
	var heals := int(cards.map(func(card): return int(card.get("heal", 0))).reduce(func(a, b): return a + b, 0))
	var shields := int(cards.map(func(card): return int(card.get("shield", 0))).reduce(func(a, b): return a + b, 0))
	return {"core_element": core, "core_count": core_count, "damage": total, "damage_segments": visible_segments, "shield_damage": mini(actual, target_shield), "hp_damage": maxi(0, actual - target_shield), "heal": heals, "shield_gain": shields, "health_cost": int(cards.map(func(card): return int(card.get("health_cost", 0))).reduce(func(a, b): return a + b, 0)), "stun_seconds": str(cards.map(func(card): return float(card.get("stun_seconds", 0))).max()), "draw_block_seconds": str(cards.map(func(card): return float(card.get("draw_block_seconds", 0))).max()), "draw_charge": str(cards.map(func(card): return float(card.get("draw_charge", 0))).reduce(func(a, b): return a + b, 0)), "immediate_draw": int(cards.map(func(card): return int(card.get("immediate_draw", 0))).reduce(func(a, b): return a + b, 0)), "draw_speed_seconds": str(cards.map(func(card): return float(card.get("draw_speed_seconds", 0))).max()), "draw_speed_modifier": str(cards.map(func(card): return float(card.get("draw_speed_modifier", 0))).min()), "resonance_multiplier": str(resonance), "conflict_pair_count": conflict_pairs, "conflict_cancellation": str(cancellation)}

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
			combat_preview = _calculate_combat_preview(selected_cards)
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
		"combat.previewed", "combat.preview_rejected": pass
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
