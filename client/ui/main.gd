extends Control

const P = preload("res://ui/palette.gd")
const Art = preload("res://ui/art.gd")
const CardView = preload("res://ui/card_view.gd")
const DeckBuilder = preload("res://ui/deck_builder_view.gd")
const ReferenceUI = preload("res://ui/reference_ui.gd")
const ConfirmationModalScene = preload("res://ui/confirmation_modal.tscn")
const BoundedBar = preload("res://ui/bounded_bar.gd")
const EquipmentDetails = preload("res://ui/equipment_details.gd")
const EquipmentCompareDialog = preload("res://ui/equipment_compare_dialog.gd")
const InventoryView = preload("res://ui/inventory_view.gd")
const CardDetails = preload("res://ui/card_details.gd")
const BattleDetails = preload("res://ui/battle_details.gd")
const AudioSettings = preload("res://ui/audio_settings.gd")
const TipsOverlay = preload("res://ui/tips_overlay.gd")
const CATALOG = preload("res://data/catalog.json")
const DESCRIPTIONS = preload("res://data/card_descriptions.json")
const UI_CONFIG = preload("res://data/ui_config.json")
var screen := "hall"
var content: VBoxContainer
var root_column: VBoxContainer
var status_label: Label
var toast_label: Label
var tips_overlay: CanvasLayer
var cards: Dictionary = {}
var owned: Array = []
var inventory: Dictionary = {}
var shop: Dictionary = {}
var listings: Array = []
var deck_draft: Array = []
var gear_draft: Array = []
var bag_tier := "Free"
var potion_count := 0
var edit_mode := false
var screen_loading := false
var _render_pending := false
var mail_modal_lock := false
var _midlayer_seen: Dictionary = {}
var _login_address := "http://127.0.0.1:5080"
var _login_name := ""
var _session_generation: int = -1
var _search := ""
var _combat_panels: Dictionary = {}
var _background: TextureRect
var _reference: Control
var _quality := ""
var _enhance_item := ""
var _market_item := ""
var _shop_inventory_ready := false
var _market_price := 100
var _view_cell := ""
var _codex_card := ""
var _codex_scroll := 0
var _codex_deck_scroll := 0
var _deck_builder_scroll := 0
var _equipment_scroll := 0
var _codex_ready := false
var _codex_mutating := false
var _enhancement_quote: Dictionary = {}
var _enhancement_quote_key := ""
var _game_title: Label

func _ready() -> void:
	theme = P.theme()
	for card in CATALOG.data.tables.Cards: cards[card.id] = card
	if not Game.gateway.base_url.strip_edges().is_empty(): _login_address = Game.gateway.base_url
	if not Game.gateway.local_account_name.is_empty(): _login_name = Game.gateway.local_account_name
	_session_generation = Game.gateway.session_generation
	Game.changed.connect(_schedule_render)
	Game.notice.connect(_toast)
	Game.authentication_required.connect(_show_ban_dialog)
	Game.combat_feedback.connect(_feedback)
	_build_shell()
	var audio_settings := AudioSettings.new()
	audio_settings.name = "AudioSettings"
	add_child(audio_settings)
	_sync_account_session()
	_render()

func _build_shell() -> void:
	var background := TextureRect.new()
	_background = background
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	background.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	background.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if ResourceLoader.exists("res://assets/scenes/camp_hall.png"):
		background.texture = load("res://assets/scenes/camp_hall.png")
		background.modulate = Color.WHITE
	add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right"]: margin.add_theme_constant_override("margin_" + side, 80)
	for side in ["top", "bottom"]: margin.add_theme_constant_override("margin_" + side, 48)
	add_child(margin)
	root_column = VBoxContainer.new()
	margin.add_child(root_column)
	var top := HBoxContainer.new()
	root_column.add_child(top)
	var game_title := _label(top, P.localized("game_title"), 38, P.GOLD)
	game_title.name = "GameTitle"
	_game_title = game_title
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(spacer)
	status_label = _label(top, "", 20, P.MUTED)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	root_column.add_child(scroll)
	content = VBoxContainer.new()
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(content)
	tips_overlay = TipsOverlay.new()
	tips_overlay.name = "TipsOverlay"
	add_child(tips_overlay)
	# Compatibility alias for existing UI checks; rendering and animation live in TipsOverlay.
	toast_label = tips_overlay.label

func _schedule_render() -> void:
	if mail_modal_lock: return
	_sync_account_session()
	if is_instance_valid(_game_title): _game_title.text = P.localized("game_title")
	if _render_pending: return
	_render_pending = true
	_render.call_deferred()

func _sync_account_session() -> void:
	if _session_generation != Game.gateway.session_generation:
		_session_generation = Game.gateway.session_generation
		_reset_account_ui()
	var lobby_cards: Variant = Game.lobby.get("cards", null)
	if lobby_cards is Array:
		owned = lobby_cards
		_codex_ready = true
	if not Game.lobby.is_empty() and not Game.gateway.token.is_empty() and not Game.gateway.local_account_name.is_empty():
		_login_name = Game.gateway.local_account_name

func _reset_account_ui() -> void:
	screen = "hall"
	owned = []
	inventory = {}
	shop = {}
	listings = []
	deck_draft = []
	gear_draft = []
	bag_tier = "Free"
	potion_count = 0
	edit_mode = false
	screen_loading = false
	_midlayer_seen.clear()
	_search = ""
	_quality = ""
	_enhance_item = ""
	_market_item = ""
	_market_price = 100
	_view_cell = ""
	_codex_card = ""
	_codex_scroll = 0
	_codex_deck_scroll = 0
	_deck_builder_scroll = 0
	_equipment_scroll = 0
	_codex_ready = false
	_codex_mutating = false
	_shop_inventory_ready = false
	_enhancement_quote = {}
	_enhancement_quote_key = ""
	_combat_panels.clear()
	if is_instance_valid(tips_overlay): tips_overlay.clear()
	for key in ["exploration_map_open", "inventory_open", "relic_pile", "inventory_selected", "relic_selected", "pending_move", "item_detail_scroll"]:
		if has_meta(key): remove_meta(key)
	# Account-bound dialogs must not retain actions against the next login.
	for child in get_children():
		if child is Window or child.name == "ConfirmationModal":
			remove_child(child)
			child.queue_free()

