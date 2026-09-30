extends Node

signal changed
signal notice(message: String)
signal player_data_invalidated
signal shop_refreshed(payload: Dictionary)
signal combat_feedback(payload: Dictionary)
signal sound_requested(cue: String)
signal authentication_required(reason: String)
signal network_telemetry(sample: Dictionary)
signal cache_changed(module: String)

const Gateway = preload("res://network/gateway.gd")
const PlatformService = preload("res://platform/platform_service.gd")
const CardDetails = preload("res://ui/card_details.gd")
const CatalogIndex = preload("res://data/catalog_index.gd")
const ElementRules = preload("res://state/element_rules.gd")
const BattleTargets = preload("res://state/battle_targets.gd")
const CATALOG = preload("res://data/catalog.json")
const LATEST_WINS_ACTIONS := ["battle.select_target", "combat.preview"]
const LATEST_WINS_DEBOUNCE_MS := 80
var gateway: Node
var platform: Node
var authentication_reason := ""
var configuration_error := ""
var server_info: Dictionary = {}
var _server_info_address := ""
var _client_info_socket := WebSocketPeer.new()
var _client_info_retry_at := 0
var relic_details: Dictionary = {}
var combat_preview: Dictionary = {}
var _preview_request: Dictionary = {}
var _preview_deadline: int = 0
var lobby: Dictionary = {}
var _cache_syncing: Dictionary = {}
var _cache_sync_again: Dictionary = {}
var _cache_versions: Dictionary = {}
var _lobby_request_epoch := 0
var _shop_rotation_check_at := 0
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
var _settlement_ack_pending_id := ""
var _settlement_polling := false
var _settlement_poll_at := 0
var _settlement_recovery_match_id := ""
var settlement_query_failed := false
var _extraction_sync_at := 0
var _queued_command: Dictionary = {}
var _queue_deadline: int = 0
var _pending_play: Dictionary = {}
var _play_deadline: int = 0
var _pending_commands: Dictionary = {}
var _combat_sync_at := 0
var _latest_commands: Dictionary = {}
var _snapshot_request_at: int = 0
var _snapshot_request_pending := false
var network_rtt_ms := -1
var last_command_latency_ms := -1
var _sound_ready := false
var _sound_commands: Dictionary = {}
var _sound_seen: Dictionary = {}
var _sound_terminal_rooms: Dictionary = {}

func _process(_delta: float) -> void:
	_process_client_info()
	_check_shop_rotation()
	_flush_latest_commands()
	_flush_combat_preview()
	var now := Time.get_ticks_msec()
	if room.has("extraction_remaining_ms"):
		if _extraction_sync_at == 0:
			_extraction_sync_at = now + 1000
		elif now >= _extraction_sync_at:
			_extraction_sync_at = now + 1000
			if _snapshot_request_pending and now - _snapshot_request_at > 3000: _snapshot_request_pending = false
			_request_snapshot()
	else:
		_extraction_sync_at = 0
	var phase: String = str(room.get("player", {}).get("phase", ""))
	if phase in ["Pve", "Pvp"]:
		if _combat_sync_at == 0: _combat_sync_at = now + 4000
		elif now >= _combat_sync_at:
			_combat_sync_at = now + 4000
			# Natural draws and utility intents may have no presentation event.
			# Keep the visible hand and legal opportunities authoritative.
			if _snapshot_request_pending and now - _snapshot_request_at > 3000: _snapshot_request_pending = false
			_request_snapshot()
	else: _combat_sync_at = 0
	if settlement.is_empty() and (phase in ["Extracted", "Dead"] or not _settlement_recovery_match_id.is_empty()) and now >= _settlement_poll_at and not _settlement_polling:
		_poll_ready_settlement()
	var pending_changed := false
	if not _pending_play.is_empty() and Time.get_ticks_msec() > _play_deadline:
		_pending_play = {}
		pending_changed = true
	for request_id in _pending_commands.keys():
		if Time.get_ticks_msec() > int(_pending_commands[request_id].get("deadline", 0)):
			if _pending_commands[request_id].get("confirmed", false):
				# The write succeeded, but its new state is still missing. Restore
				# the authoritative room through reconnect rather than resend it.
				room = {}
				selected_cards.clear()
				clear_combat_preview()
				_pending_commands.clear()
				gateway.recovering = true
				gateway.connect_realtime()
				pending_changed = true
				break
			_pending_commands.erase(request_id)
			pending_changed = true
	if not _queued_command.is_empty() and Time.get_ticks_msec() > _queue_deadline:
		_queued_command = {}
		notice.emit("操作未发出，请在连接恢复后重试")
		pending_changed = true
	if pending_changed: changed.emit()

func _check_shop_rotation() -> void:
	if gateway == null or gateway.token.is_empty() or lobby.is_empty(): return
	if Time.get_ticks_msec() < _shop_rotation_check_at: return
	_shop_rotation_check_at = Time.get_ticks_msec() + 60000
	var shop: Dictionary = lobby.shop if lobby.get("shop") is Dictionary else {}
	if shop.is_empty(): return
	# The server rotates the regular shop at 04:00 China time (20:00 UTC).
	var day: Dictionary = Time.get_datetime_dict_from_unix_time(int(Time.get_unix_time_from_system()) + 4 * 3600)
	var reset_key := "%04d-%02d-%02d" % [day.year, day.month, day.day]
	if str(shop.get("resetKey", "")) != reset_key: refresh_cache("shop")

func _ready() -> void:
	gateway = Gateway.new()
	add_child(gateway)
	gateway.failed.connect(func(message): notice.emit(message))
	gateway.event_received.connect(_on_event)
	gateway.telemetry.connect(_on_gateway_telemetry)
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
		var url: String = gateway.base_url.replace("https://", "wss://").replace("http://", "ws://")
		_client_info_socket = WebSocketPeer.new()
		_client_info_socket.connect_to_url(url + "/ws/v1/client-info")

func _apply_server_info(info: Dictionary) -> void:
	if info == server_info: return
	server_info = info
	if lobby.is_empty():
		changed.emit()
	else:
		validate_config(str(info.get("configVersion", "")), "服务器")

func login(address: String, display_name: String) -> void:
	await _login(address, display_name, false)

func login_steam(address: String, display_name: String = "") -> void:
	await _login(address, display_name, true)

func logout() -> void:
	# End the local session and show the login screen in one state change.
	# The gateway has no logout request to wait for.
	gateway.end_session("", false)
	_on_authentication_required("已退出登录")

func reconnect() -> void:
	if busy: return
	# A WebSocket reconnect only works while its in-memory access token is still
	# valid. After restarting the client, restore a local development session
	# from the remembered account; cloud and Steam sessions must be re-authenticated.
	if gateway.token.is_empty() or gateway.session_expired():
		var is_local_server: bool = gateway.base_url.trim_suffix("/") == Gateway.DEFAULT_LOCAL_BASE_URL
		if OS.is_debug_build() and is_local_server and not gateway.local_account_name.is_empty():
			await _login(gateway.base_url, gateway.local_account_name, false)
		else:
			gateway.end_session("登录会话已失效，请重新登录")
		return
	busy = true
	connection = "正在恢复连接…"
	changed.emit()
	var generation: int = gateway.session_generation
	await refresh_lobby()
	if generation == gateway.session_generation and not lobby.is_empty() and configuration_error.is_empty():
		gateway.connect_realtime()
	busy = false
	changed.emit()

func _clear_authenticated_state() -> void:
	lobby = {}
	_cache_syncing.clear()
	_cache_sync_again.clear()
	_cache_versions.clear()
	_shop_rotation_check_at = 0
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
	_pending_play = {}
	_pending_commands.clear()
	_latest_commands.clear()
	_snapshot_request_pending = false
	_settlement_loading = ""
	_settlement_ack_pending_id = ""
	_settlement_polling = false
	_settlement_poll_at = 0
	_settlement_recovery_match_id = ""
	settlement_query_failed = false
	_extraction_sync_at = 0
	busy = false
	_sound_ready = false
	_sound_commands.clear()
	_sound_seen.clear()
	_sound_terminal_rooms.clear()

func _on_connection_changed(value: String) -> void:
	connection = value
	clear_combat_preview()
	_pending_play = {}
	_pending_commands.clear()
	_latest_commands.clear()
	_snapshot_request_pending = false
	if _queued_command.get("retry", false): _queued_command = {}
	_sound_ready = false
	_sound_commands.clear()
	_sound_seen.clear()
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
	gateway.begin_sign_in(address)
	var generation: int = gateway.session_generation
	busy = true
	changed.emit()
	var has_current_server_info: bool = not server_info.is_empty() and _server_info_address == gateway.base_url
	if (has_current_server_info and validate_config(str(server_info.get("configVersion", "")), "服务器")) or await _refresh_server_info():
		var capability := "identity.steam" if steam_login else "identity.local"
		if capability not in server_info.get("capabilities", []):
			authentication_reason = "此服务器未启用 Steam 登录" if steam_login else "此服务器未启用本地开发登录"
			notice.emit(authentication_reason)
		else:
			var sign_in: Dictionary = {"deviceId": gateway.device_id, "displayName": display_name}
			var ticket_result: Dictionary = {"ok": true}
			if steam_login:
				ticket_result = await platform.request_login_ticket()
				if ticket_result.ok: sign_in = {"ticket": ticket_result.ticket, "displayName": display_name}
			if generation != gateway.session_generation: return
			if ticket_result.ok:
				var result: Dictionary = await gateway.request("/api/v1/auth/steam" if steam_login else "/api/v1/auth/local", HTTPClient.METHOD_POST, sign_in)
				if steam_login: platform.release_ticket()
				if result.ok and result.data is Dictionary and result.data.get("player") is Dictionary:
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
	_server_info_address = gateway.base_url
	return validate_config(str(server_info.get("configVersion", "")), "服务器")

