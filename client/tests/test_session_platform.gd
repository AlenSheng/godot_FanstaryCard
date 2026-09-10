extends RefCounted

func run_test() -> Dictionary:
	var Gateway = load("res://network/gateway.gd")
	var Store = load("res://state/game_store.gd")
	var PlatformService = load("res://platform/platform_service.gd")
	var Proto = load("res://network/protobuf.gd")
	var gateway = Gateway.new()
	gateway.persist_session = false
	var store = Store.new()
	store.gateway = gateway
	gateway.authentication_required.connect(store._on_authentication_required)
	var platform = PlatformService.new()
	store.platform = platform
	var ok: bool = not platform.login_unavailable_reason().is_empty()
	ok = ok and Gateway.parse_expiry("2030-01-01T08:00:00.000+08:00") == Gateway.parse_expiry("2030-01-01T00:00:00Z")
	ok = ok and not gateway.accept_session("", "2030-01-01T00:00:00Z", "a")
	ok = ok and not gateway.accept_session("ticket", "2000-01-01T00:00:00Z", "a")
	ok = ok and gateway.accept_session("token-a", "2030-01-01T00:00:00Z", "a")
	gateway.room_id = "unfinished"
	gateway.last_sequence = 20
	gateway.room_revision = 4
	gateway.online = true
	gateway.reconnect_enabled = true
	store.lobby = {"player": {"userId": "a"}}
	store.room = {"room_id": "unfinished"}
	store.preparation = {"preparationId": "old"}
	store.ticket = {"ticketId": "old"}
	store.selected_cards = ["old"]
	store.relic_details = {"old": {}}
	store._queued_command = {"action": "battle.play_cards"}
	var proto = Proto.new()
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "session.replaced", "sequence": 21, "payload": proto.encode("SessionReplacedEvent", {"reason": "new connection"})}))
	ok = ok and gateway.token.is_empty() and not gateway.online and not gateway.reconnect_enabled
	ok = ok and store.lobby.is_empty() and store.room.is_empty() and store.preparation.is_empty() and store.ticket.is_empty()
	ok = ok and store.selected_cards.is_empty() and store._queued_command.is_empty() and store.relic_details.is_empty()
	ok = ok and not store.authentication_reason.is_empty() and gateway.room_id == "unfinished" and gateway.last_sequence == 20
	gateway.begin_sign_in(gateway.base_url)
	ok = ok and gateway.accept_session("new-token-a", "2030-01-01T00:00:00Z", "a") and gateway.last_sequence == 20
	gateway.begin_sign_in(gateway.base_url)
	ok = ok and gateway.accept_session("token-b", "2030-01-01T00:00:00Z", "b") and gateway.last_sequence == 0 and gateway.room_id.is_empty()
	var version: String = str(Store.CATALOG.data.version)
	ok = ok and store.validate_config(version, "test") and store._preparation_config_valid({"snapshot": {"configVersion": version}})
	store.lobby = {"player": {"userId": "b"}}
	store.room = {"allowed_actions": ["battle.play_cards"]}
	gateway.online = true
	ok = ok and not store.validate_config("outdated-package", "test") and not store.allowed("battle.play_cards")
	ok = ok and store.lobby.is_empty() and gateway.token.is_empty() and not store.configuration_error.is_empty()
	store.configuration_error = ""
	gateway.accept_session("token-b", "2030-01-01T00:00:00Z", "b")
	gateway.token_expires_at = Time.get_unix_time_from_system() - 1
	gateway._process(0.0)
	ok = ok and gateway.token.is_empty() and not gateway.reconnect_enabled
	platform._ticket_pending = true
	platform._ticket_handle = 7
	platform._on_web_api_ticket(8, 1, 2, PackedByteArray([1, 2]))
	ok = ok and platform._ticket_pending and platform._ticket_result.is_empty()
	platform._on_web_api_ticket(7, 1, 5, PackedByteArray([1, 2]))
	ok = ok and not platform._ticket_result.ok
	platform._ticket_pending = true
	platform._on_web_api_ticket(7, 1, 2, PackedByteArray([1, 2, 3]))
	ok = ok and platform._ticket_result.ok and platform._ticket_result.ticket == "0102"
	platform.release_ticket()
	ok = ok and platform._ticket_handle == 0 and platform._ticket_result.is_empty()
	store.free()
	gateway.free()
	platform.free()
	return {"ok": ok, "message": "Session replacement/expiry clears UI and stops retries; explicit relogin restores only same-user cursor; config mismatch blocks entry; Steam failure and ticket callbacks validated"}