func _render() -> void:
	_render_pending = false
	var room_cell := "%s:%s:%s" % [Game.room.get("room_id", ""), Game.room.get("self", {}).get("row", -1), Game.room.get("self", {}).get("column", -1)]
	if room_cell != _view_cell or Game.room.get("player", {}).get("phase", "") != "ActionBar":
		set_meta("exploration_map_open", false)
		for key in ["inventory_open", "relic_pile", "inventory_selected", "relic_selected"]:
			if has_meta(key): remove_meta(key)
		if has_meta("pending_move"): remove_meta("pending_move")
	_view_cell = room_cell
	if is_instance_valid(_reference):
		remove_child(_reference)
		_reference.queue_free()
		_reference = null
	content.add_theme_constant_override("separation", 10 if not Game.room.is_empty() else 18)
	if not Game.room.is_empty():
		_background.texture = Art.texture("UI/Encounter/encounter_background.png")
		_background.modulate = Color(0.8, 0.8, 0.8)
	else:
		_background.texture = load("res://assets/scenes/camp_hall.png")
		_background.modulate = Color.WHITE
	_combat_panels = {}
	for node in content.get_children():
		content.remove_child(node)
		node.queue_free()
	status_label.text = P.localized_text(Game.connection)
	if not Game.lobby.is_empty(): status_label.text += P.localized_text("    金币 %s" % Game.lobby.get("wallet", {}).get("gold", 0))
	var use_reference: bool = not Game.lobby.is_empty() and Game.lobby.get("unfinishedMatch") == null
	if not Game.room.is_empty() or not Game.settlement.is_empty(): use_reference = true
	root_column.get_parent().visible = not use_reference
	if use_reference:
		var scene_path := "res://assets/scenes/dungeon_battle.png" if not Game.room.is_empty() else "res://assets/scenes/camp_hall.png"
		if ResourceLoader.exists(scene_path):
			_background.texture = load(scene_path)
			_background.modulate = Color.WHITE
		if screen in ["cards", "deck"] and Game.room.is_empty() and Game.settlement.is_empty():
			_background.texture = Art.texture("UI/CardCodex/card_codex_background_normal.png")
			_background.modulate = Color.WHITE
		_reference = ReferenceUI.new()
		add_child(_reference)
		_reference.build(self)
		return
	if not Game.settlement.is_empty():
		_settlement()
		return
	if not Game.room.is_empty():
		_room()
		return
	if Game.lobby.is_empty():
		_login()
		return
	if not Game.ready_prompt.is_empty():
		_ready_screen()
		return
	if Game.lobby.get("unfinishedMatch") != null:
		_label(content, "正在恢复上次探索…", 42, P.GOLD)
		_button(content, "重新连接", Game.gateway.connect_realtime)
		return
	_nav()
	if screen_loading:
		_label(content, "正在读取…", 32)
		return
	match screen:
		"hall": _hall()
		"prep": _preparation()
		"cards": _codex()
		"deck": _codex()
		"gear": _equipment()
		"shop": _shop()
		"market": _market()

func _label(parent: Node, text: String, size: int = 24, color: Color = P.PAPER) -> Label:
	var node := Label.new()
	var display_text := P.localized_text(text)
	var typeface := P.font_for_text(display_text, size)
	node.add_theme_font_override("font", typeface)
	node.text = display_text
	node.add_theme_font_size_override("font_size", size)
	node.add_theme_color_override("font_color", color)
	node.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	node.clip_text = true
	parent.add_child(node)
	P.fit_control_font(node, typeface, size)
	return node

func _button(parent: Node, text: String, callback: Callable, disabled: bool = false, key: String = "") -> Button:
	var button := Button.new()
	button.text = P.localized_text(text)
	button.disabled = disabled
	button.custom_minimum_size.y = 62
	button.clip_text = true
	button.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	button.pressed.connect(callback)
	var button_key := key if not key.is_empty() else ("UI/CardCodex/card_codex_action_button_orange.png" if _is_positive_button(text) else "UI/CardCodex/card_codex_action_button_blue.png")
	Art.button(button, button_key)
	parent.add_child(button)
	P.fit_control_font(button, P.font_for_text(button.text, 24), 24, 48.0)
	return button

func _is_positive_button(value: String) -> bool:
	for keyword in ["确认", "领取", "登录", "注册", "开始", "保存", "购买", "强化", "穿戴", "上架", "选择", "准备就绪", "探索准备"]:
		if value.contains(keyword): return true
	return false