func validate_config(version: String, source: String) -> bool:
	if not version.is_empty() and version == str(CATALOG.data.version): return true
	configuration_error = "%s配置与客户端不一致，请更新客户端后重新登录（客户端 %s，服务器 %s）" % [source, CATALOG.data.version, version if not version.is_empty() else "未提供版本"]
	gateway.end_session(configuration_error)
	return false

func refresh_lobby() -> void:
	var generation: int = gateway.session_generation
	_lobby_request_epoch += 1
	var request_epoch := _lobby_request_epoch
	var origin_scope := _lobby_scope()
	var result: Dictionary = await gateway.request("/api/v1/bootstrap")
	if not _lobby_request_current(generation, request_epoch, origin_scope): return
	if not result.ok: return
	if not result.data is Dictionary or not validate_config(str(result.data.get("configVersion", "")), "大厅"): return
	for required in ["player", "wallet", "materials"]:
		if not result.data.get(required) is Dictionary:
			notice.emit("服务器大厅数据不完整，请重试")
			return
	if generation != gateway.session_generation: return
	var next_lobby: Dictionary = result.data.duplicate(true)
	if _settlement_ack_pending_id != "":
		next_lobby["unfinishedSettlement"] = null
		next_lobby["unfinishedMatch"] = null
	if not next_lobby.get("mail") is Dictionary:
		var mail_result: Dictionary = await gateway.request("/api/v1/mail", HTTPClient.METHOD_GET, null, [404])
		if not _lobby_request_current(generation, request_epoch, origin_scope): return
		next_lobby["mail"] = mail_result.data if mail_result.ok and mail_result.data is Dictionary else {"items": [], "unreadCount": 0}
	# Older servers omit the optional account snapshot fields. Fetch those only
	# once during login/recovery, never when a module is opened.
	if not next_lobby.get("shop") is Dictionary or not next_lobby.get("market") is Array or not next_lobby.get("inventory") is Dictionary:
		var economy: Dictionary = await gateway.request("/api/v1/economy/context")
		if not _lobby_request_current(generation, request_epoch, origin_scope): return
		if economy.ok and economy.data is Dictionary:
			next_lobby["shop"] = economy.data.get("shop", {})
			next_lobby["market"] = economy.data.get("market", [])
			next_lobby["inventory"] = economy.data.get("inventory", {})
	if next_lobby.get("unfinishedSettlement") == null and next_lobby.get("unfinishedMatch") == null and room.is_empty() and ticket.is_empty() and not next_lobby.has("activePreparation"):
		var active: Dictionary = await gateway.request("/api/v1/preparations", HTTPClient.METHOD_GET, null, [404])
		if not _lobby_request_current(generation, request_epoch, origin_scope): return
		if active.ok:
			if not _preparation_config_valid(active.data): return
			next_lobby["activePreparation"] = active.data
		elif active.status == 404: next_lobby["activePreparation"] = null
	if not _lobby_request_current(generation, request_epoch, origin_scope): return
	lobby = next_lobby
	mail = lobby.get("mail", {"items": [], "unreadCount": 0})
	for module in ["shop", "market", "inventory", "cards", "decks", "wallet", "mail"]:
		_cache_versions[module] = int(_cache_versions.get(module, 0)) + 1
	if lobby.player.get("selectedClass") != null: hero_class = lobby.player.selectedClass
	if lobby.get("unfinishedSettlement") != null:
		gateway.room_id = ""
		gateway.room_revision = 0
		settlement = lobby.unfinishedSettlement
		_settlement_recovery_match_id = ""
	elif lobby.get("unfinishedMatch") != null:
		gateway.room_id = lobby.unfinishedMatch.roomId
	elif room.is_empty() and ticket.is_empty():
		gateway.room_id = ""
		gateway.room_revision = 0
		if lobby.has("activePreparation"):
			preparation = lobby.activePreparation if lobby.activePreparation is Dictionary else {}
	changed.emit()

func _lobby_scope() -> String:
	return JSON.stringify([room.get("match_id", ""), gateway.room_id, preparation.get("preparationId", ""),
		ticket.get("ticketId", ""), settlement.get("settlementId", ""), _settlement_ack_pending_id, _cache_versions])

func _lobby_request_current(generation: int, request_epoch: int, origin_scope: String) -> bool:
	return generation == gateway.session_generation and request_epoch == _lobby_request_epoch and origin_scope == _lobby_scope()

func update_cache(module: String, value: Variant) -> void:
	if lobby.is_empty(): return
	if module == "mail" and value is Dictionary: mail = value
	lobby[module] = value
	_cache_versions[module] = int(_cache_versions.get(module, 0)) + 1
	cache_changed.emit(module)
	if module == "cards" and value is Array and lobby.get("shop") is Dictionary:
		var ownership: Dictionary = {}
		for card in value:
			if card is Dictionary: ownership[str(card.get("cardId", ""))] = bool(card.get("unlocked", false)) and int(card.get("copyCount", 0)) > 0
		var next_shop: Dictionary = lobby.shop.duplicate(true)
		var products: Array = next_shop.get("products", [])
		var changed_shop := false
		for index in products.size():
			var product: Dictionary = products[index]
			if str(product.get("kind", "")) != "Cards": continue
			var parsed: Variant = product.get("payload", {})
			if not parsed is Dictionary or not parsed.has("cardId"): continue
			var owned := bool(ownership.get(str(parsed.cardId), false))
			if bool(product.get("alreadyOwned", false)) == owned: continue
			product["alreadyOwned"] = owned
			products[index] = product
			changed_shop = true
		if changed_shop:
			next_shop["products"] = products
			lobby["shop"] = next_shop
			cache_changed.emit("shop")

func refresh_cache(module: String) -> void:
	if gateway.token.is_empty() or lobby.is_empty(): return
	if _cache_syncing.has(module):
		_cache_sync_again[module] = true
		return
	var paths := {"shop": "/api/v1/shop/", "market": "/api/v1/market/", "inventory": "/api/v1/inventory/", "cards": "/api/v1/cards/", "decks": "/api/v1/decks/", "mail": "/api/v1/mail/", "wallet": "/api/v1/economy/wallet"}
	if not paths.has(module): return
	var generation: int = gateway.session_generation
	_cache_syncing[module] = generation
	while generation == gateway.session_generation:
		_cache_sync_again.erase(module)
		var version: int = int(_cache_versions.get(module, 0))
		var result: Dictionary = await gateway.request(paths[module], HTTPClient.METHOD_GET, null, [404])
		if generation != gateway.session_generation: break
		if int(_cache_versions.get(module, 0)) != version:
			_cache_sync_again[module] = true
		elif result.ok:
			update_cache(module, result.data)
		elif module == "mail" and int(result.get("status", 0)) == 404:
			update_cache("mail", {"items": [], "unreadCount": 0})
		if not _cache_sync_again.has(module): break
	if _cache_syncing.get(module) == generation:
		_cache_syncing.erase(module)
		_cache_sync_again.erase(module)

func refresh_mail() -> void:
	if gateway.token.is_empty(): return
	var result: Dictionary = await gateway.request("/api/v1/mail", HTTPClient.METHOD_GET, null, [404])
	if result.ok and result.data is Dictionary:
		update_cache("mail", result.data)
	elif result.status == 404:
		update_cache("mail", {"items": [], "unreadCount": 0})

func mark_mail_read(id: String, rerender: bool = true) -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/%s/read" % id.uri_encode(), HTTPClient.METHOD_POST, {})
	if not result.ok: return
	for index in range(mail.get("items", []).size()):
		var item: Dictionary = mail.items[index]
		if str(item.get("id", item.get("mailId", ""))) == id:
			if not bool(item.get("read", false)):
				item["read"] = true
				mail.items[index] = item
				mail.unreadCount = maxi(0, int(mail.get("unreadCount", 0)) - 1)
			break
	update_cache("mail", mail)
	if rerender: changed.emit()

func claim_mail(id: String) -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/%s/claim" % id.uri_encode(), HTTPClient.METHOD_POST, {})
	if result.ok:
		if result.data is Dictionary and bool(result.data.get("alreadyClaimed", false)):
			await refresh_lobby()
			notice.emit("邮件附件已领取")
			return
		var granted: Array = result.data.get("granted", []) if result.data is Dictionary else []
		_apply_claimed_mail(id, granted)
		notice.emit("邮件附件已领取")
		_sync_claimed_assets(granted)

