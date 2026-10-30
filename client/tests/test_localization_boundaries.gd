extends RefCounted

const P = preload("res://ui/palette.gd")
const RemoteCopy = preload("res://ui/remote_copy.gd")
const ReferenceUI = preload("res://ui/reference_ui.gd")
const Exploration = preload("res://ui/exploration_view.gd")
const InventoryView = preload("res://ui/inventory_view.gd")
const Store = preload("res://state/game_store.gd")
const LOCALES := ["zh-CN", "en", "es"]
const AUTHORED_NAME := "Fire  Gold / 装备"
const BAN_DETAIL := "Fire  Gold: 装备\nmaintenance / 管理员说明"

## Exercise Main's real presentation methods without creating its game shell,
## attaching session callbacks, starting music, or clearing shared asset caches.
class QuietMain extends "res://ui/main.gd":
	func _ready() -> void:
		set_process(false)
	func _process(_delta: float) -> void:
		pass
	func _notification(_what: int) -> void:
		pass
	func _exit_tree() -> void:
		pass

## The actual store handles the authentication signal, while this boundary owns
## no HTTP client, socket, persisted session, or platform service.
class RecordingGateway extends Node:
	signal authentication_required(reason: String)
	var last_reason := ""
	func end_session(reason: String, notify: bool = true) -> void:
		last_reason = reason
		if notify: authentication_required.emit(reason)

var _checks: Dictionary = {}
var _errors: Array[Dictionary] = []

func run_test() -> Dictionary:
	_checks = {}
	_errors = []
	var tree := Engine.get_main_loop() as SceneTree
	if tree == null:
		return {"ok": false, "checks": {}, "errors": [{"check": "SceneTree is available"}]}
	var saved := {"language": P.language(), "room": Game.room, "mail": Game.mail,
		"configuration_error": Game.configuration_error, "relic_details": Game.relic_details}
	var host := QuietMain.new()
	host.name = "LocalizationBoundaryTestHost"
	tree.root.add_child(host)
	# No test callback is pressed. Also disable Game.allowed at its first guard,
	# so construction never depends on the live gateway's presence or readiness.
	Game.configuration_error = "localization-boundary-test"
	Game.relic_details = {}
	for locale in LOCALES:
		P.set_language(locale)
		_check(locale + "/registered", P.language() == locale)
		_check_bans(host, locale)
		_check_mail(host, locale, false)
		_check_mail(host, locale, true)
		_check_mail(host, locale, false, "系统通知")
		_check_mail(host, locale, false, "System Notice")
		_check_duel(host, locale)
		_check_relics(host, locale)
	_check_persistent_configuration_messages(host)
	Game.room = saved.room
	Game.mail = saved.mail
	Game.configuration_error = saved.configuration_error
	Game.relic_details = saved.relic_details
	P.set_language(saved.language)
	host.free()
	return {"ok": _errors.is_empty(), "checks": _checks, "errors": _errors,
		"scope": "Real ban dialog, mail list/detail, duel and relic text construction plus real store validation across zh-CN/en/es. No network, Steam, rendered-frame, or whole-language acceptance claim."}

func _check(name: String, passed: bool, observed: Variant = null) -> void:
	_checks[name] = passed
	if not passed: _errors.append({"check": name, "observed": observed})

func _view(host: Control) -> Control:
	var view = ReferenceUI.new()
	view.host = host
	view.theme = P.theme()
	host.add_child(view)
	return view

func _texts(node: Node) -> Array[String]:
	var result: Array[String] = []
	if node is Label: result.append(node.text)
	for child in node.get_children(): result.append_array(_texts(child))
	return result

func _dialogs(host: Node) -> Array[AcceptDialog]:
	var result: Array[AcceptDialog] = []
	for child in host.get_children():
		if child is AcceptDialog: result.append(child)
	return result