func _panel(parent: Node, minimum_width: float = 0) -> VBoxContainer:
	var panel := PanelContainer.new()
	panel.custom_minimum_size.x = minimum_width
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel.add_theme_stylebox_override("panel", Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png"))
	parent.add_child(panel)
	var column := VBoxContainer.new()
	panel.add_child(column)
	return column

func _row(parent: Node) -> HBoxContainer:
	var row := HBoxContainer.new()
	parent.add_child(row)
	return row

func _login() -> void:
	_label(content, "混沌领域", 76, P.GOLD)
	_label(content, "搜寻遗物，组合五行，带着战利品归来。", 30)
	var row := _row(content)
	var panel := _panel(row, 680)
	_label(panel, "启程", 40)
	_label(panel, "账号名称", 22, P.MUTED)
	var name_input := LineEdit.new()
	name_input.text = _login_name
	name_input.placeholder_text = P.localized_text("输入唯一账号名称")
	name_input.max_length = 20
	name_input.text_changed.connect(func(value): _login_name = value)
	panel.add_child(name_input)
	if Game.platform.local_login_enabled() and "identity.local" in Game.server_info.get("capabilities", []):
		_label(panel, "同名登录原账号，新名称自动注册新账号。", 20, P.MUTED)
	_label(panel, "服务器地址", 22, P.MUTED)
	var address := LineEdit.new()
	address.text = _login_address
	address.placeholder_text = "http://127.0.0.1:5080"
	address.text_changed.connect(func(value): _login_address = value)
	panel.add_child(address)
	if Game.platform.local_login_enabled() and "identity.local" in Game.server_info.get("capabilities", []):
		_button(panel, "正在连接…" if Game.busy else "本地登录 / 注册", func(): Game.login(_login_address.strip_edges(), _login_name.strip_edges()), Game.busy)
	var steam_reason: String = Game.platform.login_unavailable_reason()
	_button(panel, "Steam 登录", func(): Game.login_steam(_login_address.strip_edges(), _login_name.strip_edges()), Game.busy or not steam_reason.is_empty())
	if not steam_reason.is_empty(): _label(panel, steam_reason, 20, P.MUTED)
	if not Game.authentication_reason.is_empty(): _label(panel, Game.authentication_reason, 22, P.GOLD)
	if not Game.configuration_error.is_empty(): _label(panel, Game.configuration_error, 22, P.GOLD)
	var about := _panel(row, 680)
	var announcement: Dictionary = Game.server_info.get("announcement", {})
	var title := str(announcement.get("title", "")).strip_edges()
	var body := str(announcement.get("body", "")).strip_edges()
	var announcement_title := _label(about, title if not title.is_empty() else "版本公告", 34, P.GOLD)
	announcement_title.custom_minimum_size.y = 58
	announcement_title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	announcement_title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	var announcement_scroll := ScrollContainer.new()
	announcement_scroll.custom_minimum_size.y = 230
	announcement_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	announcement_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	announcement_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_NEVER
	_about_scroll_content(announcement_scroll, body)
	about.add_child(announcement_scroll)

func _about_scroll_content(scroll: ScrollContainer, body: String) -> void:
	var text := Label.new()
	text.text = body if not body.is_empty() else "暂无公告"
	text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	text.add_theme_font_override("font", P.font_for_text(text.text, 24))
	text.add_theme_font_size_override("font_size", 24)
	text.add_theme_color_override("font_color", P.PAPER)
	scroll.add_child(text)

func _nav() -> void:
	var nav := _row(content)
	var names := {"hall": "营地", "cards": "卡牌图鉴", "gear": "穿戴 / 强化", "shop": "金币商店", "market": "金币市场", "prep": "探索准备"}
	for key in names:
		var button := _button(nav, names[key], _navigate.bind(key), Game.busy or not Game.ticket.is_empty())
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		if screen == key: button.add_theme_stylebox_override("normal", Art.style("UI/CardCodex/card_codex_action_button_orange.png"))

func _navigate(value: String) -> void:
	var generation: int = Game.gateway.session_generation
	if value == "gear" and screen != "gear": _equipment_scroll = 0
	screen = value
	edit_mode = false
	_codex_card = ""
	_codex_scroll = 0
	_deck_builder_scroll = 0
	_enhancement_quote_key = ""
	_enhancement_quote = {}
	if value == "shop": _shop_inventory_ready = false
	if value in ["cards", "deck"] and _codex_ready:
		deck_draft = Game.deck().get("cardIds", []).duplicate()
		screen_loading = false
		_render()
		return
	if value in ["cards", "deck", "gear", "enhance", "shop", "market", "prep"]:
		screen_loading = true
		_render()
		var path: String = {"cards": "/cards", "deck": "/cards", "gear": "/inventory", "enhance": "/inventory", "shop": "/shop/", "market": "/market/", "prep": "/inventory"}[value]
		var result: Dictionary = await Game.gateway.request("/api/v1" + path)
		if not _session_result_current(generation, result): return
		if result.ok:
			match value:
				"cards", "deck":
					owned = result.data
					_codex_ready = true
					deck_draft = Game.deck().get("cardIds", []).duplicate()
				"gear", "enhance", "prep":
					inventory = result.data
					gear_draft = Game.loadout().get("equipmentIds", []).duplicate()
					gear_draft.resize(5)
				"shop":
					shop = result.data
					var stock: Dictionary = await Game.gateway.request("/api/v1/inventory")
					if not _session_result_current(generation, stock): return
					if stock.ok:
						inventory = stock.data
						_shop_inventory_ready = true
				"market":
					listings = result.data
					var bag: Dictionary = await Game.gateway.request("/api/v1/inventory")
					if not _session_result_current(generation, bag): return
					if bag.ok: inventory = bag.data
		screen_loading = false
	_render()

func _hall() -> void:
	_label(content, "余火营地", 56, P.GOLD)
	var identity := _row(content)
	_label(identity, "%s · UID %s" % [Game.lobby.player.get("displayName", ""), Game.lobby.player.get("userId", "")], 20, P.MUTED)
	_button(identity, "切换账号", Game.logout, Game.busy)
	var classes := _row(content)
	for key in P.CLASSES:
		var info: Array = P.CLASSES[key]
		var button := _button(classes, "%s   %s\n生命上限 %s" % [P.word(key), info[0], info[2]], func(): Game.select_class(key), Game.busy or not Game.preparation.is_empty())
		button.icon = Art.texture("UI/Codex/class_badge_%s.png" % key.to_lower())
		button.expand_icon = true
		button.add_theme_constant_override("icon_max_width", 44)
		# 当前职业的元素图标放在职业条旁边，而不是职业选择框内部。
		if Game.hero_class == key:
			var element_icon := TextureRect.new()
			element_icon.texture = Art.texture("UI/Battle/battle_element_icon_fire.png")
			element_icon.custom_minimum_size = Vector2(44, 44)
			element_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			element_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			classes.add_child(element_icon)
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		if Game.hero_class == key: button.add_theme_stylebox_override("normal", Art.style("UI/CardCodex/card_codex_action_button_orange.png"))
	var row := _row(content)
	var hero := _panel(row, 740)
	Art.image(hero, Art.portrait(Game.hero_class), Vector2(200, 240))
	var info: Array = P.CLASSES[Game.hero_class]
	_label(hero, info[0], 52)
	_label(hero, info[3], 25, P.MUTED)
	_label(hero, info[4], 30, P.TEAL)
	_label(hero, "出战编组  %s / 20" % Game.deck().get("cardIds", []).size(), 26)
	var portal := _panel(row, 740)
	Art.image(portal, Art.texture("UI/Hall/portal_background_clean.png"), Vector2(360, 240))
	_label(portal, "混沌领域", 60, P.GOLD)
	_label(portal, "六乘六的未知旅途\n四名旅人，向领域中心前进。", 28)
	_button(portal, "探索准备   →", _navigate.bind("prep"))
	_label(portal, "怪物各自迎战，同格可能触发决斗。", 22, P.MUTED)

func _preparation() -> void:
	_label(content, "带上勇气，留出归途", 46, P.GOLD)
	if not Game.preparation.is_empty():
		var panel := _panel(content)
		var snap: Dictionary = Game.preparation.snapshot
		_label(panel, "准备已锁定 · %s · %s 张牌" % [P.CLASSES[snap.heroClass][0], snap.cardIds.size()], 32)
		_label(panel, "背包 %s 格 / 安全 %s 格 · 生命药剂 %s" % [snap.backpackCapacity, snap.safeSlotIndexes.size(), snap.potionCount])
		if not Game.ticket.is_empty():
			_label(panel, "正在寻找旅人…不足四人时由机器人补位。", 30, P.TEAL)
		else:
			_button(panel, "开始匹配", Game.enqueue, Game.busy or not Game.gateway.online)
		_button(panel, "取消匹配 / 准备" if not Game.ticket.is_empty() else "取消准备", Game.cancel_preparation, Game.busy)
		return
	var row := _row(content)
	var left := _panel(row, 650)
	var identity := _row(left)
	Art.image(identity, Art.portrait(Game.hero_class), Vector2(90, 110))
	_label(identity, P.CLASSES[Game.hero_class][0], 36)
	_label(left, "锁定武器 · " + P.CLASSES[Game.hero_class][1], 26, P.GOLD)
	_label(left, P.localized("deck_count_summary") % Game.deck().get("cardIds", []).size())
	var consumables: Dictionary = inventory.get("consumables", {})
	for key in ["Free", "Advanced", "Top"]:
		var text_key: String = {"Free": "bag_option_free", "Advanced": "bag_option_advanced", "Top": "bag_option_top"}[key]
		var text: String = P.localized(text_key)
		var button := _button(left, text, func(): bag_tier = key; _render())
		if bag_tier == key: button.add_theme_stylebox_override("normal", Art.style("UI/CardCodex/card_codex_action_button_orange.png"))
	_label(left, P.localized("health_potion_summary") % consumables.get("healthPotionCount", 0), 22)
	var potion := SpinBox.new()
	potion.max_value = mini(2, int(consumables.get("healthPotionCount", 0)))
	potion.value = potion_count
	potion.value_changed.connect(func(value): potion_count = int(value))
	left.add_child(potion)
	_button(left, "确认探索准备", func(): Game.prepare(bag_tier, potion_count), Game.busy)
	var right := _panel(row, 880)
	_label(right, "临时背包", 34)
	_label(right, "描边为安全格，卡牌与专属武器不占格。", 22, P.MUTED)
	var grid := GridContainer.new()
	grid.columns = 6
	grid.add_theme_constant_override("h_separation", Art.COMMON_CELL_GAP)
	grid.add_theme_constant_override("v_separation", Art.COMMON_CELL_GAP)
	right.add_child(grid)
	var capacity: int = {"Free": 20, "Advanced": 28, "Top": 36}[bag_tier]
	var safe: int = {"Free": 0, "Advanced": 1, "Top": 3}[bag_tier]
	for index in range(capacity):
		var cell := _button(grid, str(index + 1), func(): pass, true)
		Art.button(cell, Art.COMMON_CELL_KEY)
		cell.custom_minimum_size = Art.COMMON_CELL_DISPLAY_SIZE
		if index >= capacity - safe:
			cell.add_theme_stylebox_override("disabled", P.box(P.INK, P.GOLD, 3))
			cell.icon = Art.texture("UI/Prep/icon_safe.png")
			cell.expand_icon = true
			cell.add_theme_constant_override("icon_max_width", 30)

func _ready_screen() -> void:
	var panel := _panel(content)
	_label(panel, "旅人集结", 60, P.GOLD)
	_label(panel, "找到同行者，请确认启程。", 32)
	_label(panel, "已确认 %s / %s" % [Game.ready_prompt.get("ready_players", 0), Game.ready_prompt.get("required_players", 1)])
	var remaining := maxi(0, int((int(Game.ready_prompt.get("deadline_unix_ms", 0)) - Time.get_unix_time_from_system() * 1000) / 1000))
	_label(panel, "确认剩余 %s 秒" % remaining, 32, P.TEAL)
	_button(panel, "准备就绪", func(): Game.gateway.send("room.ready"), not Game.gateway.online)

func card_description(id: String, kind: String = "face") -> String:
	var locale := P.language()
	var descriptions: Dictionary = DESCRIPTIONS.data.get(locale, DESCRIPTIONS.data.get("zh", {}))
	# Description tables use the `card.<kind>.desc.<id>` namespace. Keep the
	# lookup here aligned with both the face summary and the full detail text;
	# the old key omitted `.desc` and silently fell back to numeric shorthand.
	return str(descriptions.get("card.%s.desc.%s" % [kind, id], ""))

func _card_text(id: String, level: int = 0, element_override: String = "") -> String:
	var info: Dictionary = CardDetails.with_element(cards.get(id, {}), element_override)
	var source: String = info.get("source", "")
	var badge := "怪" if not info.get("is_codex", true) else P.word(info.get("hero_class", ""))
	var name := CardDetails.localized_name(id, info)
	var description: String = card_description(id, "face")
	if description.is_empty():
		# Cards without a configured face description use the structured fallback.
		var lines: Array = []
		for key in ["elemental_damage", "direct_damage", "heal", "shield"]:
			if int(info.get(key, 0)) > 0:
				lines.append("%s %s" % [{"elemental_damage": P.word(info.get("element", "None")), "direct_damage": "直伤", "heal": "治疗", "shield": "护盾"}[key], info[key]])
		description = " / ".join(lines)
	return "%s %s\n%s\n\n%s" % [badge, name, P.word(info.get("quality", "")) if source != "Monster" else "暗红 · 本局", description]

func _card_button(parent: Node, id: String, callback: Callable, selected: bool = false, disabled: bool = false, options: Dictionary = {}) -> Button:
	var button := CardView.new()
	button.set_meta("sound_cue", "" if options.get("preview", false) else "card_select")
	button.disabled = disabled
	button.pressed.connect(callback)
	parent.add_child(button)
	var element_override: String = options.get("element_override", "")
	button.configure(id, CardDetails.with_element(cards.get(id, {}), element_override), _card_text(id, int(options.get("level", 0)), element_override), selected, options)
	return button

func _owned_card(id: String) -> Dictionary:
	for entry in owned:
		if entry.get("cardId") == id: return entry
	return {}

func _card_material(kind: String) -> int:
	var field := kind.left(1).to_lower() + kind.substr(1)
	return int(Game.lobby.get("materials", {}).get(field, 0))

func _card_action_block_reason(id: String, action: String) -> String:
	var entry := _owned_card(id)
	if entry.is_empty() or not entry.has("craftCost"): return "报价暂不可用"
	var kind := str(entry.get("currencyKind", "WarriorSoul"))
	var material := P.localized_word(kind)
	var balance := _card_material(kind)
	if action == "upgrade":
		if int(entry.get("level", 0)) >= 5: return "已达最高等级"
		var cost := int(entry.get("upgradeCost", 0))
		if balance < cost: return "%s不足，还需 %s" % [material, cost - balance]
		if not entry.get("canUpgrade", false): return "当前状态已改变，请重新选择操作"
	elif action == "craft":
		if entry.get("unlocked", false) or int(entry.get("copyCount", 0)) > 0: return "卡牌已激活"
		var craft_cost := int(entry.get("craftCost", 0))
		if balance < craft_cost: return "%s不足，还需 %s" % [material, craft_cost - balance]
	elif action == "dismantle" and deck_draft.count(id) >= int(entry.get("copyCount", 0)):
		return "当前编组正在使用这张卡，请先从编组移除"
	return ""

func _replace_owned_card(card: Dictionary) -> void:
	var id := str(card.get("cardId", ""))
	if id.is_empty(): return
	for index in range(owned.size()):
		if str(owned[index].get("cardId", "")) == id:
			owned[index] = card
			return
	owned.append(card)

func _set_codex_action_busy(value: bool) -> void:
	if not is_instance_valid(_reference): return
	for node_name in ["UpgradeCard", "DismantleCard", "CraftCard", "CloseCardDetails"]:
		var button := _reference.find_child(node_name, true, false) as Button
		if button != null: button.disabled = value
	var primary := _reference.find_child("UpgradeCard", true, false) as Button
	if value and primary != null: primary.text = P.localized_text("正在处理…")

func _card_action(id: String, action: String) -> void:
	if Game.busy or _codex_mutating or not _codex_ready: return
	var entry := _owned_card(id)
	if entry.is_empty() or not entry.has("craftCost"): return
	var blocked := _card_action_block_reason(id, action)
	if not blocked.is_empty():
		_toast(blocked)
		return
	_codex_mutating = true
	Game.busy = true
	_set_codex_action_busy(true)
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1/cards/%s/%s" % [id.uri_encode(), action], HTTPClient.METHOD_POST, {"expectedVersion": int(entry.get("version", 0))})
	if not _session_result_current(generation, result):
		_codex_mutating = false
		return
	if result.ok:
		if result.data.get("card") is Dictionary: _replace_owned_card(result.data.card)
		if result.data.get("materials") is Dictionary: Game.lobby["materials"] = result.data.materials
		_codex_ready = true
		Sound.play_cue("upgrade" if action == "upgrade" else "reward")
		_toast({"craft": "合成成功，已获得 1 张卡牌", "dismantle": "分解成功，材料已返还", "upgrade": "升级成功，卡牌效果已提升"}.get(action, "操作完成"))
	else:
		Sound.play_cue("error")
		var refreshed: Dictionary = await Game.gateway.request("/api/v1/cards")
		if not _session_result_current(generation, refreshed):
			_codex_mutating = false
			return
		_codex_ready = refreshed.ok
		if refreshed.ok: owned = refreshed.data
	_codex_mutating = false
	if not _session_result_current(generation): return
	Game.busy = false
	_render()

func _codex() -> void:
	var header := _row(content)
	_label(header, "卡牌图鉴", 42, P.GOLD)
	_label(header, P.localized("deck_count_summary") % deck_draft.size(), 30)
	_button(header, "保存编组", _save_deck, deck_draft.size() != 20 or Game.busy)
	_button(header, "还原", func(): deck_draft = Game.deck().get("cardIds", []).duplicate(); _render())
	var deck_row := HFlowContainer.new()
	content.add_child(deck_row)
	for index in range(deck_draft.size()):
		var id: String = deck_draft[index]
		_button(deck_row, "%s ×" % CardDetails.localized_name(id, cards.get(id, {})), func(): deck_draft.remove_at(index); _render())
	var resources: Dictionary = Game.lobby.get("materials", {})
	_label(content, "勇士之魂 %s   ·   职业之魂 %s" % [resources.get("warriorSoul", 0), resources.get(Game.hero_class.to_lower() + "Soul", 0)], 22, P.MUTED)
	var grid := GridContainer.new()
	grid.columns = 6
	content.add_child(grid)
	for card in owned:
		var class_value: Variant = card.get("heroClass")
		if class_value != null and class_value != Game.hero_class: continue
		var id: String = card.cardId
		var can_add: bool = card.get("unlocked", false) and deck_draft.size() < 20 and deck_draft.count(id) == 0
		if cards.get(id, {}).get("quality", "") == "Orange":
			for entry in deck_draft:
				var existing: Dictionary = cards.get(entry, {})
				if existing.get("quality") == "Orange" and (existing.get("hero_class") == null) == (class_value == null): can_add = false
		var button := _card_button(grid, id, func(): deck_draft.append(id); _render(), false, not can_add)
		button.tooltip_text += "\n已编入 %s / 持有 %s · 等级 %s" % [deck_draft.count(id), card.copyCount, card.level]

func _save_deck() -> void:
	if Game.busy: return
	if deck_draft.size() != DeckBuilder.DECK_SIZE:
		_toast(P.localized("deck_requires_twenty"))
		return
	Game.busy = true
	_render()
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1/decks/" + Game.hero_class, HTTPClient.METHOD_PUT, {"cardIds": deck_draft, "expectedVersion": Game.deck().get("version", 0)}, [0, 400, 409, 429, 500, 502, 503, 504])
	if not _session_result_current(generation, result): return
	if result.ok:
		await Game.refresh_lobby()
		if not _session_result_current(generation): return
		deck_draft = Game.deck().get("cardIds", []).duplicate()
		Sound.play_cue("equip")
		_toast(P.localized("deck_saved"))
	elif int(result.get("status", 0)) == 409:
		await Game.refresh_lobby()
		if not _session_result_current(generation): return
		deck_draft = Game.deck().get("cardIds", []).duplicate()
		_toast(P.localized("deck_changed_retry"))
	elif int(result.get("status", 0)) == 400:
		_toast(P.localized("deck_invalid"))
	else:
		_toast(P.localized("deck_save_failed"))
	Game.busy = false
	_render()

func _equipment_name(item: Dictionary) -> String:
	return EquipmentDetails.title(item)

func _equipment() -> void:
	_label(content, "行装与本命", 44, P.GOLD)
	var weapon: Dictionary = {}
	for value in Game.lobby.get("classWeapons", []):
		if value.heroClass == Game.hero_class: weapon = value
	var top := _row(content)
	Art.image(top, Art.texture("UI/Item/exploration_prep_item_icon_weapon_%s.png" % Game.hero_class.to_lower()), Vector2(80, 100))
	_label(top, "锁定 · %s  +%s" % [P.CLASSES[Game.hero_class][1], weapon.get("level", 0)], 30, P.GOLD)
	_button(top, "强化专属武器", _enhance_weapon, Game.busy or int(weapon.get("level", 0)) >= 5)
	_label(content, "装备碎片 %s" % Game.lobby.get("materials", {}).get("equipmentFragments", 0), 24, P.MUTED)
	var slot_names := ["头部", "胸甲", "手部", "腿部", "鞋子"]
	var row := _row(content)
	for index in range(5):
		var id: Variant = gear_draft[index] if index < gear_draft.size() else null
		var name := "未穿戴"
		var worn_item: Dictionary = {}
		for item in inventory.get("equipments", []):
			if item.instanceId == id:
				name = _equipment_name(item)
				worn_item = item
		var slot := _button(row, slot_names[index] + "\n" + name + ("\n点击卸下" if id != null else ""), func(): gear_draft[index] = null; _render(), id == null)
		slot.icon = Art.equipment_texture(worn_item) if not worn_item.is_empty() else Art.texture("UI/Item/exploration_prep_item_icon_%s.png" % ["helmet", "chest", "gauntlet", "legs", "boots"][index])
		slot.expand_icon = true
		slot.add_theme_constant_override("icon_max_width", 58)
		if id == null:
			for state in ["normal", "hover", "pressed", "disabled", "focus"]:
				slot.add_theme_color_override("icon_%s_color" % state, Art.UNEQUIPPED_ITEM_MODULATE)
	_button(content, "保存五部位穿戴", func(): _mutate("/loadouts/" + Game.hero_class, HTTPClient.METHOD_PUT, {"equipmentIds": gear_draft, "expectedVersion": Game.loadout().get("version", 0)}), Game.busy)
	for item in inventory.get("equipments", []):
		var line := _row(_panel(content))
		_label(line, _equipment_name(item), 26)
		_label(line, P.word(item.get("effectAffix")), 24, P.TEAL)
		_button(line, "穿戴", func(): _equip(item), Game.busy or item.get("location") not in ["Inventory", "Equipped"])
		_button(line, "强化", func(): _enhance(item), Game.busy or int(item.get("level", 0)) >= 5)
	if inventory.get("equipments", []).is_empty(): _label(content, "仓库暂无装备，探索撤离后可带回战利品。", 28, P.MUTED)

func _equip(item: Dictionary) -> void:
	var slots := {"Head": 0, "Helmet": 0, "Chest": 1, "Body": 1, "Hands": 2, "Gloves": 2, "Legs": 3, "Feet": 4, "Boots": 4}
	if not slots.has(item.slot): _toast("未识别的装备部位"); return
	gear_draft[slots[item.slot]] = item.instanceId
	_render()

func _equipped_items() -> Array:
	if not Game.room.is_empty(): return Game.room.get("player", {}).get("equipped_items", [])
	return inventory.get("equipments", []).filter(func(value): return value.get("instanceId", "") in gear_draft)

func _current_equipment(item: Dictionary, worn: Array = []) -> Dictionary:
	var gear: Dictionary = EquipmentDetails.equipment(item)
	if worn.is_empty(): worn = _equipped_items()
	var current: Dictionary = {}
	for candidate in worn:
		if EquipmentDetails.equipment(candidate).get("slot", "") == gear.get("slot", ""):
			current = candidate
			break
	return current

func _show_equipment_details(item: Dictionary, action: Callable = Callable(), action_title: String = "穿戴") -> void:
	var worn := _equipped_items()
	var current := _current_equipment(item, worn)
	# Wearing into an empty slot has no baseline to compare. Follow the GDD/UI
	# flow and execute the requested equip action without opening a modal.
	if current.is_empty() and action.is_valid():
		if not Game.busy: action.call()
		return
	var dialog := EquipmentCompareDialog.new()
	add_child(dialog)
	dialog.open(item, current, worn, action, action_title, Game.busy)

func _show_battle_details(status: Dictionary) -> void:
	var dialog := AcceptDialog.new()
	dialog.title = P.localized_text("当前战斗属性与套装")
	dialog.dialog_text = BattleDetails.description(status) if not status.is_empty() else P.localized_text("等待战斗属性同步")
	add_child(dialog)
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	dialog.popup_centered(Vector2i(700, 630))

func _enhance(item: Dictionary) -> void:
	if Game.busy: return
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1/equipment/" + item.instanceId + "/enhancement-quote")
	if not _session_result_current(generation, result): return
	if not result.ok: return
	var quote: Dictionary = result.data
	if not quote.get("canEnhance", false): _toast(P.localized("enhance_unavailable")); return
	var body := {"expectedVersion": quote.expectedVersion}
	var cost_text := P.localized("enhance_cost_confirm") % [quote.fragmentCost, quote.nextLevel]
	if int(quote.materialCount) == 0:
		_confirm(cost_text + "？", func(): _mutate("/equipment/" + item.instanceId + "/enhance", HTTPClient.METHOD_POST, body))
		return
	var dialog := AcceptDialog.new()
	dialog.title = P.localized("enhance_material_dialog")
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(720, 390)
	dialog.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(column)
	_label(column, P.localized("enhance_material_cost") % cost_text, 24)
	var count := 0
	for material in inventory.get("equipments", []):
		if material.instanceId == item.instanceId or material.get("location") != "Inventory" or material.quality != item.quality: continue
		count += 1
		_button(column, _equipment_name(material), func(): body.materialEquipmentId = material.instanceId; dialog.queue_free(); _confirm(P.localized("enhance_material_confirm") % [cost_text, _equipment_name(material)], func(): _mutate("/equipment/" + item.instanceId + "/enhance", HTTPClient.METHOD_POST, body)))
	if count == 0: _label(column, P.localized("enhance_no_material"))
	add_child(dialog)
	dialog.popup_centered(Vector2i(750, 360))
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)

