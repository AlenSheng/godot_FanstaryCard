extends SceneTree

var game: Node
var account_ui: Control
var checks: Dictionary = {}
var late_response: Dictionary = {}

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	game = root.get_node("Game")
	var base := OS.get_environment("FANTASYCARD_SESSION_TEST_URL")
	if not base.begins_with("http://127.0.0.1:"):
		quit(2)
		return
	game.gateway.persist_session = false
	game.gateway.device_id = "isolated-session-fixture"
	account_ui = load("res://ui/main.gd").new()
	game.changed.connect(account_ui._sync_account_session)
	await _check_account_switch(base)
	await game.login(base, "Session fixture")
	_stop_socket()
	checks.login = not game.lobby.is_empty() and not game.gateway.token.is_empty()
	game.room = {"room_id": "stale-room"}
	game.selected_cards = ["stale-card"]
	var unauthorized: Dictionary = await game.gateway.request("/unauthorized")
	checks.unauthorized = not unauthorized.ok and game.lobby.is_empty() and game.room.is_empty() and game.selected_cards.is_empty() and not game.gateway.reconnect_enabled
	await game.login(base, "Session fixture")
	_stop_socket()
	checks.relogin = not game.lobby.is_empty() and game.authentication_reason.is_empty()
	var proto = load("res://network/protobuf.gd").new()
	game.gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "session.replaced", "sequence": 1, "payload": proto.encode("SessionReplacedEvent", {"reason": "replacement fixture"})}))
	checks.replaced = game.lobby.is_empty() and game.gateway.token.is_empty() and not game.gateway.reconnect_enabled
	await game.login(base, "Session fixture")
	_stop_socket()
	_delayed_request()
	await create_timer(0.05).timeout
	game.gateway.end_session("fixture expiry")
	await game.login(base, "Session fixture")
	_stop_socket()
	var generation: int = game.gateway.session_generation
	while late_response.is_empty(): await process_frame
	checks.stale_response = not late_response.ok and late_response.get("stale_session", false) and not game.lobby.is_empty() and generation == game.gateway.session_generation
	await game.login(base + "/mismatch", "Session fixture")
	checks.server_mismatch = game.lobby.is_empty() and not game.configuration_error.is_empty() and game.gateway.token.is_empty()
	await game.login(base + "/bootstrap-mismatch", "Session fixture")
	checks.bootstrap_mismatch = game.lobby.is_empty() and not game.configuration_error.is_empty() and game.gateway.token.is_empty()
	await game.login(base, "Session fixture")
	_stop_socket()
	checks.recovered_matching_config = not game.lobby.is_empty() and game.configuration_error.is_empty()
	game.logout()
	checks.logout = game.lobby.is_empty() and game.gateway.token.is_empty() and not game.busy
	game.changed.disconnect(account_ui._sync_account_session)
	account_ui.free()
	var ok := checks.values().all(func(value): return value == true)
	print(JSON.stringify({"session_integration": true, "ok": ok, "checks": checks}))
	quit(0 if ok else 1)

func _check_account_switch(base: String) -> void:
	await game.login(base, "  Account A  ")
	_stop_socket()
	var uid_a: String = game.gateway.authenticated_user_id
	checks.account_name_remembered = game.gateway.local_account_name == "Account A" and account_ui._login_name == "Account A"
	var update: Dictionary = await game.gateway.request("/fixture/account-progress", HTTPClient.METHOD_POST, {"gold": 37, "selectedClass": "Priest"})
	await game.refresh_lobby()
	checks.account_a_progress = update.ok and game.lobby.get("wallet", {}).get("gold") == 37 and game.hero_class == "Priest"
	game.room = {"room_id": "account-a-room"}
	game.preparation = {"preparationId": "account-a-prep"}
	game.selected_cards = ["account-a-card"]
	game.relic_details = {"account-a-relic": {}}
	game.gateway.room_id = "account-a-room"
	game.gateway.last_sequence = 41
	game.gateway.room_revision = 5
	account_ui.screen = "shop"
	account_ui.owned = [{"cardId": "account-a-card"}]
	account_ui.inventory = {"equipments": ["account-a-item"]}
	account_ui.shop = {"products": ["account-a-product"]}
	account_ui.listings = [{"sellerId": uid_a}]
	account_ui.deck_draft = ["account-a-card"]
	account_ui.gear_draft = ["account-a-item"]
	account_ui.bag_tier = "Top"
	account_ui.potion_count = 3
	account_ui._enhancement_quote = {"fragmentCost": 7}
	account_ui.set_meta("inventory_selected", "account-a-item")
	var old_dialog := ConfirmationDialog.new()
	account_ui.add_child(old_dialog)
	await game.login(base, "Account B")
	_stop_socket()
	var uid_b: String = game.gateway.authenticated_user_id
	checks.changed_name_new_uid = not uid_a.is_empty() and not uid_b.is_empty() and uid_a != uid_b
	checks.new_account_fresh_progress = game.lobby.get("wallet", {}).get("gold") == 0 and game.hero_class == "Mage"
	checks.account_store_cleared = game.room.is_empty() and game.preparation.is_empty() and game.selected_cards.is_empty() and game.relic_details.is_empty()
	checks.account_replay_cleared = game.gateway.room_id.is_empty() and game.gateway.last_sequence == 0 and game.gateway.room_revision == 0
	checks.account_ui_cleared = account_ui.screen == "hall" and account_ui.owned.is_empty() and account_ui.inventory.is_empty() and account_ui.shop.is_empty() and account_ui.listings.is_empty() and account_ui.deck_draft.is_empty() and account_ui.gear_draft.is_empty() and account_ui.bag_tier == "Free" and account_ui.potion_count == 0 and account_ui._enhancement_quote.is_empty() and not account_ui.has_meta("inventory_selected") and not is_instance_valid(old_dialog)
	await game.login(base, "  account a  ")
	_stop_socket()
	checks.same_name_restores_uid_and_progress = game.gateway.authenticated_user_id == uid_a and game.lobby.get("wallet", {}).get("gold") == 37 and game.hero_class == "Priest"
	checks.saved_name_uses_server_spelling = game.gateway.local_account_name == "Account A" and account_ui._login_name == "Account A"
	var generation: int = game.gateway.session_generation
	await game.login(base, " \t ")
	checks.empty_name_keeps_current_session = generation == game.gateway.session_generation and game.gateway.authenticated_user_id == uid_a and not game.gateway.token.is_empty()
	var header: Control = load("res://ui/reference_ui.gd").new()
	header.host = account_ui
	header._header()
	checks.account_identity_visible = header.get_node("AccountIdentity").text.contains(uid_a) and header.get_node("AccountIdentity").text.contains("Account A")
	header.get_node("SwitchAccountButton").pressed.emit()
	checks.switch_account_button = game.lobby.is_empty() and game.gateway.token.is_empty() and account_ui._login_name == "Account A"
	header.free()
	await game.login(base, "Unavailable fixture")
	checks.failed_name_not_remembered = game.gateway.local_account_name == "Account A" and game.gateway.token.is_empty() and game.lobby.is_empty()

func _stop_socket() -> void:
	game.gateway.reconnect_enabled = false
	game.gateway.socket.close()

func _delayed_request() -> void:
	late_response = await game.gateway.request("/late-unauthorized")