func claim_all_mail() -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/claim-all", HTTPClient.METHOD_POST, {})
	if result.ok:
		if not result.data is Dictionary or not result.data.get("claims") is Array:
			# Older servers do not report which mails they actually granted. Re-read
			# authoritative balances instead of crediting potentially stale mail.
			await refresh_lobby()
			notice.emit("邮件附件已全部领取")
			return
		var pending_ids: Dictionary = {}
		for item in mail.get("items", []):
			if item is Dictionary and not bool(item.get("claimed", false)):
				pending_ids[str(item.get("id", item.get("mailId", "")))] = true
		var actual_ids: Dictionary = {}
		for claim in result.data.claims:
			if claim is Dictionary: actual_ids[str(claim.get("mailId", ""))] = true
		if pending_ids != actual_ids:
			# A different client changed the mailbox. Reconcile all balances once.
			await refresh_lobby()
			notice.emit("邮件附件已全部领取")
			return
		var granted: Array = []
		for claim in result.data.claims:
			if not claim is Dictionary: continue
			var attachments: Array = claim.get("granted", [])
			_apply_claimed_mail(str(claim.get("mailId", "")), attachments)
			granted.append_array(attachments)
		notice.emit("邮件附件已全部领取")
		_sync_claimed_assets(granted)

func _sync_claimed_assets(granted: Array) -> void:
	update_cache("mail", mail)
	if granted.any(func(item): return item is Dictionary and item.get("kind", "") in ["Equipment", "HealthPotion", "AdvancedBag", "TopBag"]):
		refresh_cache("inventory")
	if granted.any(func(item): return item is Dictionary and item.get("kind", "") == "Card"):
		refresh_cache("cards")

func _apply_claimed_mail(id: String, granted: Array) -> void:
	for index in range(mail.get("items", []).size()):
		var item: Dictionary = mail.items[index]
		if str(item.get("id", item.get("mailId", ""))) != id: continue
		if not bool(item.get("read", false)): mail.unreadCount = maxi(0, int(mail.get("unreadCount", 0)) - 1)
		item["read"] = true
		item["claimed"] = true
		mail.items[index] = item
		break
	var wallet: Dictionary = lobby.get("wallet", {}).duplicate()
	var materials: Dictionary = lobby.get("materials", {}).duplicate()
	for raw in granted:
		var attachment: Dictionary = raw if raw is Dictionary else {}
		var kind := str(attachment.get("kind", ""))
		var amount := int(attachment.get("amount", 0))
		if kind == "Gold": wallet["gold"] = int(wallet.get("gold", 0)) + amount
		elif kind == "Diamond": wallet["diamond"] = int(wallet.get("diamond", 0)) + amount
		elif kind in ["WarriorSoul", "PriestSoul", "MageSoul", "GuardianSoul", "EquipmentFragments"]:
			var key := kind.left(1).to_lower() + kind.substr(1)
			materials[key] = int(materials.get(key, 0)) + amount
	lobby["wallet"] = wallet
	lobby["materials"] = materials
	cache_changed.emit("wallet")
	changed.emit()

func mark_all_mail_read() -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/read-all", HTTPClient.METHOD_POST, {})
	if result.ok:
		for index in range(mail.get("items", []).size()):
			var item: Dictionary = mail.items[index]
			item["read"] = true
			mail.items[index] = item
		mail["unreadCount"] = 0
		update_cache("mail", mail)

func delete_mail(id: String) -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/%s" % id.uri_encode(), HTTPClient.METHOD_DELETE, {})
	if result.ok:
		notice.emit("邮件已删除")
		mail["items"] = mail.get("items", []).filter(func(item): return str(item.get("id", item.get("mailId", ""))) != id)
		mail["unreadCount"] = mail.items.filter(func(item): return not bool(item.get("read", false))).size()
		update_cache("mail", mail)

func delete_read_mail() -> void:
	var result: Dictionary = await gateway.request("/api/v1/mail/read", HTTPClient.METHOD_DELETE, {})
	if result.ok:
		notice.emit("已读邮件已清理")
		mail["items"] = mail.get("items", []).filter(func(item): return not bool(item.get("read", false)))
		mail["unreadCount"] = mail.items.size()
		update_cache("mail", mail)

func select_class(value: String) -> void:
	if busy or not room.is_empty() or not preparation.is_empty() or not ticket.is_empty(): return
	if value not in ["Priest", "Mage", "Guardian"]: return
	if value == hero_class and (_pending_class.is_empty() or _pending_class == value) and str(lobby.get("player", {}).get("selectedClass", "")) == value: return
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
	var current_info: bool = not server_info.is_empty() and _server_info_address == gateway.base_url
	if not ((current_info and validate_config(str(server_info.get("configVersion", "")), "服务器")) or await _refresh_server_info()):
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
	if result.ok and _preparation_config_valid(result.data):
		preparation = result.data
		lobby["activePreparation"] = result.data
		refresh_cache("inventory")
	busy = false
	changed.emit()

func enqueue() -> void:
	if busy or preparation.is_empty() or not gateway.online or not configuration_error.is_empty(): return
	busy = true
	var generation: int = gateway.session_generation
	var current_info: bool = not server_info.is_empty() and _server_info_address == gateway.base_url
	if not ((current_info and validate_config(str(server_info.get("configVersion", "")), "服务器")) or await _refresh_server_info()) or not _preparation_config_valid(preparation):
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
	var snapshot: Dictionary = value.snapshot if value.get("snapshot") is Dictionary else {}
	return validate_config(str(snapshot.get("configVersion", "")), "准备")

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
		lobby["activePreparation"] = null
		refresh_cache("inventory")
	if generation != gateway.session_generation: return
	busy = false
	changed.emit()

func allowed(action: String) -> bool:
	var aliases := {"reward.choice.refresh": "choice.refresh", "reward.choice.claim": "choice.pick"}
	if action == "battle.play_cards" and _target_selection_pending(): return false
	if action not in LATEST_WINS_ACTIONS and _has_pending_action(action): return false
	return configuration_error.is_empty() and gateway.online and not gateway.recovering and (action in room.get("allowed_actions", []) or aliases.get(action, "") in room.get("allowed_actions", []))

func has_pending_commands() -> bool:
	return not _pending_commands.is_empty() or not _latest_commands.is_empty() or not _queued_command.is_empty()

func combat_wait_state() -> Dictionary:
	var player: Dictionary = room.get("player", {})
	var hand: Array = player.get("hand", [])
	var reason := "available"
	var remaining_ms := 0
	if not gateway.online or gateway.recovering:
		reason = "recovering"
	elif has_pending_commands():
		reason = "confirming"
	elif int(player.get("stun_remaining_ms", 0)) > 0:
		reason = "stunned"
		remaining_ms = int(player.stun_remaining_ms)
	elif combat_target_id().is_empty():
		reason = "target"
	elif hand.is_empty() and int(player.get("draw_block_remaining_ms", 0)) > 0:
		reason = "draw_blocked"
		remaining_ms = int(player.draw_block_remaining_ms)
	elif hand.is_empty():
		reason = "drawing"
	elif hand.size() >= 5:
		reason = "full_hand"
	return {"reason": reason, "remaining_ms": remaining_ms, "hand_count": hand.size(),
		"legal_opportunity": reason in ["available", "full_hand"] and allowed("battle.play_cards")}

func command(action: String, payload: Dictionary = {}) -> bool:
	if not allowed(action): return false
	if action in LATEST_WINS_ACTIONS:
		_latest_commands[action] = {"payload": payload.duplicate(true), "due": Time.get_ticks_msec() + LATEST_WINS_DEBOUNCE_MS}
		if action == "battle.select_target" and _target_selection_pending(): clear_combat_preview()
		changed.emit()
		return true
	if not _queued_command.is_empty() or _has_pending_action(action): return false
	if action == "battle.play_cards" and not _pending_play.is_empty(): return false
	if action == "relic.read": return gateway.send(action, payload)
	# Send the intent against the latest locally known revision. The server
	# serializes it in the room actor; only a confirmed revision conflict reads
	# a fresh snapshot and retries once.
	return _send_queued_command({"action": action, "payload": payload.duplicate(true)})

func toggle_card(instance_id: String) -> void:
	if not allowed("battle.play_cards"): return
	if not room.get("player", {}).get("hand", []).any(func(card): return card.get("instance_id", "") == instance_id): return
	if instance_id in selected_cards: selected_cards.erase(instance_id)
	else: selected_cards.append(instance_id)
	sound_requested.emit("card_select")
	_refresh_combat_preview()
	changed.emit()

func clear_combat_preview() -> void:
	combat_preview = {}
	_preview_request = {}
	_preview_deadline = 0

func _target_selection_pending() -> bool:
	# Synchronizing the GDD death fallback keeps the current effective target.
	# A manual switch to another target must reach the snapshot before playing.
	var target_id := combat_target_id()
	var queued: Dictionary = _latest_commands.get("battle.select_target", {})
	if not queued.is_empty() and _intent_valid("battle.select_target", queued.get("payload", {})) and str(queued.get("payload", {}).get("target_id", "")) != target_id: return true
	for pending in _pending_commands.values():
		if pending.get("action", "") == "battle.select_target" and _intent_valid("battle.select_target", pending.get("payload", {})) and str(pending.get("payload", {}).get("target_id", "")) != target_id: return true
	return false