func _enhance_weapon() -> void:
	if Game.busy: return
	var generation: int = Game.gateway.session_generation
	var hero_class: String = Game.hero_class
	var result: Dictionary = await Game.gateway.request("/api/v1/class-weapons/" + hero_class + "/enhancement-quote")
	if not _session_result_current(generation, result): return
	if not result.ok: return
	var quote: Dictionary = result.data
	if not quote.get("canEnhance", false): _toast(P.localized("enhance_weapon_unavailable")); return
	_confirm(P.localized("enhance_weapon_confirm") % [quote.fragmentCost, quote.nextLevel], func(): _mutate("/class-weapons/" + hero_class + "/enhance", HTTPClient.METHOD_POST, {"expectedVersion": quote.expectedVersion}))

func _read_enhancement_quote(item: Dictionary, weapon: Dictionary) -> void:
	var id: String = item.get("instanceId", Game.hero_class)
	var key := "%s:%s" % [id, item.get("version", weapon.get("version", 0))]
	if key == _enhancement_quote_key: return
	_enhancement_quote_key = key
	_enhancement_quote = {}
	var prefix := "/equipment/" if not item.is_empty() else "/class-weapons/"
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1" + prefix + id + "/enhancement-quote")
	if not _session_result_current(generation, result): return
	if key != _enhancement_quote_key or screen != "enhance": return
	_enhancement_quote = result.data if result.ok else {"error": true}
	_schedule_render()

