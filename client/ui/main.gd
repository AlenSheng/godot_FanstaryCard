extends Control

const P = preload("res://ui/palette.gd")
const Art = preload("res://ui/art.gd")
const CardView = preload("res://ui/card_view.gd")
const ReferenceUI = preload("res://ui/reference_ui.gd")
const BoundedBar = preload("res://ui/bounded_bar.gd")
const EquipmentDetails = preload("res://ui/equipment_details.gd")
const InventoryView = preload("res://ui/inventory_view.gd")
const CardDetails = preload("res://ui/card_details.gd")
const BattleDetails = preload("res://ui/battle_details.gd")
const AudioSettings = preload("res://ui/audio_settings.gd")
const CATALOG = preload("res://data/catalog.json")
const DESCRIPTIONS = preload("res://data/card_descriptions.json")
const UI_CONFIG = preload("res://data/ui_config.json")
var screen := "hall"
var content: VBoxContainer
var root_column: VBoxContainer
var status_label: Label
var toast_label: Label
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
var _toast_serial := 0
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
var _codex_ready := false
var _codex_mutating := false
var _enhancement_quote: Dictionary = {}
var _enhancement_quote_key := ""
var _toast_tween: Tween
var _game_title: Label

func _ready() -> void:
	theme = P.theme()
	for card in CATALOG.data.tables.Cards: cards[card.id] = card
	_login_address = Game.gateway.base_url
	if not Game.gateway.local_account_name.is_empty(): _login_name = Game.gateway.local_account_name
	_session_generation = Game.gateway.session_generation
	Game.changed.connect(_schedule_render)
	Game.notice.connect(_toast)
	Game.combat_feedback.connect(_feedback)
	_build_shell()
	var audio_settings := AudioSettings.new()
	audio_settings.name = "AudioSettings"
	add_child(audio_settings)
	_render()

func _build_shell() -> void:
	var background := TextureRect.new()
	_background = background
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	background.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	background.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if ResourceLoader.exists("res://assets/portal.png"):
		background.texture = load("res://assets/portal.png")
		background.modulate = Color(0.45, 0.58, 0.59)
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
	var game_title := _label(top, "幻境牌旅", 38, P.GOLD)
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
	toast_label = _label(self, "", 20, P.GOLD)
	toast_label.set_anchors_preset(Control.PRESET_CENTER)
	toast_label.position = Vector2(-300, -210)
	toast_label.size = Vector2(600, 48)
	toast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	toast_label.z_index = 100
	toast_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	toast_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	toast_label.custom_minimum_size.y = 34

func _schedule_render() -> void:
	if mail_modal_lock: return
	_sync_account_session()
	if is_instance_valid(_game_title): _game_title.text = P.localized_text("幻境牌旅")
	if _render_pending: return
	_render_pending = true
	_render.call_deferred()

func _sync_account_session() -> void:
	if _session_generation != Game.gateway.session_generation:
		_session_generation = Game.gateway.session_generation
		_reset_account_ui()
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
	_codex_ready = false
	_codex_mutating = false
	_shop_inventory_ready = false
	_enhancement_quote = {}
	_enhancement_quote_key = ""
	_combat_panels.clear()
	_toast_serial += 1
	if is_instance_valid(toast_label): toast_label.text = ""
	for key in ["exploration_map_open", "inventory_open", "relic_pile", "inventory_selected", "relic_selected", "pending_move", "item_detail_scroll"]:
		if has_meta(key): remove_meta(key)
	# Account-bound dialogs must not retain actions against the next login.
	for child in get_children():
		if child is Window:
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
		_background.texture = load("res://assets/portal.png")
		_background.modulate = Color(0.45, 0.58, 0.59)
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
		if screen == "cards" and Game.room.is_empty() and Game.settlement.is_empty():
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
	if Game.platform.local_login_enabled():
		_label(panel, "同名登录原账号，新名称自动注册新账号。", 20, P.MUTED)
	_label(panel, "服务器地址", 22, P.MUTED)
	var address := LineEdit.new()
	address.text = _login_address
	address.text_changed.connect(func(value): _login_address = value)
	panel.add_child(address)
	if Game.platform.local_login_enabled():
		_button(panel, "正在连接…" if Game.busy else "本地登录 / 注册", func(): Game.login(_login_address.strip_edges(), _login_name.strip_edges()), Game.busy)
	var steam_reason: String = Game.platform.login_unavailable_reason()
	_button(panel, "Steam 登录", func(): Game.login_steam(_login_address.strip_edges(), _login_name.strip_edges()), Game.busy or not steam_reason.is_empty())
	if not steam_reason.is_empty(): _label(panel, steam_reason, 20, P.MUTED)
	if not Game.authentication_reason.is_empty(): _label(panel, Game.authentication_reason, 22, P.GOLD)
	if not Game.configuration_error.is_empty(): _label(panel, Game.configuration_error, 22, P.GOLD)
	var about := _panel(row, 680)
	_label(about, "每一次深入，都是新的抉择", 34, P.GOLD)
	for value in ["三种职业 · 一套属于你的二十张牌", "五行连放 · 实时抽牌与目标选择", "只向内探索 · 在战斗与撤离之间取舍"]:
		_label(about, value, 25)