func _refresh_combat_preview() -> void:
	clear_combat_preview()
	combat_preview = _calculate_combat_preview(selected_cards)
	if combat_preview.is_empty() or not target_alive(combat_target_id()): return
	_preview_request = {"request_id": "", "context": _preview_context(selected_cards), "revision": int(room.get("room_revision", 0)), "due": Time.get_ticks_msec() + LATEST_WINS_DEBOUNCE_MS}

func _flush_combat_preview() -> void:
	# A preview is a bounded read; it never enters the business-command queue
	# or locks a legal play while the local estimate is visible.
	if _preview_request.is_empty(): return
	if _preview_request.get("context", {}) != _preview_context(selected_cards) or not allowed("battle.play_cards"):
		clear_combat_preview()
		return
	var now := Time.get_ticks_msec()
	if not str(_preview_request.get("request_id", "")).is_empty():
		if now >= _preview_deadline: _preview_request = {}
		return
	if now < int(_preview_request.get("due", 0)): return
	var context: Dictionary = _preview_request.context
	var request_id: String = gateway.new_id()
	var payload := {"battle_id": context.battle_id, "target_id": context.target_id, "card_instance_ids": context.card_instance_ids.duplicate()}
	if gateway.send("combat.preview", payload, request_id):
		_preview_request["request_id"] = request_id
		_preview_deadline = now + 3000
	else: _preview_request = {}

func _request_snapshot() -> void:
	if room.is_empty() or not gateway.online or gateway.recovering or _snapshot_request_pending: return
	var now := Time.get_ticks_msec()
	if now - _snapshot_request_at < 80: return
	_snapshot_request_at = now
	_snapshot_request_pending = gateway.send("room.snapshot.read")

func refresh_room_snapshot() -> void:
	_request_snapshot()

func _has_pending_action(action: String) -> bool:
	for pending in _pending_commands.values():
		if str(pending.get("action", "")) == action: return true
	return false

func _flush_latest_commands() -> void:
	var now := Time.get_ticks_msec()
	for action in _latest_commands.keys():
		var queued: Dictionary = _latest_commands[action]
		if action == "battle.select_target" and not _intent_valid(action, queued.get("payload", {})):
			_latest_commands.erase(action)
			continue
		if now < int(queued.get("due", 0)): continue
		if not allowed(action) or not _queued_command.is_empty() or _has_pending_action(action):
			queued["due"] = now + LATEST_WINS_DEBOUNCE_MS
			_latest_commands[action] = queued
			continue
		_latest_commands.erase(action)
		_send_queued_command({"action": action, "payload": queued.get("payload", {}).duplicate(true)})

func _preview_context(ids: Array) -> Dictionary:
	var battle: Dictionary = room.get("duel", room.get("pve", {}))
	var player: Dictionary = room.get("player", {})
	var player_context := {}
	for key in ["player_id", "phase", "hero_class", "weapon_level", "combat", "battle_status", "numerical_state", "stun_remaining_ms", "draw_block_remaining_ms", "draw_speed_remaining_ms", "draw_block_speed_remaining_ms", "base_draw_interval_seconds"]:
		if player.has(key): player_context[key] = player[key]
	var selected_hand: Array = []
	for id in ids:
		for card in player.get("hand", []):
			if card.get("instance_id", "") == id: selected_hand.append(card.duplicate(true))
	return {"room_id": room.get("room_id", ""), "room_revision": int(room.get("room_revision", 0)), "config_version": room.get("config_version", ""),
		"battle_id": battle.get("duel_id", battle.get("battle_id", "")), "target_id": combat_target_id(), "card_instance_ids": ids.duplicate(), "selected_hand": selected_hand,
		"player": player_context.duplicate(true),
		"target": battle.get("opponent", {}).duplicate(true) if room.has("duel") else _monster_by_id(battle).duplicate(true),
		"opponent_status": battle.get("opponent_status", {}).duplicate(true), "opponent_class": battle.get("opponent_class", "")}

func _accept_combat_preview(payload: Dictionary) -> void:
	if payload.get("_replayed", false): return
	if not allowed("battle.play_cards") or not target_alive(combat_target_id()): return
	if _preview_request.is_empty() or payload.get("_request_id", "") != _preview_request.get("request_id", ""): return
	if Time.get_ticks_msec() >= _preview_deadline or _preview_request.get("context", {}) != _preview_context(selected_cards): return
	var revision := int(payload.get("_room_revision", -1))
	if revision != int(_preview_request.get("revision", -1)) or revision != int(room.get("room_revision", 0)): return
	var context: Dictionary = _preview_request.context
	if payload.has("battle_id") and payload.battle_id != context.battle_id: return
	if payload.has("target_id") and payload.target_id != context.target_id: return
	if payload.has("card_instance_ids") and payload.card_instance_ids != context.card_instance_ids: return
	combat_preview = payload.duplicate(true)
	combat_preview["source_revision"] = revision
	combat_preview["authoritative"] = true
	combat_preview["control_estimated"] = false
	_preview_request = {}
	_preview_deadline = 0

func _status_bonuses(status: Dictionary) -> Dictionary:
	var result := {}
	for entry in status.get("bonuses", []): result[str(entry.get("key", ""))] = float(entry.get("value", 0))
	return result

func _counter(attacker: String, target: String) -> bool:
	return ElementRules.counters(attacker, target)

func _conflict_pair(left: String, right: String) -> bool:
	return ElementRules.conflicts(left, right)

func _generated(element: String) -> String:
	return ElementRules.generated(element)

func _monster_by_id(battle: Dictionary) -> Dictionary:
	return BattleTargets.current(battle)

func combat_target_id() -> String:
	if room.has("duel"): return str(room.duel.get("opponent_id", ""))
	return str(BattleTargets.current(room.get("pve", {})).get("monster_id", ""))

func _sync_pve_target() -> void:
	var action := "battle.select_target"
	var queued: Dictionary = _latest_commands.get(action, {})
	if not queued.is_empty() and not _intent_valid(action, queued.get("payload", {})):
		_latest_commands.erase(action)
	if room.has("duel"): return
	var battle: Dictionary = room.get("pve", {})
	var target_id := combat_target_id()
	if target_id.is_empty() or target_id == str(battle.get("current_target_id", "")): return
	if not allowed(action): return
	var payload := {"battle_id": battle.get("battle_id", ""), "target_id": target_id}
	# Repeated snapshots must not reset the debounce or send duplicate requests.
	if _latest_commands.has(action): return
	for pending in _pending_commands.values():
		if pending.get("action", "") == action and pending.get("payload", {}) == payload: return
	command(action, payload)

func _target_resistance(element: String, battle: Dictionary, monster: Dictionary = {}) -> float:
	if battle.has("opponent_status"): return _status_bonuses(battle.opponent_status).get("resistance_" + element, 0.0)
	if monster.is_empty(): monster = _monster_by_id(battle)
	var id := str(monster.get("monster_id", ""))
	if id == "annihilation-core":
		var boss_main := "Fire" if int(monster.get("boss_phase", 1)) == 1 else "Metal"
		var neighbor := "Wood" if boss_main == "Fire" else "Earth"
		if element == boss_main: return 0.35
		if element == neighbor: return 0.20
		if _counter(element, boss_main): return -0.30
		if _counter(boss_main, element): return 0.30
		return 0.0
	# Shield/charge intents have no attack element. Species resistance remains
	# fixed through those intents; BoxSpirit keeps its publicly rolled element.
	var species_elements := {"fire-bat": "Fire", "fire-bat-a": "Fire", "fire-bat-b": "Fire", "rust-rat": "Metal", "thorn-mite": "Wood", "murk-snail": "Water", "sand-lizard": "Earth", "metal-guard": "Metal", "fire-herald": "Fire", "marsh-mother": "Water", "stone-guard": "Earth", "thorn-guard": "Wood"}
	var species_id := id.trim_suffix("-a").trim_suffix("-b")
	var main := str(species_elements.get(species_id, monster.get("intent_element", "None")))
	if main == "None": return 0.0
	var elite := id in ["metal-guard", "fire-herald", "marsh-mother", "stone-guard", "thorn-guard"]
	if element == main: return 0.25 if elite else 0.15
	if elite and element == _generated(main): return 0.15
	if _counter(element, main): return -0.30
	if _counter(main, element): return 0.25
	return 0.0