func _weapon_benefit(level: int) -> String:
	var percent: int = [6, 8, 10, 11, 13, 14][clampi(level, 0, 5)]
	match Game.hero_class:
		"Priest": return P.localized("weapon_benefit_heal") % percent
		"Mage": return P.localized("weapon_benefit_charge") % [P.localized("class_mage_weapon"), percent]
		_: return P.localized("weapon_benefit_shield") % (3 if level >= 4 else (2 if level >= 2 else 1))

func _shop() -> void:
	_label(content, "旅人补给", 44, P.GOLD)
	var grid := GridContainer.new()
	grid.columns = 3
	content.add_child(grid)
	for item in shop.get("products", []):
		var panel := _panel(grid, 535)
		_label(panel, P.word(item.kind), 30)
		var payload: Variant = JSON.parse_string(item.get("payload", "{}"))
		if payload is Dictionary and payload.has("cardId"):
			var card_id := str(payload.cardId)
			_label(panel, CardDetails.localized_name(card_id, cards.get(card_id, {})), 26, P.TEAL)
		_label(panel, P.localized("shop_price") % item.priceGold, 36, P.GOLD)
		_label(panel, P.localized("shop_purchase_count") % [item.purchased, item.limit], 22, P.MUTED)
		_button(panel, "已激活" if item.get("alreadyOwned", false) else "购买", func(): _confirm("花费 %s 金币购买？" % item.priceGold, func(): _mutate("/shop/purchases", HTTPClient.METHOD_POST, {"productId": item.productId, "quantity": 1})), Game.busy or item.get("alreadyOwned", false) or int(item.purchased) >= int(item.limit) or int(item.priceGold) > int(Game.lobby.wallet.gold))
	if shop.get("products", []).is_empty(): _label(content, "暂无商品，稍后刷新。", 28)