func _nav() -> void:
	var nav := _row(content)
	var names := {"hall": "营地", "cards": "图鉴 / 编组", "gear": "穿戴 / 强化", "shop": "金币商店", "market": "金币市场", "prep": "探索准备"}
	for key in names:
		var button := _button(nav, names[key], _navigate.bind(key), Game.busy or not Game.ticket.is_empty())
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		if screen == key: button.add_theme_stylebox_override("normal", Art.style("UI/CardCodex/card_codex_action_button_orange.png"))

func _navigate(value: String) -> void:
	var generation: int = Game.gateway.session_generation
	screen = value
	edit_mode = false
	_codex_card = ""
	_codex_scroll = 0
	_enhancement_quote_key = ""
	_enhancement_quote = {}
	if value == "shop": _shop_inventory_ready = false
	if value == "cards": _codex_ready = false
	if value in ["cards", "gear", "enhance", "shop", "market", "prep"]:
		screen_loading = true
		_render()
		var path: String = {"cards": "/cards", "gear": "/inventory", "enhance": "/inventory", "shop": "/shop/", "market": "/market/", "prep": "/inventory"}[value]
		var result: Dictionary = await Game.gateway.request("/api/v1" + path)
		if not _session_result_current(generation, result): return
		if result.ok:
			match value:
				"cards":
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
	Art.image(portal, Art.texture("UI/Hall/portal_panel.png"), Vector2(360, 240))
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
	_label(left, "编组 %s / 20" % Game.deck().get("cardIds", []).size())
	var consumables: Dictionary = inventory.get("consumables", {})
	for key in ["Free", "Advanced", "Top"]:
		var text: String = {"Free": "轻装行囊  20 / 0  · 免费", "Advanced": "高级行囊  28 / 1  · 持有 %s" % consumables.get("advancedBagCount", 0), "Top": "顶级行囊  36 / 3  · 持有 %s" % consumables.get("topBagCount", 0)}[key]
		var button := _button(left, text, func(): bag_tier = key; _render())
		if bag_tier == key: button.add_theme_stylebox_override("normal", Art.style("UI/CardCodex/card_codex_action_button_orange.png"))
	_label(left, "生命药剂 · 持有 %s · 最多携带 2 瓶" % consumables.get("healthPotionCount", 0), 22)
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

func _card_text(id: String, level: int = 0, element_override: String = "") -> String:
	var info: Dictionary = CardDetails.with_element(cards.get(id, {}), element_override)
	var source: String = info.get("source", "")
	var badge := "怪" if not info.get("is_codex", true) else P.word(info.get("hero_class", ""))
	var name: String = info.get("name", id)
	var descriptions: Dictionary = DESCRIPTIONS.data.get("zh-CN", DESCRIPTIONS.data.get("zh", {}))
	var description: String = descriptions.get("card.face.desc." + id, "")
	if level > 0 or not element_override.is_empty(): description = CardDetails.effect_text(CardDetails.at_level(info, level))
	if description.is_empty():
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

func _card_action(id: String, action: String) -> void:
	if Game.busy or _codex_mutating or not _codex_ready: return
	var entry := _owned_card(id)
	if entry.is_empty() or not entry.has("craftCost"): return
	if action == "dismantle" and deck_draft.count(id) >= int(entry.get("copyCount", 0)):
		_toast("当前编组正在使用这张卡，请先从编组移除")
		return
	_codex_mutating = true
	Game.busy = true
	_render()
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1/cards/%s/%s" % [id.uri_encode(), action], HTTPClient.METHOD_POST, {"expectedVersion": int(entry.get("version", 0))})
	if not _session_result_current(generation, result):
		_codex_mutating = false
		return
	if result.ok:
		if result.data.get("materials") is Dictionary: Game.lobby["materials"] = result.data.materials
		Sound.play_cue("upgrade" if action == "upgrade" else "reward")
		_toast({"craft": "合成成功，已获得 1 张卡牌", "dismantle": "分解成功，材料已返还", "upgrade": "升级成功，卡牌效果已提升"}.get(action, "操作完成"))
	else: Sound.play_cue("error")
	var refreshed: Dictionary = await Game.gateway.request("/api/v1/cards")
	if not _session_result_current(generation, refreshed):
		_codex_mutating = false
		return
	_codex_ready = refreshed.ok
	if refreshed.ok: owned = refreshed.data
	await Game.refresh_lobby()
	_codex_mutating = false
	if not _session_result_current(generation): return
	Game.busy = false
	_render()