func _calculate_combat_preview(ids: Array) -> Dictionary:
	if ids.is_empty() or not allowed("battle.play_cards"): return {}
	var battle: Dictionary = room.get("duel", room.get("pve", {}))
	var hand_by_id := {}
	for card in room.get("player", {}).get("hand", []):
		var instance_id = card.get("instance_id", "")
		if not hand_by_id.has(instance_id): hand_by_id[instance_id] = card
	var cards: Array = []
	for id in ids:
		var instance: Dictionary = hand_by_id.get(id, {})
		if instance.is_empty(): return {}
		var definition: Dictionary = CatalogIndex.card(str(instance.get("card_id", "")))
		if definition.is_empty(): return {}
		cards.append(CardDetails.with_element(CardDetails.at_level(definition, int(instance.get("level", 0))), str(instance.get("element_override", ""))))
	var target_monster := _monster_by_id(battle)
	var status := _status_bonuses(room.get("player", {}).get("battle_status", {}))
	var elemental: Array = cards.filter(func(card): return int(card.get("elemental_damage", 0)) > 0 and str(card.get("element", "None")) != "None" and int(card.get("secondary_elemental_damage", 0)) == 0)
	var counts := {}
	for card in elemental: counts[card.element] = int(counts.get(card.element, 0)) + 1
	# The first selected elemental card establishes the core.  Do not choose
	# the most frequent element: a later branch may contain more cards, but it
	# must not replace the player's first-card core choice.
	var core := str(elemental[0].get("element", "")) if not elemental.is_empty() else ""
	var core_count := int(counts.get(core, 0))
	var reveal_element: String = str({"Mage": "Fire", "Priest": "Water"}.get(room.get("player", {}).get("hero_class", ""), "Earth"))
	# Catalog rows use null for cards without the flag; GDScript has no bool()
	# conversion constructor, so test the actual boolean value directly.
	var reveal := cards.any(func(card): return card.get("is_class_reveal", false) == true)
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
	var conflict_heal := 0
	if not core.is_empty():
		for card in elemental:
			if str(card.get("element", "None")) != core and not card.get("is_element_tuning", false) and _conflict_pair(core, str(card.get("element", "None"))): conflict_pairs += 1
		var resonance_bonus := 1 if cards.any(func(card): return int(card.get("resonance_bonus", 0)) > 0) else 0
		# The first core card is the fixed baseline. M counts later core cards
		# after counter cards consume their advantage.
		var main_core_stacks: int = maxi(0, core_count - 1 + resonance_bonus - conflict_pairs)
		resonance = 1.0 + 0.20 * main_core_stacks
		var cancel_bonus := float(cards.map(func(card): return float(card.get("conflict_cancel_bonus", 0))).max())
		cancellation = minf(0.80, 0.20 * conflict_pairs + cancel_bonus) if conflict_pairs > 0 else 0.0
		var shared_multiplier: float = (1.0 + float(status.get("damage_" + core, 0.0))) * (1.0 - _target_resistance(core, battle, target_monster))
		if conflict_pairs > 0:
			var core_base := 0
			for index in cards.size():
				if str(cards[index].get("element", "None")) == core and int(cards[index].get("secondary_elemental_damage", 0)) == 0 and not cards[index].get("is_element_tuning", false): core_base += int(bases[index])
			var coefficient := maxf(.5, float(cards.map(func(card): return float(card.get("conflict_heal_coefficient", 0))).max()))
			var base_heal := int(floor(core_base * shared_multiplier * resonance * cancellation * coefficient)) + 2 * conflict_pairs
			conflict_heal = int(floor(base_heal * (1.0 + float(status.get("vitality_heal", 0.0)))))
		for i in cards.size():
			var card: Dictionary = cards[i]
			if int(card.get("elemental_damage", 0)) <= 0 or str(card.get("element", "None")) == "None" or int(card.get("secondary_elemental_damage", 0)) > 0: continue
			var element := str(card.get("element", "None"))
			var branch_multiplier := resonance if element == core else (1.0 if card.get("is_element_tuning", false) or not _conflict_pair(core, element) else 1.0 - cancellation)
			var value := int(floor(float(bases[i]) * shared_multiplier * branch_multiplier))
			if value > 0: segments[element] = int(segments.get(element, 0)) + value
	var total := int(segments.values().reduce(func(a, b): return a + b, 0))
	var direct := 0
	for i in cards.size():
		var card: Dictionary = cards[i]
		if int(card.get("secondary_elemental_damage", 0)) > 0:
			var secondary := int(card.get("secondary_elemental_damage", 0))
			if reveal and card.get("secondary_element", "None") == reveal_element: secondary = int(floor(secondary * 1.3))
			for pair in [[str(card.get("element", "None")), int(bases[i])], [str(card.get("secondary_element", "None")), secondary]]:
				var elemental_multiplier := (1.0 + float(status.get("damage_" + pair[0], 0.0))) * (1.0 - _target_resistance(pair[0], battle, target_monster)) if core.is_empty() else (1.0 + float(status.get("damage_" + core, 0.0))) * (1.0 - _target_resistance(core, battle, target_monster))
				var value := int(floor(pair[1] * elemental_multiplier))
				if value > 0: segments[pair[0]] = int(segments.get(pair[0], 0)) + value; total += value
		# Printed direct damage is already a direct segment.  Piercing is an
		# additional per-card contribution and must not replace the base value.
		direct += int(card.get("direct_damage", 0))
		var piercing_secondary := int(card.get("secondary_elemental_damage", 0))
		if reveal and card.get("secondary_element", "None") == reveal_element: piercing_secondary = int(floor(piercing_secondary * 1.3))
		direct += int(floor((bases[i] + piercing_secondary + int(card.get("direct_damage", 0))) * float(status.get("piercing", 0.0))))
	if direct > 0: segments["Direct"] = direct; total += direct
	var target: Dictionary = battle.get("opponent", {}) if battle.has("opponent") else target_monster
	var target_shield := int(target.get("shield", 0))
	var incoming_multiplier := 1.0
	if str(battle.get("opponent_class", "")) == "Guardian":
		var target_status := _status_bonuses(battle.get("opponent_status", {}))
		incoming_multiplier = 1.0 - float(target_status.get("bulwark_reduction", 0.0))
		total = int(floor(total * incoming_multiplier))
	var actual := mini(total, target_shield + int(target.get("hp", 0)))
	var visible_segments := _visible_damage_segments(segments, actual, incoming_multiplier)
	var recovery := _preview_recovery(cards, status, conflict_pairs, conflict_heal)
	var draw_charge := float(cards.map(func(card): return float(card.get("draw_charge", 0))).reduce(func(a, b): return a + b, 0))
	var immediate_draw := int(cards.map(func(card): return int(card.get("immediate_draw", 0))).reduce(func(a, b): return a + b, 0))
	var player: Dictionary = room.get("player", {})
	if str(player.get("hero_class", "")) == "Mage" and core_count > 0:
		var passive: Dictionary = player.get("battle_status", {})
		var combo := int(passive.get("combo", 0)) + 1 if str(passive.get("core_element", "")) == core else 1
		var rhythm := mini(5, core_count + combo - 1)
		draw_charge += minf(.50, float([0.0, .12, .24, .36, .48, .50][rhythm]) + recovery.weapon_bonus)
		var draw_basis := core_count if str(player.get("numerical_state", {}).get("fenxian_policy", "CurrentRhythm")) == "CoreCardsSpent" else rhythm
		immediate_draw += 0 if draw_basis <= 2 else (1 if draw_basis <= 4 else 2)
	var stun := float(cards.map(func(card): return float(card.get("stun_seconds", 0))).max())
	var block := float(cards.map(func(card): return float(card.get("draw_block_seconds", 0))).max())
	return {"authoritative": false, "control_estimated": true, "core_element": core, "core_count": core_count, "damage": total, "damage_segments": visible_segments,
		"shield_damage": mini(actual, target_shield), "hp_damage": maxi(0, actual - target_shield), "heal": recovery.heal, "shield_gain": recovery.shield_gain,
		"heal_overflow": recovery.heal_overflow, "shield_overflow": recovery.shield_overflow, "health_cost": recovery.health_cost,
		"stun_seconds": str(_preview_control(stun, recovery)), "draw_block_seconds": str(_preview_control(block, recovery) if room.has("duel") else 0.0),
		"draw_block_speed_seconds": str(_preview_control(block / 2.0, recovery) if not room.has("duel") else 0.0),
		"draw_charge": str(draw_charge), "immediate_draw": immediate_draw,
		"draw_speed_seconds": str(cards.map(func(card): return float(card.get("draw_speed_seconds", 0))).max()), "draw_speed_modifier": str(cards.map(func(card): return float(card.get("draw_speed_modifier", 0))).min()),
		"resonance_multiplier": str(resonance), "conflict_pair_count": conflict_pairs, "conflict_cancellation": str(cancellation)}

func _visible_damage_segments(segments: Dictionary, actual: int, multiplier: float) -> Array:
	if actual <= 0: return []
	var segment_total := int(segments.values().reduce(func(a, b): return a + b, 0))
	if segment_total <= 0: return [{"kind": "Direct", "amount": actual}]
	var largest_kind := ""
	var largest_value := -1
	var allocated := 0
	var reduced: Dictionary = {}
	for kind in segments:
		if int(segments[kind]) > largest_value:
			largest_kind = kind
			largest_value = int(segments[kind])
		var amount := int(floor(float(segments[kind]) * multiplier))
		reduced[kind] = amount
		allocated += amount
	var expected := int(floor(segment_total * multiplier))
	reduced[largest_kind] += expected - allocated
	if expected != actual:
		allocated = 0
		var scale := float(actual) / maxf(1.0, expected)
		for kind in reduced:
			reduced[kind] = int(floor(float(reduced[kind]) * scale))
			allocated += int(reduced[kind])
		reduced[largest_kind] += actual - allocated
	var result: Array = []
	for kind in reduced:
		if int(reduced[kind]) > 0: result.append({"kind": kind, "amount": int(reduced[kind])})
	return result