func _market() -> void:
	_label(content, "旅人集市", 44, P.GOLD)
	_label(content, "金币交易 · 上架上限 8 件 · 48 小时 · 手续费 10%（至少 1 金币）", 24, P.MUTED)
	for listing in listings:
		var row := _row(_panel(content))
		_label(row, "装备 " + str(listing.equipmentId).left(8), 25)
		_label(row, "%s 金币" % listing.priceGold, 32, P.GOLD)
		if listing.sellerId == Game.lobby.player.userId:
			_label(row, "卖家实得 %s" % (int(listing.priceGold) - maxi(1, int(int(listing.priceGold) / 10.0))), 22)
			_button(row, "下架", func(): _mutate("/market/listings/" + listing.listingId, HTTPClient.METHOD_DELETE), Game.busy)
		else:
			_button(row, "购买", func(): _confirm("花费 %s 金币购买此装备？" % listing.priceGold, func(): _mutate("/market/" + listing.listingId + "/purchase?expectedVersion=" + str(int(listing.version)), HTTPClient.METHOD_POST)), Game.busy or int(listing.priceGold) > int(Game.lobby.wallet.gold))
	if listings.is_empty(): _label(content, "集市暂时没有挂单。", 28, P.MUTED)
	_label(content, "选择仓库装备上架", 32)
	for item in inventory.get("equipments", []):
		if item.get("isBound", false) or item.get("location") != "Inventory": continue
		var row := _row(content)
		_label(row, _equipment_name(item))
		var price := SpinBox.new()
		price.min_value = 1
		price.max_value = 100000000
		price.value = 100
		row.add_child(price)
		_button(row, "上架", func(): _confirm("确认以 %s 金币上架？" % int(price.value), func(): _mutate("/market/listings", HTTPClient.METHOD_POST, {"equipmentId": item.instanceId, "priceGold": int(price.value)})), Game.busy)

func _mutate(path: String, method: int, body: Variant = null) -> void:
	if Game.busy: return
	Game.busy = true
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1" + path, method, body)
	if not _session_result_current(generation, result): return
	if result.ok:
		var cue := "equip"
		if path.ends_with("/enhance"): cue = "upgrade"
		elif path == "/shop/purchases" or path.contains("/purchase?"): cue = "purchase"
		Sound.play_cue(cue)
		_toast("操作成功")
	else: Sound.play_cue("error")
	await Game.refresh_lobby()
	if not _session_result_current(generation): return
	Game.busy = false
	await _navigate(screen)

func _purchase_shop_item(item: Dictionary, product_title: String) -> void:
	var purchase := func(): _complete_shop_purchase(item)
	if item.get("kind", "") == "Cards":
		_confirm("花费 %s 金币购买%s？" % [item.get("priceGold", 0), product_title], purchase)
	else:
		purchase.call()

func _complete_shop_purchase(item: Dictionary) -> void:
	if Game.busy: return
	Game.busy = true
	var generation: int = Game.gateway.session_generation
	var product_id: String = str(item.get("productId", ""))
	var scroll_position := 0
	if is_instance_valid(_reference):
		var shop_scroll := _reference.get_node_or_null("ShopScroll") as ScrollContainer
		if shop_scroll != null: scroll_position = shop_scroll.scroll_horizontal
	var result: Dictionary = await Game.gateway.request("/api/v1/shop/purchases", HTTPClient.METHOD_POST, {"productId": product_id, "quantity": 1})
	if not _session_result_current(generation, result): return
	if result.ok:
		_apply_shop_purchase(product_id, result.data)
		Sound.play_cue("purchase")
		_toast("操作成功")
	else:
		Sound.play_cue("error")
	Game.busy = false
	_render()
	_restore_shop_scroll.call_deferred(scroll_position)

func _restore_shop_scroll(scroll_position: int) -> void:
	if screen != "shop" or not is_instance_valid(_reference): return
	var shop_scroll := _reference.get_node_or_null("ShopScroll") as ScrollContainer
	if shop_scroll != null: shop_scroll.scroll_horizontal = scroll_position

func _apply_shop_purchase(product_id: String, response: Dictionary) -> void:
	var quantity: int = int(response.get("quantity", 1))
	var products: Array = shop.get("products", [])
	for index in products.size():
		var product: Dictionary = products[index]
		if str(product.get("productId", "")) != product_id: continue
		product["purchased"] = int(product.get("purchased", 0)) + quantity
		products[index] = product
		var kind: String = str(product.get("kind", ""))
		if kind in ["AdvancedBag", "TopBag"]:
			var payload: Variant = JSON.parse_string(product.get("payload", "{}"))
			var amount: int = int(payload.get("amount", 1)) if payload is Dictionary else 1
			var consumables: Dictionary = inventory.get("consumables", {}).duplicate()
			var key := "advancedBagCount" if kind == "AdvancedBag" else "topBagCount"
			consumables[key] = int(consumables.get(key, 0)) + amount * quantity
			inventory["consumables"] = consumables
		break
	shop["products"] = products
	var wallet: Dictionary = Game.lobby.get("wallet", {}).duplicate()
	wallet["gold"] = int(response.get("goldAfter", wallet.get("gold", 0)))
	Game.lobby["wallet"] = wallet