func _codex() -> void:
	var header := _row(content)
	_label(header, "卡牌图鉴", 42, P.GOLD)
	_label(header, "编组 %s / 20" % deck_draft.size(), 30)
	_button(header, "保存编组", _save_deck, deck_draft.size() != 20 or Game.busy)
	_button(header, "还原", func(): deck_draft = Game.deck().get("cardIds", []).duplicate(); _render())
	var deck_row := HFlowContainer.new()
	content.add_child(deck_row)
	for index in range(deck_draft.size()):
		var id: String = deck_draft[index]
		_button(deck_row, "%s ×" % cards.get(id, {}).get("name", id), func(): deck_draft.remove_at(index); _render())
	var resources: Dictionary = Game.lobby.get("materials", {})
	_label(content, "勇士之魂 %s   ·   职业之魂 %s" % [resources.get("warriorSoul", 0), resources.get(Game.hero_class.to_lower() + "Soul", 0)], 22, P.MUTED)
	var grid := GridContainer.new()
	grid.columns = 6
	content.add_child(grid)
	for card in owned:
		var class_value: Variant = card.get("heroClass")
		if class_value != null and class_value != Game.hero_class: continue
		var id: String = card.cardId
		var can_add: bool = card.get("unlocked", false) and deck_draft.size() < 20 and deck_draft.count(id) < int(card.get("copyCount", 0))
		if cards.get(id, {}).get("quality", "") == "Orange":
			for entry in deck_draft:
				var existing: Dictionary = cards.get(entry, {})
				if existing.get("quality") == "Orange" and (existing.get("hero_class") == null) == (class_value == null): can_add = false
		var button := _card_button(grid, id, func(): deck_draft.append(id); _render(), false, not can_add)
		button.tooltip_text += "\n已编入 %s / 持有 %s · 等级 %s" % [deck_draft.count(id), card.copyCount, card.level]

func _save_deck() -> void:
	if Game.busy: return
	Game.busy = true
	_render()
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1/decks/" + Game.hero_class, HTTPClient.METHOD_PUT, {"cardIds": deck_draft, "expectedVersion": Game.deck().get("version", 0)})
	if not _session_result_current(generation, result): return
	await Game.refresh_lobby()
	if not _session_result_current(generation): return
	var refreshed: Dictionary = await Game.gateway.request("/api/v1/cards")
	if not _session_result_current(generation, refreshed): return
	_codex_ready = refreshed.ok
	if refreshed.ok: owned = refreshed.data
	Game.busy = false
	if result.ok:
		Sound.play_cue("equip")
		_toast("编组已保存")
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

func _comparison(item: Dictionary) -> String:
	var gear: Dictionary = EquipmentDetails.equipment(item)
	var worn: Array = Game.room.get("player", {}).get("equipped_items", []) if not Game.room.is_empty() else inventory.get("equipments", []).filter(func(value): return value.get("instanceId", "") in gear_draft)
	var current: Dictionary = {}
	for candidate in worn:
		if EquipmentDetails.equipment(candidate).get("slot", "") == gear.get("slot", ""):
			current = candidate
			break
	return "所选装备\n%s\n\n当前同部位\n%s" % [EquipmentDetails.description(item), "未穿戴" if current.is_empty() else EquipmentDetails.description(current)]