func _check_bans(host: Control, locale: String) -> void:
	# This literal is an existing server wire reason, not authored interface copy.
	var raw_wire := "账号已被封禁：" + BAN_DETAIL
	var reasons := {"server_wire": raw_wire}
	for source_locale in LOCALES:
		var source_label := str(P.languages()[source_locale].strings.ui_account_banned)
		reasons["label_" + source_locale] = source_label + ":" + BAN_DETAIL
	for source in reasons:
		var reason := str(reasons[source])
		var parsed: Dictionary = RemoteCopy.account_ban(reason)
		_check(locale + "/ban/" + source + "/raw_detail", parsed.has("reason") and parsed.get("reason") == BAN_DETAIL, parsed)
		host._show_ban_dialog(reason)
		var dialogs := _dialogs(host)
		_check(locale + "/ban/" + source + "/dialog_exists", dialogs.size() == 1, dialogs.size())
		if dialogs.size() == 1:
			_check(locale + "/ban/" + source + "/localized_title", dialogs[0].title == P.localized("ui_account_banned"), dialogs[0].title)
			_check(locale + "/ban/" + source + "/dialog_keeps_detail", dialogs[0].dialog_text.contains(BAN_DETAIL), dialogs[0].dialog_text)
		for dialog in dialogs: dialog.free()
	for index in range(3):
		var ordinary: String = ["账号已在其他窗口连接，请重新登录", "Connection replaced", "maintenance: " + raw_wire][index]
		_check(locale + "/ordinary_session/" + str(index) + "/not_a_ban", RemoteCopy.account_ban(ordinary).is_empty())
		host._show_ban_dialog(ordinary)
		var unexpected := _dialogs(host)
		_check(locale + "/ordinary_session/" + str(index) + "/no_dialog", unexpected.is_empty())
		for dialog in unexpected: dialog.free()

func _check_mail(host: Control, locale: String, explicit_translation: bool, special_title: String = "") -> void:
	var kind := "translation" if explicit_translation else "legacy"
	if not special_title.is_empty(): kind += "/" + special_title
	var authored_title := "装备维护公告 / Fire  Gold" if special_title.is_empty() else special_title
	var authored_sender := AUTHORED_NAME
	var authored_body := "Fire  Gold: 装备维护正文\nKeep this administrator-authored text."
	var item := {"id": "localization-boundary-mail", "title": authored_title,
		"sender": authored_sender, "body": authored_body, "read": true, "attachments": []}
	if explicit_translation:
		item["title"] = "Original title"
		item["sender"] = "Original sender"
		item["body"] = "Original body"
		item["translations"] = {locale: {"title": authored_title, "sender": authored_sender, "body": authored_body}}
	Game.mail = {"items": [item], "unreadCount": 0}
	var view := _view(host)
	var list := VBoxContainer.new()
	view.add_child(list)
	view._build_mail_rows(list)
	var list_title := list.get_node_or_null("MailRow_localization-boundary-mail/MailOpenArea/MailTitle") as Label
	_check(locale + "/mail/" + kind + "/list_keeps_title", list_title != null and list_title.text.contains(authored_title), list_title.text if list_title != null else "missing")
	var detail := Control.new()
	view.add_child(detail)
	view._mail_detail_panel(detail, item)
	var labels := _texts(detail)
	_check(locale + "/mail/" + kind + "/detail_keeps_title", labels.has(authored_title), labels)
	_check(locale + "/mail/" + kind + "/detail_keeps_sender", labels.has(P.localized("sender") + ": " + authored_sender), labels)
	_check(locale + "/mail/" + kind + "/detail_keeps_body", labels.has(authored_body), labels)
	view.free()

func _duel_state() -> Dictionary:
	return {"room_id": "localization-boundary-room", "allowed_actions": [],
		"player": {"player_id": "self", "hero_class": "Mage", "phase": "Pvp",
			"combat": {"hp": 70, "maximum_hp": 70}, "hand": []},
		"duel": {"duel_id": "localization-boundary-duel", "opponent_id": "opponent",
			"opponent_name": AUTHORED_NAME, "opponent_class": "Mage",
			"opponent": {"hp": 70, "maximum_hp": 70}}}