func _session_result_current(generation: int, result: Dictionary = {}) -> bool:
	return generation == Game.gateway.session_generation and not result.get("stale_session", false)

func _confirm(message: String, action: Callable, options: Dictionary = {}) -> void:
	if get_node_or_null("ConfirmationModal") != null: return
	var dialog := ConfirmationModalScene.instantiate()
	add_child(dialog)
	dialog.configure(message, action, options)

func _room() -> void:
	var state: Dictionary = Game.room
	var player: Dictionary = state.get("player", {})
	var combat: Dictionary = player.get("combat", {})
	var row := _row(content)
	_label(row, "混沌领域 / " + P.word(player.get("phase", "")), 38, P.GOLD)
	_label(row, "生命 %s / %s   护盾 %s" % [combat.get("hp", 0), combat.get("maximum_hp", 0), combat.get("shield", 0)], 28)
	_button(row, "同步", func(): Game.gateway.send("room.snapshot.read"))
	if player.get("phase", "") in ["Pve", "Pvp"]:
		_battle(state)
	elif state.has("reward_choice"):
		_rewards(state.reward_choice)
	else:
		_map(state)
		_action_bar(state)
	for key in ["extraction_remaining_ms", "spring_remaining_ms"]:
		if state.has(key): _label(content, ("撤离中 " if key.begins_with("extraction") else "饮用泉水 ") + "%.1f 秒" % (float(state[key]) / 1000.0), 32, P.TEAL)

func _battle(state: Dictionary) -> void:
	var stage := _row(content)
	var hero := _panel(stage, 560)
	hero.add_theme_constant_override("separation", 8)
	_combat_panels[state.player.player_id] = hero.get_parent()
	_label(hero, P.CLASSES.get(state.player.hero_class, P.CLASSES.Mage)[0], 32)
	Art.image(hero, Art.portrait(state.player.hero_class), Vector2(120, 110))
	_health_bar(hero, state.player.combat)
	if state.has("duel"):
		var opponent := _panel(stage, 900)
		_combat_panels[state.duel.opponent_id] = opponent.get_parent()
		_label(opponent, "同格旅人", 42, P.GOLD)
		_health_bar(opponent, state.duel.opponent)
		_label(opponent, "生命 %s / %s    护盾 %s" % [state.duel.opponent.hp, state.duel.opponent.maximum_hp, state.duel.opponent.shield], 28)
		if Game.allowed("duel.leave"): _button(opponent, "双方离开", func(): Game.command("duel.leave", {"duel_id": state.duel.duel_id}))
		if Game.allowed("duel.escape"): _button(opponent, "强制逃脱", func(): Game.command("duel.escape", {"duel_id": state.duel.duel_id}))
		if state.duel.has("escape_remaining_ms"): _label(opponent, "逃脱读条 %.1f 秒" % (float(state.duel.escape_remaining_ms) / 1000.0))
	else:
		for monster in state.get("pve", {}).get("monsters", []):
			var enemy := _panel(stage, 420)
			enemy.add_theme_constant_override("separation", 8)
			_combat_panels[monster.monster_id] = enemy.get_parent()
			var button := _button(enemy, _monster_name(monster.monster_id) + (" · 当前目标" if state.pve.current_target_id == monster.monster_id else " · 选择目标"), func(): Game.command("battle.select_target", {"battle_id": state.pve.battle_id, "target_id": monster.monster_id}), not Game.allowed("battle.select_target") or int(monster.hp) <= 0)
			button.custom_minimum_size.y = 60
			var portrait := Art.image(enemy, Art.monster(monster.monster_id), Vector2(110, 90))
			if portrait.texture == null:
				portrait.custom_minimum_size.y = 40
				_label(enemy, _monster_name(monster.monster_id), 28, P.MUTED)
			_label(enemy, "生命 %s / %s    盾 %s" % [monster.hp, monster.maximum_hp, monster.shield], 20)
			_health_bar(enemy, monster)
			var intent: String = {"Charge": "蓄力", "Empower": "强化", "Shield": "护盾"}.get(monster.intent_kind, P.word(monster.intent_element))
			_label(enemy, "意图 %s %s" % [intent, monster.intent_value if int(monster.intent_value) > 0 else ""], 23, P.ELEMENT.get(monster.intent_element, Color.WHITE))
	var charge := BoundedBar.new()
	charge.configure("UI/Battle/battle_energy_cell_lit.png", "UI/Battle/battle_energy_cell_unlit.png")
	charge.max_value = 1.0
	charge.value = float(state.player.get("draw_charge", "0"))
	charge.custom_minimum_size.y = 16
	content.add_child(charge)
	_label(content, "1–5 选牌 / 空格放出 / R 同步    已选 %s 张" % Game.selected_cards.size(), 22, P.MUTED)
	var hand := _row(content)
	hand.alignment = BoxContainer.ALIGNMENT_CENTER
	for index in range(5):
		if index < state.player.hand.size():
			var card: Dictionary = state.player.hand[index]
			var button := _card_button(hand, card.card_id, func(): Game.toggle_card(card.instance_id), card.instance_id in Game.selected_cards, not Game.allowed("battle.play_cards"))
			button.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		else:
			var empty := _button(hand, "", func(): pass, true)
			Art.button(empty, "UI/Codex/qframe_common.png")
			empty.custom_minimum_size = Vector2(218, 376)
			empty.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	var play := _button(hand, "放", Game.play_cards, Game.selected_cards.is_empty() or not Game.allowed("battle.play_cards"))
	Art.button(play, "UI/Battle/battle_play_button.png")
	play.custom_minimum_size = Vector2(100, 100)
	play.size_flags_vertical = Control.SIZE_SHRINK_CENTER

func _map(state: Dictionary) -> void:
	var row := _row(content)
	var grid := GridContainer.new()
	grid.columns = 6
	row.add_child(grid)
	for y in range(6):
		for x in range(6):
			var text := ""
			for cell in state.get("map", []):
				if int(cell.row) == y and int(cell.column) == x:
					if cell.get("is_boss", false): text = "首领"
					elif cell.get("has_spring", false): text = "源泉"
			var current: bool = state.get("self", {}).get("row", -1) == y and state.get("self", {}).get("column", -1) == x
			if current: text += "\n自己"
			var legal := false
			for move in state.get("legal_moves", []):
				if int(move.row) == y and int(move.column) == x: legal = true
			var button := _button(grid, text, _move.bind(y, x), not legal or not Game.allowed("room.move"))
			button.custom_minimum_size = Vector2(148, 88)
			var layer: int = mini(mini(x, y), mini(5 - x, 5 - y))
			button.add_theme_stylebox_override("disabled", P.box([Color("243e40"), Color("3b4842"), Color("594d3e")][layer], P.GOLD if current else Color("486368"), 3 if current else 1))
	var side := _panel(row, 630)
	_label(side, "深入混沌", 38, P.GOLD)
	_label(side, "首领 / 源泉 / 自己", 26, P.TEAL)
	_label(side, "只能同层横行或向内探索。\n随机撤离点进入所在格后才可发现。", 24, P.MUTED)
	_label(side, "行囊", 30)
	for item in state.get("player", {}).get("inventory", []):
		_label(side, "%s ×%s%s" % [P.word(item.kind), item.quantity, " · 安全" if item.is_safe else ""], 22)

func _monster_name(id: String) -> String:
	var names := {"fire-bat": "火蝠", "thorn-mite": "棘螨", "murk-snail": "浊螅", "sand-lizard": "砂蜥", "rust-rat": "锈刃鼠", "metal-guard": "金卫", "fire-herald": "火劫使", "marsh-mother": "沼母", "stone-guard": "石甲卫", "thorn-guard": "棘林卫", "annihilation-core": "湮核", "treasure-box-spirit": "匣灵"}
	return names.get(id.trim_suffix("-a").trim_suffix("-b"), id)