func _preview_recovery(cards: Array, status: Dictionary, conflict_pairs: int, conflict_heal: int) -> Dictionary:
	var player: Dictionary = room.get("player", {})
	var hero := str(player.get("hero_class", hero_class))
	var combat: Dictionary = player.get("combat", {})
	var maximum_hp := int(combat.get("maximum_hp", {"Mage": 70, "Priest": 80, "Guardian": 100}.get(hero, 70)))
	var hp := int(combat.get("hp", maximum_hp))
	var shield := int(combat.get("shield", 0))
	var weapon := clampi(int(player.get("weapon_level", 0)), 0, 5)
	var weapon_bonus := float([.06, .08, .10, .11, .13, .14][weapon])
	var requested_cost := int(cards.map(func(card): return int(card.get("health_cost", 0))).reduce(func(a, b): return a + b, 0))
	var after_cost := maxi(1, hp - maxi(0, requested_cost))
	var missing_ratio := clampf(1.0 - float(hp) / maxf(1.0, maximum_hp), 0.0, 1.0)
	var raw_heal: float = float(cards.map(func(card): return int(card.get("heal", 0))).reduce(func(a, b): return a + b, 0)) * (1.0 + .25 * conflict_pairs)
	if hero == "Priest":
		raw_heal = floor(raw_heal * (1.0 + .80 * missing_ratio))
		raw_heal = floor(raw_heal * (1.0 + weapon_bonus))
	raw_heal = floor(raw_heal * (1.0 + float(status.get("vitality_heal", 0.0)))) + conflict_heal
	var effective_max_hp := int(floor(maximum_hp * (1.0 + minf(.40, float(status.get("vitality_overcap", 0.0))))))
	var effective_heal := mini(int(raw_heal), maxi(0, effective_max_hp - after_cost))
	var printed_shield := int(cards.map(func(card): return int(card.get("shield", 0))).reduce(func(a, b): return a + b, 0))
	var raw_shield: float = printed_shield
	if hero == "Guardian": raw_shield *= 1.0 + .45 * clampf(float(after_cost) / maxf(1.0, maximum_hp), 0.0, 1.0)
	raw_shield = floor(raw_shield * (1.0 + float(status.get("bulwark_shield", 0.0))))
	if hero == "Guardian" and printed_shield > 0:
		var numerical: Dictionary = player.get("numerical_state", {})
		if str(numerical.get("guardian_policy", "CurrentSteps")) == "FractionalRemainder":
			if shield < maximum_hp / 2: raw_shield += floor(float([10, 14, 18, 22, 26, 30][weapon] + int(numerical.get("guardian_remainder_tenths", 0))) / 10.0)
		else: raw_shield += 3 if weapon >= 4 else (2 if weapon >= 2 else 1)
	var effective_shield := mini(int(raw_shield), maxi(0, int(maximum_hp / 2) - shield))
	return {"heal": effective_heal, "shield_gain": effective_shield, "heal_overflow": maxi(0, int(raw_heal) - effective_heal), "shield_overflow": maxi(0, int(raw_shield) - effective_shield),
		"health_cost": maxi(0, hp - after_cost), "weapon_bonus": weapon_bonus, "missing_ratio": missing_ratio, "hero": hero,
		"hp": hp, "maximum_hp": maximum_hp, "weapon_level": weapon}

func _preview_control(seconds: float, recovery: Dictionary) -> float:
	if recovery.hero != "Priest" or seconds <= 0: return seconds
	# Authoritative control uses decimal floors. Published durations have whole
	# microseconds; integer numerators avoid binary rounding below a millisecond.
	var maximum := maxi(1, int(recovery.maximum_hp))
	var bounded_hp := clampi(int(recovery.hp), 0, maximum)
	var numerator := roundi(seconds * 1000000.0) * (140 * maximum - 40 * bounded_hp)
	var milliseconds := floori(float(numerator) / float(100000 * maximum))
	var weapon_percent := int([6, 8, 10, 11, 13, 14][int(recovery.weapon_level)])
	return floor(float(milliseconds * (100 + weapon_percent)) / 100.0) / 1000.0

func play_cards() -> void:
	if selected_cards.is_empty(): return
	var battle: Dictionary = room.get("duel", room.get("pve", {}))
	var target_id := combat_target_id()
	if not target_alive(target_id):
		notice.emit("请先选择存活目标")
		return
	var payload := {"battle_id": battle.get("duel_id", battle.get("battle_id", "")), "target_id": target_id, "card_instance_ids": selected_cards.duplicate()}
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
	var map_player_count := int(snapshot.get("map_player_count", 0))
	if map_player_count <= 0:
		map_player_count = int(payload.get("player_count", room.get("map_player_count", 0) if same_room else 0))
	if map_player_count > 0: snapshot["map_player_count"] = map_player_count
	var before_battle: Dictionary = room.get("duel", room.get("pve", {}))
	var after_battle: Dictionary = snapshot.get("duel", snapshot.get("pve", {}))
	var before_id: String = before_battle.get("duel_id", before_battle.get("battle_id", ""))
	var after_id: String = after_battle.get("duel_id", after_battle.get("battle_id", ""))
	var before_phase := str(room.get("player", {}).get("phase", ""))
	var after_phase := str(snapshot.get("player", {}).get("phase", ""))
	if live and after_phase in ["Pve", "Pvp"] and not after_id.is_empty() and (before_phase not in ["Pve", "Pvp"] or before_id != after_id):
		sound_requested.emit("battle_start")
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
	var player_id := str(room.get("player", {}).get("player_id", ""))
	var attacker_id := str(payload.get("attacker_id", ""))
	var target_id := str(payload.get("target_id", ""))
	var player_attack := not player_id.is_empty() and attacker_id == player_id
	var player_hit := not player_id.is_empty() and target_id == player_id
	if kind == "battle.combo_resolved" and player_attack and not payload.get("card_instance_ids", []).is_empty():
		sound_requested.emit("card_play")
	var largest := 0
	var damage_kind := "direct"
	for segment in payload.get("damage_segments", []):
		if int(segment.get("amount", 0)) > largest:
			largest = int(segment.amount)
			damage_kind = str(segment.get("kind", "Direct")).to_lower()
	if int(payload.get("damage", 0)) > 0:
		if damage_kind not in ["direct", "fire", "water", "wood", "metal", "earth"]: damage_kind = "direct"
		sound_requested.emit("player_attack" if player_attack else "monster_attack")
		sound_requested.emit("player_hit" if player_hit else "monster_hit")
		sound_requested.emit("hit_" + damage_kind)
	if int(payload.get("heal", 0)) > 0: sound_requested.emit("heal")
	if int(payload.get("shield_gain", 0)) > 0: sound_requested.emit("shield")
	if bool(payload.get("battle_ended", false)) and player_attack:
		sound_requested.emit("battle_victory")

func _sound_event(kind: String, payload: Dictionary) -> void:
	if not _sound_is_live(payload): return
	var request_id: String = payload.get("_request_id", "")
	var command_info: Dictionary = _sound_commands.get(request_id, {})
	var command_action: String = command_info.get("action", "") if command_info.get("room_id", "") == room.get("room_id", "") else ""
	var expected := {"reward.choice_claimed": "reward.choice.claim", "reward.choice.claimed": "reward.choice.claim", "relic.taken": "relic.take", "relic.replaced": "relic.replace", "action.potion_used": "action.potion", "room.moved": "room.move", "action.extract_started": "action.extract", "battle.target_selected": "battle.select_target"}
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
			"battle.target_selected": sound_requested.emit("battle_target")
			"inventory.changed":
				if action in ["inventory.equip", "inventory.unequip"]: sound_requested.emit("equip")
				elif action in ["card.upgrade", "inventory.upgrade"]: sound_requested.emit("upgrade")
				elif action in ["shop.buy", "market.buy", "market.sell"]: sound_requested.emit("purchase")
				else: sound_requested.emit("ui_confirm")
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

func _send_queued_command(queued: Dictionary) -> bool:
	var request_id: String = gateway.new_id()
	if gateway.send(queued.action, queued.payload, request_id):
		var deadline := Time.get_ticks_msec() + 3000
		_play_deadline = deadline
		_pending_commands[request_id] = {"action": queued.action, "payload": queued.payload.duplicate(true), "room_id": room.get("room_id", ""), "sent_revision": int(room.get("room_revision", 0)), "retry": queued.get("retry", false), "deadline": deadline}
		if queued.action == "battle.play_cards":
			_pending_play = {"request_id": request_id, "room_id": room.get("room_id", ""), "payload": queued.payload.duplicate(true), "retry": queued.get("retry", false)}
		_sound_commands[request_id] = {"action": queued.action, "room_id": room.get("room_id", "")}
		if _sound_commands.size() > 64: _sound_commands.erase(_sound_commands.keys()[0])
		changed.emit()
		return true
	elif queued.get("retry", false):
		notice.emit("操作未发出，请在连接恢复后重试")
	return false