func _check_duel(host: Control, locale: String) -> void:
	Game.room = _duel_state()
	host._combat_panels.clear()
	var view := _view(host)
	Exploration._duel(view, host, Game.room)
	var label := view.get_node_or_null("DuelOpponentTitle") as Label
	var expected := AUTHORED_NAME + " · " + P.localized("battle_class_mage")
	_check(locale + "/duel/name_is_verbatim", label != null and label.text == expected, label.text if label != null else "missing")
	_check(locale + "/duel/tooltip_is_verbatim", label != null and label.tooltip_text == expected, label.tooltip_text if label != null else "missing")
	view.free()
	host._combat_panels.clear()

func _check_relics(host: Control, locale: String) -> void:
	var pile_id := "localization-boundary-pile"
	var state := {"room_id": "localization-boundary-room", "allowed_actions": [],
		"player": {"player_id": "self", "hero_class": "Mage", "phase": "ActionBar",
			"combat": {"hp": 70, "maximum_hp": 70}, "inventory": [], "inventory_capacity": 0},
		"current_cell": {"relic_piles": [{"pile_id": pile_id, "owner_name": AUTHORED_NAME, "version": 1}]}}
	Game.room = state
	host._combat_panels.clear()
	var action_view := _view(host)
	Exploration._actions(action_view, host, state)
	var action_expected := P.localized("exploration_relic_owner") % AUTHORED_NAME
	var action_labels := _texts(action_view)
	_check(locale + "/relic/action_owner_is_verbatim", action_labels.has(action_expected), action_labels)
	action_view.free()
	host._combat_panels.clear()
	host.set_meta("relic_pile", pile_id)
	var inventory_view := _view(host)
	InventoryView.build(inventory_view, host, state)
	var owner_expected := AUTHORED_NAME + P.localized("relic_owner_suffix")
	var inventory_labels := _texts(inventory_view)
	_check(locale + "/relic/inventory_owner_is_verbatim", inventory_labels.has(owner_expected), inventory_labels)
	inventory_view.free()
	host.remove_meta("relic_pile")

func _check_persistent_configuration_messages(host: Control) -> void:
	var store: Node = Store.new()
	var gateway := RecordingGateway.new()
	store.gateway = gateway
	gateway.authentication_required.connect(store._on_authentication_required)
	# The nonempty version deliberately contains recognized aliases. Version
	# identifiers must survive translation while an absent version is a UI label.
	for origin_locale in LOCALES:
		for source_key in ["server", "hall", "room", "preparation"]:
			for server_version in ["Fire  Gold 装备:v0", ""]:
				P.set_language(origin_locale)
				var mismatch: bool = not store.validate_config(server_version, P.localized(source_key))
				var case_name: String = origin_locale + "/" + source_key + ("/version" if not server_version.is_empty() else "/missing_version")
				_check("config/" + case_name + "/real_validation_rejected", mismatch)
				_check("config/" + case_name + "/signal_populated_persistent_fields", not store.configuration_error.is_empty() and store.authentication_reason == gateway.last_reason and store.connection == gateway.last_reason)
				for target_locale in LOCALES:
					P.set_language(target_locale)
					var expected := P.localized("config_mismatch_details") % [P.localized(source_key), str(Store.CATALOG.data.version), server_version if not server_version.is_empty() else P.localized("version_missing")]
					for field in ["configuration_error", "authentication_reason", "connection"]:
						var raw_message := str(store.get(field))
						var label: Label = host._label(host, raw_message)
						_check("config/" + case_name + "/to_" + target_locale + "/" + field, label.text == expected, {"expected": expected, "actual": label.text})
						label.free()
	store.free()
	gateway.free()