func _move(row: int, column: int) -> void:
	var layer: int = mini(mini(row, column), mini(5 - row, 5 - column))
	var id: String = Game.room.get("room_id", "")
	if layer > 0 and not _midlayer_seen.has(id):
		set_meta("pending_move", Vector2i(row, column))
		_render()
	else: Game.command("room.move", {"row": row, "column": column})

func _action_bar(_state: Dictionary) -> void:
	var row := _row(content)
	for action in {"action.spring": "饮用源泉", "action.potion": "使用生命药剂", "action.extract": "撤离"}:
		if Game.allowed(action):
			_button(row, {"action.spring": "饮用源泉", "action.potion": "使用生命药剂", "action.extract": "撤离"}[action], func(): Game.command(action))

func _rewards(reward: Dictionary) -> void:
	_label(content, "留下你最需要的", 46, P.GOLD)
	var row := _row(content)
	for option in reward.get("options", []):
		var panel := _panel(row, 510)
		var index := int(option.kind)
		_label(panel, {1: "装备", 2: "装备碎片", 3: "即时回血"}.get(index, "战利品"), 38)
		_label(panel, "%s%% 生命" % option.heal_percent if index == 3 else "数量 %s" % option.quantity, 28, P.TEAL)
		_button(panel, "选择", func(): _claim(option), not Game.allowed("reward.choice.claim"))
	var count := int(reward.get("refresh_count", 0))
	if count < 3:
		_button(content, "刷新 · %s 金币 · 剩余 %s 次" % [[60, 180, 450][count], 3 - count], func(): Game.command("reward.choice.refresh"), not Game.allowed("reward.choice.refresh"))

func _claim(option: Dictionary, equip: bool = false) -> void:
	var player: Dictionary = Game.room.get("player", {})
	var items: Array = player.get("inventory", [])
	var reward_item := {"kind": "Equipment" if int(option.kind) == 1 else "EquipmentFragments", "item_id": option.get("item_id", "")}
	var payload := {"option_id": option.option_id, "equip": equip}
	if not equip and int(option.kind) != 3 and not InventoryView.can_add(player, reward_item):
		var dialog := AcceptDialog.new()
		dialog.title = "包满替换 · 换下物品会被系统回收"
		var scroll := ScrollContainer.new()
		scroll.custom_minimum_size = Vector2(720, 460)
		dialog.add_child(scroll)
		var column := VBoxContainer.new()
		column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		scroll.add_child(column)
		for item in items:
			_button(column, "%s ×%s%s" % [EquipmentDetails.title(item), item.quantity, " · 安全格" if item.get("is_safe", false) else ""], func():
				dialog.queue_free()
				_confirm("回收 %s 并领取战利品？" % EquipmentDetails.title(item), func(): payload.replace_item_id = item.item_id; Game.command("reward.choice.claim", payload)))
		add_child(dialog)
		dialog.confirmed.connect(dialog.queue_free)
		dialog.popup_centered(Vector2i(750, 550))
	elif equip:
		_confirm("直接穿戴新防具，同部位旧装会被系统回收。", func(): Game.command("reward.choice.claim", payload))
	else: Game.command("reward.choice.claim", payload)

func _settlement() -> void:
	_label(content, P.word(Game.settlement.get("result", "旅程结束")), 66, P.GOLD)
	_label(content, "本次旅程已由服务器结算。", 30)
	var details: Dictionary = Game.settlement.get("details", {})
	for key in ["gold", "goldEarned", "equipmentFragments", "warriorSoul"]:
		if details.has(key): _label(content, "%s  %s" % [P.word(key), details[key]], 30)
	_button(content, "返回", Game.acknowledge_settlement, Game.busy)

func _toast(message: String) -> void:
	if is_instance_valid(tips_overlay):
		tips_overlay.show_tip(message)

func _show_ban_dialog(reason: String) -> void:
	if not reason.begins_with("账号已被封禁"): return
	var dialog := AcceptDialog.new()
	dialog.title = "账号已被封禁"
	dialog.dialog_text = reason
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	add_child(dialog)
	dialog.popup_centered(Vector2i(700, 360))

func _health_bar(parent: Node, combat: Dictionary) -> void:
	var bar := BoundedBar.new()
	bar.configure("UI/Encounter/encounter_hp_fill_normal.png", "UI/Encounter/encounter_hp_track_normal.png")
	bar.max_value = maxf(1, float(combat.get("effective_maximum_hp", combat.get("maximum_hp", 1))))
	bar.value = float(combat.get("hp", 0))
	bar.custom_minimum_size.y = 20
	parent.add_child(bar)
	if int(combat.get("shield", 0)) > 0:
		var shield := BoundedBar.new()
		shield.configure_solid(Color("102128"), Color("c4d2d4"))
		shield.max_value = bar.max_value
		shield.value = float(combat.shield)
		shield.custom_minimum_size.y = 8
		parent.add_child(shield)

func _feedback(payload: Dictionary) -> void:
	var target: Control = _combat_panels.get(payload.get("target_id", ""))
	if is_instance_valid(target):
		_pulse(target, 0.97)
		var index := 0
		for segment in payload.get("damage_segments", []):
			if int(segment.get("amount", 0)) <= 0: continue
			_float_number(target, "%s %s" % ["直" if segment.kind == "Direct" else P.word(segment.kind), segment.amount], P.ELEMENT.get(segment.kind, Color.WHITE), index)
			index += 1
	var source_id: String = payload.get("source_id", "")
	if source_id.is_empty(): source_id = payload.get("attacker_id", "")
	var source: Control = _combat_panels.get(source_id)
	if is_instance_valid(source):
		_pulse(source, 1.03)
		for key in ["heal", "shield_gain"]:
			if int(payload.get(key, 0)) <= 0: continue
			_float_number(source, "+%s" % payload[key], P.TEAL if key == "heal" else Color("c4d2d4"), 0 if key == "heal" else 1)

func _pulse(node: Control, factor: float) -> void:
	var previous: Variant = node.get_meta("hit_tween") if node.has_meta("hit_tween") else null
	if previous is Tween and previous.is_running(): previous.kill()
	node.pivot_offset = node.size / 2
	var tween := node.create_tween().set_parallel(true)
	node.set_meta("hit_tween", tween)
	tween.tween_property(node, "modulate", Color(1.3, 1.3, 1.3), 0.08)
	tween.tween_property(node, "scale", Vector2.ONE * factor, 0.08)
	tween.chain().tween_property(node, "modulate", Color.WHITE, 0.15)
	tween.parallel().tween_property(node, "scale", Vector2.ONE, 0.15)

func _float_number(node: Control, value: String, tint: Color, index: int) -> void:
	var number := _label(self, value, 42, tint)
	number.add_theme_font_override("font", P.font("number"))
	number.name = "CombatNumber"
	number.position = node.global_position + Vector2(70 + index * 43, 35 + index * 50)
	number.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var tween := number.create_tween().set_parallel(true)
	tween.tween_property(number, "position:y", number.position.y - 65, 0.8)
	tween.tween_property(number, "modulate:a", 0.0, 0.8)
	tween.chain().tween_callback(number.queue_free)

func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo or Game.room.is_empty(): return
	if event.keycode >= KEY_1 and event.keycode <= KEY_5:
		var index: int = event.keycode - KEY_1
		var hand: Array = Game.room.get("player", {}).get("hand", [])
		if Game.allowed("battle.play_cards") and index < hand.size(): Game.toggle_card(hand[index].instance_id)
	elif event.keycode == KEY_SPACE: Game.play_cards()
	elif event.keycode == KEY_R: Game.gateway.send("room.snapshot.read")