func _retry_rejected_command(payload: Dictionary) -> bool:
	var request_id := str(payload.get("_request_id", ""))
	if request_id.is_empty() or not _pending_commands.has(request_id): return false
	var pending: Dictionary = _pending_commands[request_id]
	_pending_commands.erase(request_id)
	if pending.action == "battle.play_cards": _pending_play = {}
	# Retry only an explicit pre-execution rejection, never an ambiguous timeout.
	if pending.get("confirmed", false) or pending.retry or payload.get("_replayed", false) or Time.get_ticks_msec() > int(pending.get("deadline", 0)) or (pending.action == "battle.play_cards" and Time.get_ticks_msec() > _play_deadline): return false
	var is_revision_conflict: bool = payload.get("code", "") == "REVISION_CONFLICT" or (
		payload.get("code", "") == "COMMAND_REJECTED" and
		str(payload.get("detail", "")).begins_with("Room revision conflict."))
	if not is_revision_conflict: return false
	if pending.room_id != room.get("room_id", "") or not allowed(pending.action) or not _queued_command.is_empty(): return false
	var snapshot_id: String = gateway.new_id()
	_queued_command = {"action": pending.action, "payload": pending.payload, "retry": true, "room_id": pending.room_id, "snapshot_id": snapshot_id}
	_queue_deadline = Time.get_ticks_msec() + 3000
	if not gateway.send("room.snapshot.read", {}, snapshot_id):
		_queued_command = {}
		return false
	_snapshot_request_pending = true
	_sound_commands.erase(request_id)
	return true

func _snapshot_confirms_command(pending: Dictionary, snapshot: Dictionary) -> bool:
	if str(snapshot.get("room_id", "")) != str(pending.get("room_id", "")): return false
	var revision := int(snapshot.get("room_revision", -1))
	var confirmed_revision := int(pending.get("confirmed_revision", -1))
	return revision >= confirmed_revision if confirmed_revision >= 0 else revision > int(pending.get("sent_revision", 0))

func _on_event(kind: String, payload: Dictionary) -> void:
	if kind == "pong": return
	if kind == "error.command_rejected" and payload.get("code", "") == "NOT_IN_ROOM":
		var origin: Dictionary = payload.get("_origin_context", {})
		var current_match := str(room.get("match_id", _settlement_recovery_match_id))
		if not origin.is_empty() and str(origin.get("match_id", "")) != current_match: return
		# A second rejection can arrive after the room was cleared. Keep the
		# original match until its durable receipt is visible or acknowledged.
		if not current_match.is_empty(): _settlement_recovery_match_id = current_match
		var generation: int = gateway.session_generation
		_settlement_poll_at = 0
		room = {}
		selected_cards.clear()
		clear_combat_preview()
		payload["_retry_handled"] = true
		await refresh_lobby()
		if generation != gateway.session_generation or (not room.is_empty() and str(room.get("match_id", "")) != current_match): return
		if not settlement.is_empty(): _settlement_recovery_match_id = ""
		if settlement.is_empty() and lobby.get("unfinishedMatch") != null:
			notice.emit("上次探索正在结算，请稍后点击重新连接")
		return
	if kind == "error.command_rejected" and _retry_rejected_command(payload):
		payload["_retry_handled"] = true
		return
	var event_request_id := str(payload.get("_request_id", ""))
	if not event_request_id.is_empty() and _pending_commands.has(event_request_id) and kind != "error.command_rejected":
		var pending: Dictionary = _pending_commands[event_request_id]
		pending["confirmed"] = true
		pending["confirmed_revision"] = int(payload.get("_event_revision", -1))
		pending["deadline"] = Time.get_ticks_msec() + 10000
		if _snapshot_confirms_command(pending, room): _pending_commands.erase(event_request_id)
		else:
			_pending_commands[event_request_id] = pending
			_request_snapshot()
	if kind == "battle.combo_resolved" and payload.get("_request_id", "") == _pending_play.get("request_id", ""):
		_pending_play = {}
	if kind in ["room.snapshot", "room.started"]:
		var snapshot: Dictionary = payload.get("snapshot", {}) if kind == "room.started" else payload
		if (not gateway.token.is_empty() or snapshot.has("config_version")) and not validate_config(str(snapshot.get("config_version", "")), "房间"): return
	_sound_event(kind, payload)
	if kind == "battle.target_selected" and payload.get("battle_id", "") == room.get("pve", {}).get("battle_id", ""): clear_combat_preview()
	if kind in ["room.moved", "battle.target_selected", "duel.leave_ack", "duel.escape_started", "duel.escape_failed", "duel.escape_interrupted", "duel.started", "duel.ended", "action.potion_used", "relic.taken", "relic.replaced", "reward.choice_claimed", "action.extract_started", "action.extract_cancelled", "action.extract_completed", "action.spring_started", "action.spring_cancelled", "action.spring_completed"] and event_request_id.is_empty():
		_request_snapshot()
	match kind:
		"room.snapshot":
			_snapshot_request_pending = false
			for request_id in _pending_commands.keys():
				var pending: Dictionary = _pending_commands[request_id]
				if pending.get("confirmed", false) and _snapshot_confirms_command(pending, payload): _pending_commands.erase(request_id)
			if room.get("room_id", "") != payload.get("room_id", ""): relic_details = {}
			_sound_snapshot(payload, payload)
			_sync_pve_target()
			var hand: Array = room.get("player", {}).get("hand", []).map(func(card): return card.instance_id)
			selected_cards = selected_cards.filter(func(id): return id in hand)
			_refresh_combat_preview()
			ready_prompt = {}
			if not _queued_command.is_empty() and (not _queued_command.has("snapshot_id") or payload.get("_request_id", "") == _queued_command.snapshot_id):
				var queued: Dictionary = _queued_command
				_queued_command = {}
				if Time.get_ticks_msec() <= _queue_deadline and queued.get("room_id", room.get("room_id", "")) == room.get("room_id", "") and allowed(queued.action) and _intent_valid(queued.action, queued.payload): _send_queued_command(queued)
				else: notice.emit("当前状态已改变，请重新选择操作")
		"room.started":
			clear_combat_preview()
			_sound_snapshot(payload.get("snapshot", {}), payload)
			_sync_pve_target()
			ready_prompt = {}
			gateway.room_id = payload.room_id
			gateway.room_revision = room.get("room_revision", 0)
		"map.player_count":
			if not room.is_empty(): room["map_player_count"] = int(payload.get("player_count", 0))
		"match.found", "room.ready_required", "room.ready_accepted": ready_prompt = payload
		"room.ready_removed":
			ready_prompt = {}
			ticket = {}
			preparation = {}
			lobby["activePreparation"] = null
			# Preparation locking removes equipped items from the inventory cache.
			# The server releases them on timeout; reload their saved item details.
			refresh_cache("inventory")
			notice.emit("确认超时，席位已释放")
		"settlement.ready", "match.settled": _load_settlement(payload.settlement_id)
		"battle.combo_resolved", "combat.hit":
			if _feedback_is_current(payload):
				var had_preview := not combat_preview.is_empty() or not _preview_request.is_empty()
				clear_combat_preview()
				combat_feedback.emit(payload)
				_sound_combat(kind, payload)
				# Server presentation events use a nonempty synthetic request ID.
				_request_snapshot()
				if had_preview: changed.emit()
			return
		"combat.previewed": _accept_combat_preview(payload)
		"combat.preview_rejected":
			if payload.get("_request_id", "") == _preview_request.get("request_id", ""):
				_preview_request = {}
				_preview_deadline = 0
		"inventory.changed":
			if str(payload.get("action", "")) == "shop.refresh":
				refresh_cache("shop")
				shop_refreshed.emit(payload)
				return
			if str(payload.get("action", "")).begins_with("market."):
				_apply_market_event(payload)
				return
			if str(payload.get("action", "")) == "admin.refresh":
				refresh_lobby()
				notice.emit("管理员更新已同步。")
				player_data_invalidated.emit()
			else:
				if event_request_id.is_empty(): _request_snapshot()
		"relic.contents": relic_details[str(payload.get("pile_id", ""))] = payload
	changed.emit()