func _show_equipment_details(item: Dictionary, action: Callable = Callable(), action_title: String = "穿戴") -> void:
	var dialog := AcceptDialog.new()
	dialog.title = P.localized_text("装备对比")
	var column := VBoxContainer.new()
	column.custom_minimum_size.x = 680
	dialog.add_child(column)
	_label(column, _comparison(item), 24)
	if action.is_valid(): _button(column, action_title, func(): dialog.queue_free(); action.call(), Game.busy)
	add_child(dialog)
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	dialog.popup_centered(Vector2i(750, 690))

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
	if not quote.get("canEnhance", false): _toast("无法强化：碎片、同品质材料或物品状态不满足要求"); return
	var body := {"expectedVersion": quote.expectedVersion}
	var cost_text := "消耗 %s 装备碎片，强化到 +%s" % [quote.fragmentCost, quote.nextLevel]
	if int(quote.materialCount) == 0:
		_confirm(cost_text + "？", func(): _mutate("/equipment/" + item.instanceId + "/enhance", HTTPClient.METHOD_POST, body))
		return
	var dialog := AcceptDialog.new()
	dialog.title = "选择强化材料 · 材料将被消耗"
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(720, 390)
	dialog.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(column)
	_label(column, cost_text + "，另需同品质防具 ×1", 24)
	var count := 0
	for material in inventory.get("equipments", []):
		if material.instanceId == item.instanceId or material.get("location") != "Inventory" or material.quality != item.quality: continue
		count += 1
		_button(column, _equipment_name(material), func(): body.materialEquipmentId = material.instanceId; dialog.queue_free(); _confirm(cost_text + "，并消耗 " + _equipment_name(material) + "？", func(): _mutate("/equipment/" + item.instanceId + "/enhance", HTTPClient.METHOD_POST, body)))
	if count == 0: _label(column, "没有可用的同品质仓库材料。")
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
	if not quote.get("canEnhance", false): _toast("无法强化：碎片不足或已达最高等级"); return
	_confirm("消耗 %s 装备碎片，将本命武器强化到 +%s？" % [quote.fragmentCost, quote.nextLevel], func(): _mutate("/class-weapons/" + hero_class + "/enhance", HTTPClient.METHOD_POST, {"expectedVersion": quote.expectedVersion}))

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
		"Priest": return "治疗 +%s%%" % percent
		"Mage": return "焚弦额外充能 +%s%%（总充能上限 50%%）" % percent
		_: return "上盾额外 +%s" % (3 if level >= 4 else (2 if level >= 2 else 1))

func _shop() -> void:
	_label(content, "旅人补给", 44, P.GOLD)
	var grid := GridContainer.new()
	grid.columns = 3
	content.add_child(grid)
	for item in shop.get("products", []):
		var panel := _panel(grid, 535)
		_label(panel, P.word(item.kind), 30)
		var payload: Variant = JSON.parse_string(item.get("payload", "{}"))
		if payload is Dictionary and payload.has("cardId"): _label(panel, cards.get(payload.cardId, {}).get("name", payload.cardId), 26, P.TEAL)
		_label(panel, "%s 金币" % item.priceGold, 36, P.GOLD)
		_label(panel, "今日 %s / %s" % [item.purchased, item.limit], 22, P.MUTED)
		_button(panel, "购买", func(): _confirm("花费 %s 金币购买？" % item.priceGold, func(): _mutate("/shop/purchases", HTTPClient.METHOD_POST, {"productId": item.productId, "quantity": 1})), Game.busy or int(item.purchased) >= int(item.limit) or int(item.priceGold) > int(Game.lobby.wallet.gold))
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

func _session_result_current(generation: int, result: Dictionary = {}) -> bool:
	return generation == Game.gateway.session_generation and not result.get("stale_session", false)

func _confirm(message: String, action: Callable) -> void:
	var dialog := ConfirmationDialog.new()
	dialog.dialog_text = P.localized_text(message)
	dialog.title = P.localized_text("确认操作")
	dialog.ok_button_text = P.localized_text("确认")
	dialog.cancel_button_text = P.localized_text("取消")
	add_child(dialog)
	Art.button(dialog.get_ok_button(), "UI/CardCodex/card_codex_action_button_orange.png")
	Art.button(dialog.get_cancel_button(), "UI/CardCodex/card_codex_action_button_blue.png")
	dialog.confirmed.connect(func(): dialog.queue_free(); action.call())
	dialog.canceled.connect(dialog.queue_free)
	dialog.popup_centered(Vector2i(760, 260))

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
	_toast_serial += 1
	var serial := _toast_serial
	if is_instance_valid(_toast_tween): _toast_tween.kill()
	toast_label.text = P.localized_text(message)
	toast_label.modulate = Color(1, 1, 1, 1)
	toast_label.position = Vector2(-300, -210)
	toast_label.scale = Vector2(0.92, 0.92)
	_toast_tween = create_tween()
	_toast_tween.set_parallel(true)
	_toast_tween.tween_property(toast_label, "position:y", -282.0, 2.6).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	_toast_tween.tween_property(toast_label, "scale", Vector2.ONE, 0.22).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	_toast_tween.tween_property(toast_label, "modulate:a", 0.0, 0.65).set_delay(1.95)
	await get_tree().create_timer(8.0).timeout
	if serial == _toast_serial: toast_label.text = ""

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