func _apply_market_event(payload: Dictionary) -> void:
	var wire: Dictionary = payload.get("listing", {})
	if wire.is_empty():
		refresh_cache("market")
		return
	var item_wire: Dictionary = wire.get("equipment", {})
	var item := {
		"instanceId": str(item_wire.get("instance_id", "")), "slot": str(item_wire.get("slot", "")),
		"quality": str(item_wire.get("quality", "")), "level": int(item_wire.get("level", 0)),
		"isBound": bool(item_wire.get("is_bound", false)), "location": str(item_wire.get("location", "")),
		"version": int(item_wire.get("version", 0)), "element": str(item_wire.get("element", "")),
		"effectAffix": str(item_wire.get("effect_affix", "")), "secondaryTrait": str(item_wire.get("secondary_trait", ""))
	}
	var listing_id := str(wire.get("listing_id", ""))
	if listing_id.is_empty(): return
	var entry := {
		"listingId": listing_id, "sellerId": str(wire.get("seller_id", "")),
		"equipmentId": str(wire.get("equipment_id", "")), "priceGold": int(wire.get("price_gold", 0)),
		"status": str(wire.get("status", "")), "version": int(wire.get("version", 0)),
		"createdAt": Time.get_datetime_string_from_unix_time(int(int(wire.get("created_at_unix_ms", 0)) / 1000)) + "Z",
		"expiresAt": Time.get_datetime_string_from_unix_time(int(int(wire.get("expires_at_unix_ms", 0)) / 1000)) + "Z",
		"equipment": item
	}
	var updated: Array = lobby.get("market", []).duplicate(true)
	for existing in updated:
		if str(existing.get("listingId", "")) == listing_id and int(existing.get("version", 0)) > int(entry.version): return
	updated = updated.filter(func(existing): return str(existing.get("listingId", "")) != listing_id)
	if entry.status == "Active" and int(wire.get("expires_at_unix_ms", 0)) > Time.get_unix_time_from_system() * 1000:
		updated.push_front(entry)
	update_cache("market", updated)
	if entry.sellerId != str(lobby.get("player", {}).get("userId", "")): return
	if payload.has("seller_gold_after"):
		var wallet: Dictionary = lobby.get("wallet", {}).duplicate(true)
		wallet["gold"] = int(payload.seller_gold_after)
		update_cache("wallet", wallet)
	if str(payload.get("action", "")) not in ["market.listed", "market.cancelled", "market.expired"]: return
	var account_inventory: Dictionary = lobby.get("inventory", {}).duplicate(true)
	if account_inventory.is_empty(): return
	var items: Array = account_inventory.get("equipments", []).duplicate(true)
	items = items.filter(func(value): return str(value.get("instanceId", "")) != entry.equipmentId)
	if str(payload.get("action", "")) in ["market.cancelled", "market.expired"]: items.append(item)
	account_inventory["equipments"] = items
	var count := 0
	for value in items:
		if str(value.get("location", "")) == "Inventory": count += 1
	var summary: Dictionary = account_inventory.get("summary", {}).duplicate(true)
	summary["equipmentCount"] = count
	summary["freeSlots"] = maxi(0, int(summary.get("capacity", 50)) - count)
	account_inventory["summary"] = summary
	update_cache("inventory", account_inventory)

func _on_gateway_telemetry(sample: Dictionary) -> void:
	if sample.get("type", "") == "rtt":
		network_rtt_ms = int(sample.get("duration_ms", -1))
	elif sample.get("type", "") == "realtime":
		last_command_latency_ms = int(sample.get("duration_ms", -1))
	network_telemetry.emit(sample)

func _intent_valid(action: String, payload: Dictionary) -> bool:
	if action == "monster.choose":
		var pool: Dictionary = room.get("player", {}).get("monster_pool", {})
		if not pool.get("pending", []).any(func(card): return card.get("instance_id", "") == payload.get("candidate_id", "")): return false
		if payload.has("replace_instance_id"):
			return pool.get("active", []).any(func(card): return card.get("instance_id", "") == payload.replace_instance_id)
		return true
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
	if settlement.get("settlementId", "") == id or _settlement_loading == id or _settlement_ack_pending_id == id: return
	var expected_match_id := str(room.get("match_id", ""))
	if expected_match_id.is_empty(): return
	_settlement_loading = id
	var generation: int = gateway.session_generation
	var result: Dictionary = await gateway.request("/api/v1/settlements/" + id)
	if generation != gateway.session_generation: return
	if str(room.get("match_id", "")) != expected_match_id:
		_settlement_loading = ""
		return
	if _settlement_ack_pending_id == id:
		_settlement_loading = ""
		return
	if result.ok and result.data is Dictionary and str(result.data.get("matchId", "")) == expected_match_id and str(result.data.get("settlementId", "")) == id:
		settlement = result.data
	_settlement_loading = ""
	changed.emit()

func _poll_ready_settlement() -> void:
	if _settlement_polling or not settlement.is_empty() or not _settlement_ack_pending_id.is_empty(): return
	var match_id := str(room.get("match_id", _settlement_recovery_match_id))
	if match_id.is_empty() or gateway == null or gateway.token.is_empty(): return
	_settlement_polling = true
	_settlement_poll_at = Time.get_ticks_msec() + 2500
	var generation: int = gateway.session_generation
	# Bootstrap exposes only settlements whose asset holds have finished committing.
	var result: Dictionary = await gateway.request("/api/v1/bootstrap", HTTPClient.METHOD_GET, null, [0, 502, 503, 504])
	if generation != gateway.session_generation: return
	_settlement_polling = false
	if str(room.get("match_id", _settlement_recovery_match_id)) != match_id or not settlement.is_empty(): return
	if not result.ok or not result.data is Dictionary:
		settlement_query_failed = true
		changed.emit()
		return
	var was_failed := settlement_query_failed
	settlement_query_failed = false
	var ready: Variant = result.data.get("unfinishedSettlement")
	if ready is Dictionary and str(ready.get("matchId", "")) == match_id:
		settlement = ready
		_settlement_recovery_match_id = ""
		changed.emit()
	elif was_failed:
		changed.emit()

func retry_settlement() -> void:
	if str(room.get("player", {}).get("phase", "")) not in ["Extracted", "Dead"] and _settlement_recovery_match_id.is_empty(): return
	_poll_ready_settlement()

func acknowledge_settlement() -> bool:
	if settlement.is_empty() or busy: return false
	var acknowledged: Dictionary = settlement.duplicate(true)
	var previous_room: Dictionary = room.duplicate(true)
	var previous_ready_prompt: Dictionary = ready_prompt.duplicate(true)
	var previous_preparation: Dictionary = preparation.duplicate(true)
	var previous_ticket: Dictionary = ticket.duplicate(true)
	var previous_selected_cards: Array = selected_cards.duplicate(true)
	var previous_relic_details: Dictionary = relic_details.duplicate(true)
	var previous_combat_preview: Dictionary = combat_preview.duplicate(true)
	var previous_queued_command: Dictionary = _queued_command.duplicate(true)
	var previous_pending_play: Dictionary = _pending_play.duplicate(true)
	var previous_pending_commands: Dictionary = _pending_commands.duplicate(true)
	var previous_latest_commands: Dictionary = _latest_commands.duplicate(true)
	var previous_lobby_settlement: Variant = lobby.get("unfinishedSettlement")
	var previous_lobby_match: Variant = lobby.get("unfinishedMatch")
	var previous_gateway_room_id: String = gateway.room_id
	var previous_gateway_revision: int = gateway.room_revision
	var settlement_id: String = str(acknowledged.get("settlementId", ""))
	if settlement_id.is_empty(): return false
	busy = true
	_settlement_ack_pending_id = settlement_id
	settlement = {}
	room = {}
	ready_prompt = {}
	selected_cards.clear()
	relic_details = {}
	clear_combat_preview()
	_queued_command = {}
	_pending_play = {}
	_pending_commands.clear()
	_latest_commands.clear()
	preparation = {}
	ticket = {}
	lobby["unfinishedSettlement"] = null
	lobby["unfinishedMatch"] = null
	gateway.room_id = ""
	gateway.room_revision = 0
	changed.emit()
	var generation: int = gateway.session_generation
	var result: Dictionary = await gateway.request("/api/v1/settlements/" + settlement_id + "/acknowledge", HTTPClient.METHOD_POST, {})
	if generation != gateway.session_generation: return false
	if not result.ok and int(result.get("status", 0)) in [0, 200, 502, 503, 504]:
		# A lost write response can follow a committed acknowledgement. Verify the
		# account's authoritative unfinished state before restoring an old receipt.
		var verified: Dictionary = await gateway.request("/api/v1/bootstrap", HTTPClient.METHOD_GET, null, [0, 401, 503])
		if generation != gateway.session_generation: return false
		if verified.ok and verified.data is Dictionary and str(verified.data.get("configVersion", "")) == str(CATALOG.data.version) and verified.data.has("unfinishedSettlement") and verified.data.has("unfinishedMatch") and verified.data.has("activePreparation"):
			if verified.data.unfinishedSettlement == null and verified.data.unfinishedMatch == null and verified.data.activePreparation == null:
				result = {"ok": true, "status": 200, "acknowledgement_verified_by_bootstrap": true}
	if generation != gateway.session_generation: return false
	if result.ok:
		_settlement_recovery_match_id = ""
		_settlement_loading = ""
		_settlement_polling = false
		_settlement_poll_at = 0
		settlement_query_failed = false
		await refresh_lobby()
	else:
		settlement = acknowledged
		room = previous_room
		ready_prompt = previous_ready_prompt
		preparation = previous_preparation
		ticket = previous_ticket
		selected_cards = previous_selected_cards
		relic_details = previous_relic_details
		combat_preview = previous_combat_preview
		_queued_command = previous_queued_command
		_pending_play = previous_pending_play
		_pending_commands = previous_pending_commands
		_latest_commands = previous_latest_commands
		lobby["unfinishedSettlement"] = previous_lobby_settlement
		lobby["unfinishedMatch"] = previous_lobby_match
		gateway.room_id = previous_gateway_room_id
		gateway.room_revision = previous_gateway_revision
		notice.emit("结算确认失败，请重试")
	if generation != gateway.session_generation: return false
	_settlement_ack_pending_id = ""
	busy = false
	changed.emit()
	return result.ok
