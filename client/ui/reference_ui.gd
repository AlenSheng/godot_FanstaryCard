extends Control

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const RemoteCopy = preload("res://ui/remote_copy.gd")
const CardDetails = preload("res://ui/card_details.gd")
const Exploration = preload("res://ui/exploration_view.gd")
const Codex = preload("res://ui/codex_view.gd")
const DeckBuilder = preload("res://ui/deck_builder_view.gd")
const EquipmentCompareModel = preload("res://ui/equipment_compare_model.gd")
const DragScroll = preload("res://ui/drag_scroll.gd")
const BLUE := "UI/CardCodex/card_codex_action_button_blue.png"
const ORANGE := "UI/CardCodex/card_codex_action_button_orange.png"
var host: Control

func build(source: Control) -> void:
	host = source
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	if not Game.settlement.is_empty():
		Exploration.build_settlement(self, host)
	elif not Game.room.is_empty():
		Exploration.build(self, host)
		if host.has_meta("pending_move"):
			if Game.allowed("room.move"):
				var move: Vector2i = host.get_meta("pending_move")
				Exploration.show_midlayer(self, host, move.x, move.y)
			else: host.remove_meta("pending_move")
	elif not Game._settlement_recovery_match_id.is_empty():
		Exploration.build_recovery(self)
	elif not Game.ready_prompt.is_empty():
		_ready_prompt()
	else:
		_header()
		if host.screen_loading:
			text("正在读取…", Rect2(700, 440, 520, 100), 40, P.GOLD)
			return
		match host.screen:
			"hall": _hall()
			"cards": _codex()
			"deck": _deck_builder()
			"prep": _preparation()
			"gear": _gear()
			"enhance": _enhance()
			"shop": _shop()
			"market": _market()
	text(Game.connection, Rect2(1260, 1038, 620, 30), 18, P.MUTED).horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

func text(value: String, rect: Rect2, font_size: int = 24, color: Color = P.PAPER, parent: Node = null, fit_to_rect: bool = true, localize: bool = true) -> Label:
	var label := Label.new()
	var display_text := P.localized_text(value) if localize else value
	label.text = display_text
	var typeface := P.font_for_text(display_text, font_size)
	label.add_theme_font_override("font", typeface)
	label.add_theme_font_size_override("font_size", P.fit_font_size(typeface, font_size, rect.size.y, rect.size.x - 8.0, display_text) if fit_to_rect else font_size)
	label.add_theme_color_override("font_color", color)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.clip_text = true
	(parent if parent != null else self).add_child(label)
	if not (parent != null and parent is Container):
		label.position = rect.position
		label.size = rect.size
	if fit_to_rect: P.fit_control_font(label, typeface, font_size, 8.0)
	return label

func picture(texture: Texture2D, rect: Rect2) -> TextureRect:
	var image := Art.image(self, texture, Vector2.ZERO)
	image.position = rect.position
	image.size = rect.size
	return image

func panel(rect: Rect2, key: String = "UI/CardCodex/card_codex_dialog_panel_normal.png", parent: Node = null) -> Control:
	var node := Panel.new()
	node.add_theme_stylebox_override("panel", Art.style(key))
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	(parent if parent != null else self).add_child(node)
	if not (parent != null and parent is Container):
		node.position = rect.position
		node.size = rect.size
	return node

func button(value: String, rect: Rect2, action: Callable, disabled: bool = false, key: String = BLUE, parent: Node = null) -> Button:
	var node := Button.new()
	node.text = P.localized_text(value)
	node.disabled = disabled
	node.pressed.connect(action)
	node.clip_text = true
	node.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	Art.button(node, key)
	(parent if parent != null else self).add_child(node)
	if not (parent != null and parent is Container):
		node.position = rect.position
		node.size = rect.size
	P.fit_control_font(node, P.font_for_text(node.text, 24), 24, 48.0)
	return node

func card(source: Control, id: String, rect: Rect2, action: Callable, selected: bool = false, disabled: bool = false, options: Dictionary = {}) -> Button:
	var node: Button = source._card_button(self, id, action, selected, disabled, options)
	node.name = "Card_" + id
	node.position = rect.position
	node.size = Vector2(218, 376)
	node.scale = rect.size / Vector2(218, 376)
	return node

func _scroll(rect: Rect2, horizontal: bool = false, parent: Node = null) -> ScrollContainer:
	var node := DragScroll.new()
	node.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO if horizontal else ScrollContainer.SCROLL_MODE_DISABLED
	node.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED if horizontal else ScrollContainer.SCROLL_MODE_AUTO
	(parent if parent != null else self).add_child(node)
	if not (parent != null and parent is Container):
		node.position = rect.position
		node.size = rect.size
	return node

func _header() -> void:
	if host.screen in ["cards", "deck"]:
		Codex.header(self, host, "卡牌图鉴" if host.screen == "cards" else P.localized("deck_builder_title"))
		return
	panel(Rect2(24, 18, 1872, 82))
	var names := {"hall": "幻想牌域", "cards": "卡牌图鉴", "prep": "探索准备", "gear": "装备穿戴", "enhance": "碎片强化", "shop": "金币商店", "market": "金币市场"}
	if host.screen == "hall":
		text(P.localized("game_title"), Rect2(55, 27, 390, 62), 46, P.GOLD).name = "HallTitle"
	else:
		var return_button := button("返回", Rect2(60, 32, 170, 52), host._navigate.bind("hall"), Game.busy or not Game.ticket.is_empty())
		return_button.name = "ReturnButton"
		return_button.set_meta("sound_cue", "")
		text(names.get(host.screen, "营地"), Rect2(240, 30, 500, 60), 38, P.GOLD)
	var player: Dictionary = Game.lobby.get("player", {})
	var identity := text("%s\nUID %s" % [player.get("displayName", ""), player.get("userId", "")], Rect2(745, 25, 530, 70), 20, P.MUTED, null, true, false)
	identity.name = "AccountIdentity"
	var legacy_switch := button("切换账号", Rect2(1285, 32, 180, 52), Game.logout, Game.busy)
	legacy_switch.name = "SwitchAccountButton"
	legacy_switch.visible = false
	picture(_item("Gold"), Rect2(1490, 35, 44, 44))
	var wallet_label := text("%s %s" % [P.localized_text("金币"), Game.lobby.get("wallet", {}).get("gold", 0)], Rect2(1546, 38, 220, 46), 28, P.GOLD)
	wallet_label.name = "WalletGold"
	if host.screen == "hall":
		var mail_button := button("", Rect2(34, 286, 96, 82), _mail)
		mail_button.name = "MailButton"
		mail_button.icon = Art.texture("UI/Hall/mail_button.png")
		mail_button.expand_icon = true
		mail_button.add_theme_constant_override("icon_max_width", 72)
		mail_button.tooltip_text = P.localized_text("邮件")
		var badge_style := StyleBoxFlat.new()
		badge_style.bg_color = Color("#b6292b")
		badge_style.border_color = Color("#f1b978")
		badge_style.set_border_width_all(2)
		badge_style.set_corner_radius_all(19)
		var badge := Panel.new()
		badge.name = "HallMailUnreadBadge"
		badge.add_theme_stylebox_override("panel", badge_style)
		badge.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(badge)
		badge.position = Vector2(103, 276)
		var unread_badge := text("", Rect2(Vector2.ZERO, Vector2(38, 38)), 21, Color.WHITE, badge, false)
		unread_badge.name = "HallMailUnreadCount"
		unread_badge.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		unread_badge.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		_update_hall_mail_badge()

func _update_hall_mail_badge() -> void:
	var badge: Panel = get_node_or_null("HallMailUnreadBadge")
	if badge == null: return
	var count := int(Game.mail.get("unreadCount", 0))
	badge.visible = count > 0
	if count <= 0: return
	var count_label: Label = badge.get_node("HallMailUnreadCount")
	count_label.text = str(count)
	var width := maxf(38.0, 16.0 + count_label.text.length() * 14.0)
	badge.size = Vector2(width, 38)
	count_label.position = Vector2.ZERO
	count_label.size = badge.size

func _item(kind: String) -> Texture2D:
	var configured_id: String = str({"Gold": "gold", "WarriorSoul": "warrior_soul", "EquipmentFragments": "equipment_fragments", "HealthPotion": "health_potion", "MageSoul": "class_soul:Mage", "PriestSoul": "class_soul:Priest", "GuardianSoul": "class_soul:Guardian"}.get(kind, ""))
	if not configured_id.is_empty():
		var configured: Texture2D = Art.item_texture({"kind": kind if not kind.ends_with("Soul") else ("ClassSoul" if kind != "WarriorSoul" else kind), "item_id": configured_id})
		if configured != null: return configured
	var names := {"Gold": "gold", "WarriorSoul": "warrior_soul", "EquipmentFragments": "fragments", "HealthPotion": "potion", "MageSoul": "mage_soul", "PriestSoul": "priest_soul", "GuardianSoul": "guardian_soul", "Helmet": "helmet", "Head": "helmet", "Chest": "chest", "Hands": "gauntlet", "Legs": "legs", "Feet": "boots"}
	return Art.texture("UI/Item/exploration_prep_item_icon_%s.png" % names[kind]) if names.has(kind) else null

func _hall() -> void:
	for i in range(3):
		var hero_class: String = ["Priest", "Mage", "Guardian"][i]
		var card_rect := Rect2(42 + i * 310, 118, 295, 138)
		var frame_key := "UI/Hall/class_card_frame_%s.png" % ["on" if hero_class == Game.hero_class else "off"]
		var node := button("", card_rect, Game.select_class.bind(hero_class), Game.busy or not Game.preparation.is_empty())
		node.tooltip_text = P.localized_text("%s · 生命上限 %s" % [P.CLASSES[hero_class][0], P.CLASSES[hero_class][2]])
		picture(Art.texture(frame_key), card_rect).name = "ClassCardFrame_" + hero_class
		var class_portrait: Texture2D = Art.texture("UI/Hall/class_card_portrait_%s.png" % hero_class.to_lower())
		if hero_class == "Priest": class_portrait = Art.portrait(hero_class)
		picture(class_portrait, Rect2(card_rect.position + Vector2(8, 7), Vector2(104, 124))).name = "ClassPortrait_" + hero_class
		text(P.CLASSES[hero_class][0], Rect2(card_rect.position + Vector2(118, 25), Vector2(116, 30)), 22, P.GOLD).name = "ClassName_" + hero_class
		picture(Art.texture("UI/Hall/class_card_heart.png"), Rect2(card_rect.position + Vector2(119, 74), Vector2(27, 27))).name = "ClassHeart"
		text(str(P.CLASSES[hero_class][2]), Rect2(card_rect.position + Vector2(148, 75), Vector2(42, 28)), 23, P.GOLD).name = "ClassMaximumHp_" + hero_class
		var class_label := P.localized_text({"Priest": "牧师", "Mage": "法师", "Guardian": "守护者"}[hero_class])
		var class_type_rect := Rect2(card_rect.position + Vector2(194, 73), Vector2(card_rect.size.x - 200, 32))
		text(class_label, class_type_rect, 22, P.GOLD).name = "ClassType_" + hero_class
	# The live frontend is deliberately 2D-only. Character art is a static
	# portrait layer over the generated layered backdrop; no GLB is instantiated.
	picture(Art.portrait(Game.hero_class), Rect2(310, 255, 570, 550)).name = "HeroPortrait"
	picture(Art.passive(Game.hero_class), Rect2(858, 275, 84, 84)).name = "HeroPassive"
	var portal_rect := Rect2(990, 153, 835, 550)
	picture(Art.texture("UI/Hall/portal_background_clean.png"), portal_rect)
	var portal_frame := Panel.new()
	portal_frame.add_theme_stylebox_override("panel", P.box(Color(0, 0, 0, 0), Color("8c6943"), 3))
	portal_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(portal_frame)
	portal_frame.position = portal_rect.position
	portal_frame.size = portal_rect.size
	text(P.localized("enter_chaos"), Rect2(1110, 180, 595, 76), 48, P.GOLD).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var ack_pending := not Game._settlement_ack_pending_id.is_empty()
	var prep_caption := P.localized("settlement_ack_pending_title" if ack_pending else "nav_prep")
	var prep_button := button(prep_caption, Rect2(1140, 640, 520, 96), host._navigate.bind("prep"), Game.busy, ORANGE)
	prep_button.set_meta("sound_cue", "")
	if ack_pending:
		var confirmation := text(P.localized("settlement_ack_pending_message"), Rect2(990, 746, 835, 46), 24, P.PAPER)
		confirmation.name = "SettlementConfirmationStatus"
		confirmation.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var entries := [["cards", "UI/Shop/card_pack.png", "hall_entry_cards"], ["gear", "UI/Item/exploration_prep_item_icon_chest.png", "hall_entry_gear"], ["deck", "UI/Hall/entry_icon_deck_build.png", "hall_entry_deck"], ["shop", "UI/Item/exploration_prep_item_icon_gold.png", "hall_entry_shop"], ["market", "UI/Hall/entry_icon_market.png", "hall_entry_market"], ["prep", "UI/Shop/backpack_advanced.png", "hall_entry_prep"], ["enhance", "UI/Shop/equipment_fragment_pack.png", "hall_entry_enhance"]]
	for i in range(entries.size()):
		var rect := Rect2(56 + i * 259, 802, 242, 223)
		var node := button("", rect, host._navigate.bind(entries[i][0]), Game.busy or not Game.ticket.is_empty())
		node.set_meta("sound_cue", "")
		node.tooltip_text = P.localized(entries[i][2])
		# Keep the generated texture and icon inside the decorative frame's safe area.
		var content_rect := Rect2(rect.position + Vector2(12, 11), rect.size - Vector2(24, 23))
		var entry_content := Control.new()
		entry_content.clip_contents = true
		entry_content.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(entry_content)
		entry_content.position = content_rect.position
		entry_content.size = content_rect.size
		var entry_background := Art.image(entry_content, Art.texture("UI/Hall/entry_background.png"), Vector2.ZERO)
		entry_background.position = Vector2.ZERO
		entry_background.size = entry_content.size
		entry_background.stretch_mode = TextureRect.STRETCH_SCALE
		var entry_icon := Art.image(entry_content, Art.texture(entries[i][1]), Vector2.ZERO)
		entry_icon.position = Vector2(25, 12)
		entry_icon.size = Vector2(168, 88)
		picture(Art.texture("UI/Hall/entry_frame.png"), rect)
		var entry_caption := P.localized(entries[i][2])
		var entry_title := text(entry_caption, Rect2(rect.position + Vector2(18, 112), Vector2(206, 70)), 28, P.GOLD, null, false)
		var entry_font := P.font_for_text(entry_caption, 28)
		var title_lines := maxi(1, entry_caption.count("\n") + 1)
		var title_line_height := (70.0 - entry_title.get_theme_constant("line_spacing") * (title_lines - 1) - 2.0) / float(title_lines)
		entry_title.add_theme_font_size_override("font_size", P.fit_font_size(entry_font, 28, title_line_height, 198.0, entry_caption))
		entry_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		entry_title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var version_label := text(P.localized("client_version") % str(Game.CATALOG.data.version), Rect2(42, 1038, 900, 30), 18, P.MUTED)
	version_label.name = "ClientVersion"

func _mail() -> void:
	var existing := get_node_or_null("MailModal")
	if existing != null:
		return
	var modal := Control.new()
	modal.name = "MailModal"
	modal.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	modal.mouse_filter = Control.MOUSE_FILTER_STOP
	modal.z_index = 50
	add_child(modal)
	var overlay := ColorRect.new()
	overlay.color = Color(0.02, 0.05, 0.06, 0.78)
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	modal.add_child(overlay)
	var frame := panel(Rect2(280, 115, 1360, 850), "UI/CardCodex/card_codex_dialog_panel_normal.png", modal)
	frame.mouse_filter = Control.MOUSE_FILTER_STOP
	text(P.localized_text("邮件"), Rect2(334, 145, 360, 60), 42, P.GOLD, modal)
	var unread_label := text(_mail_unread_summary(), Rect2(705, 159, 250, 38), 22, P.MUTED, modal)
	unread_label.name = "MailUnreadCount"
	button(P.localized_text("一键全领"), Rect2(1050, 145, 150, 52), _mail_action.bind(Game.claim_all_mail), false, ORANGE, modal)
	button(P.localized_text("全部已读"), Rect2(1215, 145, 150, 52), _mail_action.bind(Game.mark_all_mail_read), false, ORANGE, modal)
	button(P.localized_text("删除已读"), Rect2(1380, 145, 150, 52), _mail_action.bind(Game.delete_read_mail), false, BLUE, modal)
	button(P.localized_text("关闭"), Rect2(1490, 892, 130, 52), modal.queue_free, false, BLUE, modal)
	var list: Array = Game.mail.get("items", [])
	var list_panel := Control.new()
	list_panel.position = Vector2(340, 278)
	list_panel.size = Vector2(760, 600)
	modal.add_child(list_panel)
	var detail_panel := Control.new()
	detail_panel.position = Vector2(1130, 278)
	detail_panel.size = Vector2(450, 600)
	modal.add_child(detail_panel)
	text(P.localized_text("收件箱"), Rect2(340, 224, 360, 46), 28, P.GOLD, modal)
	text(P.localized_text("邮件详情"), Rect2(1140, 224, 360, 46), 28, P.GOLD, modal)
	var detail_root := Control.new()
	detail_root.name = "MailDetailRoot"
	detail_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	detail_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	detail_panel.add_child(detail_root)
	modal.set_meta("mail_detail_root", detail_root)
	modal.set_meta("mail_detail_panel", detail_panel)
	if list.is_empty():
		text(P.localized_text("暂无邮件"), Rect2(500, 500, 420, 60), 30, P.MUTED, modal)
		text(P.localized_text("选择一封邮件查看详情"), Rect2(1140, 500, 400, 60), 28, P.MUTED, modal)
		return
	var scroll := _scroll(Rect2(340, 278, 760, 600), false, modal)
	scroll.name = "MailListScroll"
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	_enable_mail_drag_scroll(scroll)
	var column := VBoxContainer.new()
	column.name = "MailListColumn"
	column.add_theme_constant_override("separation", 12)
	scroll.add_child(column)
	modal.set_meta("mail_list_column", column)
	_build_mail_rows(column)
	_refresh_mail_detail(modal)

func _build_mail_rows(column: VBoxContainer) -> void:
	for child in column.get_children():
		column.remove_child(child)
		child.queue_free()
	for raw_item in Game.mail.get("items", []):
		var item: Dictionary = raw_item if raw_item is Dictionary else {}
		var id := str(item.get("id", item.get("mailId", "")))
		var row := HBoxContainer.new()
		row.name = "MailRow_" + id
		# The scrolling column sizes itself from its children. Reserve the viewport
		# width here so the preview area is not collapsed by the action buttons.
		row.custom_minimum_size = Vector2(760, 112)
		column.add_child(row)
		var title := RemoteCopy.field(item, "title")
		if title.is_empty(): title = P.localized("system_mail")
		var unread := not bool(item.get("read", item.get("isRead", false)))
		var attachments: Array = item.get("attachments", []) if item.get("attachments", []) is Array else []
		var preview := RemoteCopy.field(item, "body").replace("\n", " ")
		if preview.length() > 54: preview = preview.substr(0, 54) + "…"
		var state_text := P.localized_text("未读") if unread else P.localized_text("已读")
		var open_area := Control.new()
		open_area.name = "MailOpenArea"
		open_area.custom_minimum_size = Vector2(0, 104)
		open_area.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		open_area.size_flags_vertical = Control.SIZE_EXPAND_FILL
		row.add_child(open_area)
		var open := button("", Rect2(0, 0, 0, 0), func(): _mail_select_by_id(id), false, BLUE, open_area)
		open.name = "MailOpen"
		open.set_meta("mail_id", id)
		open.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		open.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		var text_left := 88.0 if not attachments.is_empty() else 16.0
		if not attachments.is_empty():
			var attachment_icon := Art.image(open_area, _mail_attachment_texture(attachments[0]), Vector2(58, 58))
			attachment_icon.name = "MailAttachmentPreview"
			attachment_icon.position = Vector2(14, 22)
			attachment_icon.size = Vector2(58, 58)
			attachment_icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var title_label := Label.new()
		title_label.name = "MailTitle"
		title_label.text = "● %s  %s" % [state_text, title]
		title_label.set_anchors_preset(Control.PRESET_TOP_WIDE)
		title_label.offset_left = text_left
		title_label.offset_top = 10.0
		title_label.offset_right = -14.0
		title_label.offset_bottom = 43.0
		title_label.clip_text = true
		title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		title_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		title_label.add_theme_color_override("font_color", P.PAPER if unread else P.MUTED)
		open_area.add_child(title_label)
		P.fit_control_font(title_label, P.font_for_text(title_label.text, 23), 23, 16.0)
		var preview_label := Label.new()
		preview_label.name = "MailPreviewText"
		preview_label.text = preview if not preview.is_empty() else " "
		preview_label.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
		preview_label.offset_left = text_left
		preview_label.offset_top = -49.0
		preview_label.offset_right = -14.0
		preview_label.offset_bottom = -10.0
		preview_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		preview_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		preview_label.clip_text = true
		preview_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		preview_label.add_theme_color_override("font_color", Color("a5bbb7") if unread else Color("718681"))
		open_area.add_child(preview_label)
		P.fit_control_font(preview_label, P.font_for_text(preview_label.text, 18), 18, 16.0)
		if not attachments.is_empty():
			open.tooltip_text = _mail_attachment_tooltip(attachments[0])
		if not attachments.is_empty():
			var claim := button(P.localized_text("领取") if not bool(item.get("claimed", false)) else P.localized_text("已领取"), Rect2(0, 0, 0, 0), _mail_action.bind(Game.claim_mail.bind(id)), bool(item.get("claimed", false)), ORANGE, row)
			claim.name = "MailClaim"
			claim.custom_minimum_size = Vector2(112, 104)
		var can_delete := bool(item.get("read", false)) and (bool(item.get("claimed", false)) or attachments.is_empty())
		var remove := button(P.localized_text("删除"), Rect2(0, 0, 0, 0), _mail_action.bind(Game.delete_mail.bind(id)), not can_delete, BLUE, row)
		remove.name = "MailDelete"
		remove.custom_minimum_size = Vector2(112, 104)

func _mail_select(item: Dictionary) -> void:
	var id := str(item.get("id", item.get("mailId", "")))
	if id.is_empty(): return
	host.set_meta("mail_selected_id", id)
	_mark_mail_read_local(id)
	var modal := get_node_or_null("MailModal")
	if modal != null:
		_update_mail_row_read_state(modal, id)
		_refresh_mail_detail(modal)

func _mail_select_by_id(id: String) -> void:
	var item := _mail_item_by_id(id)
	if not item.is_empty(): _mail_select(item)

func _mail_item_by_id(id: String) -> Dictionary:
	for raw_item in Game.mail.get("items", []):
		var item: Dictionary = raw_item if raw_item is Dictionary else {}
		if str(item.get("id", item.get("mailId", ""))) == id: return item
	return {}

func _mail_unread_summary() -> String:
	return "%s %s / %s" % [P.localized_text("未读"), Game.mail.get("unreadCount", 0), Game.mail.get("items", []).size()]

func _refresh_mail_detail(modal: Control) -> void:
	var detail_root: Control = modal.get_meta("mail_detail_root", null)
	if not is_instance_valid(detail_root): return
	var selected := _mail_item_by_id(str(host.get_meta("mail_selected_id", "")))
	var first: Dictionary = {}
	if selected.is_empty() and not Game.mail.get("items", []).is_empty():
		first = Game.mail.items[0] if Game.mail.items[0] is Dictionary else {}
	if selected.is_empty() and not first.is_empty():
		var first_id := str(first.get("id", first.get("mailId", "")))
		host.set_meta("mail_selected_id", first_id)
		_mark_mail_read_local(first_id)
		if modal != null: _update_mail_row_read_state(modal, first_id)
		selected = _mail_item_by_id(first_id)
	var item := selected if not selected.is_empty() else first
	if item.is_empty():
		for child in detail_root.get_children():
			detail_root.remove_child(child)
			child.queue_free()
		text(P.localized_text("暂无邮件"), Rect2(0, 210, 450, 60), 30, P.MUTED, detail_root)
		return
	_mail_detail_panel(detail_root, item)

func _update_mail_row_states(modal: Control) -> void:
	var unread_label: Label = modal.get_node_or_null("MailUnreadCount")
	if unread_label != null:
		unread_label.text = _mail_unread_summary()
	_update_hall_mail_badge()
	var wallet_label: Label = get_node_or_null("WalletGold")
	if wallet_label != null:
		wallet_label.text = "%s %s" % [P.localized_text("金币"), Game.lobby.get("wallet", {}).get("gold", 0)]
	var column: VBoxContainer = modal.get_meta("mail_list_column", null)
	if not is_instance_valid(column): return
	_build_mail_rows(column)

func _update_mail_row_read_state(modal: Control, id: String) -> void:
	var unread_label: Label = modal.get_node_or_null("MailUnreadCount")
	if unread_label != null:
		unread_label.text = _mail_unread_summary()
	_update_hall_mail_badge()
	var column: VBoxContainer = modal.get_meta("mail_list_column", null)
	if not is_instance_valid(column): return
	var row: HBoxContainer = null
	for candidate in column.get_children():
		if candidate.name == "MailRow_" + id:
			row = candidate
			break
	if row == null: return
	var title_label: Label = row.get_node_or_null("MailOpenArea/MailTitle")
	if title_label == null: return
	var item := _mail_item_by_id(id)
	var title := RemoteCopy.field(item, "title")
	if title.is_empty(): title = P.localized("system_mail")
	title_label.text = "● %s  %s" % [P.localized_text("已读"), title]
	title_label.add_theme_color_override("font_color", P.MUTED)

func _mark_mail_read_local(id: String) -> void:
	for index in range(Game.mail.get("items", []).size()):
		var current: Dictionary = Game.mail.items[index]
		if str(current.get("id", current.get("mailId", ""))) == id:
			if not bool(current.get("read", current.get("isRead", false))):
				current["read"] = true
				Game.mail.items[index] = current
				Game.mail.unreadCount = maxi(0, int(Game.mail.get("unreadCount", 0)) - 1)
				Game.mark_mail_read(id, false)
			return

func _enable_mail_drag_scroll(scroll: ScrollContainer) -> void:
	var state := {"dragging": false}
	scroll.gui_input.connect(func(event: InputEvent):
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
			state["dragging"] = event.pressed
			if event.pressed: scroll.accept_event()
		elif event is InputEventMouseMotion and state["dragging"]:
			scroll.scroll_vertical = clampi(scroll.scroll_vertical - int(event.relative.y), 0, maxi(0, int(scroll.get_v_scroll_bar().max_value - scroll.get_v_scroll_bar().page)))
			scroll.accept_event()
	)

func _mail_detail_panel(parent: Control, item: Dictionary) -> void:
	for child in parent.get_children(): child.queue_free()
	var id := str(item.get("id", item.get("mailId", "")))
	if not id.is_empty() and not bool(item.get("read", item.get("isRead", false))): Game.mark_mail_read(id, false)
	var content := MarginContainer.new()
	content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	content.add_theme_constant_override("margin_left", 28)
	content.add_theme_constant_override("margin_right", 28)
	content.add_theme_constant_override("margin_top", 24)
	content.add_theme_constant_override("margin_bottom", 24)
	content.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(content)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 14)
	content.add_child(column)
	var title := RemoteCopy.field(item, "title")
	text(title if not title.is_empty() else P.localized("system_mail"), Rect2(0, 0, 0, 0), 34, P.GOLD, column)
	text("%s: %s" % [P.localized_text("发件人"), item.get("sender", "System")], Rect2(0, 0, 0, 0), 20, P.MUTED, column)
	var body := Label.new()
	body.text = RemoteCopy.field(item, "body")
	if body.text.is_empty(): body.text = str(item.get("content", ""))
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.custom_minimum_size.y = 120
	body.add_theme_font_override("font", P.font_for_text(body.text, 24))
	body.add_theme_font_size_override("font_size", 24)
	body.add_theme_color_override("font_color", P.PAPER)
	column.add_child(body)
	text(P.localized_text("附件"), Rect2(0, 0, 0, 0), 25, P.GOLD, column)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", Art.COMMON_CELL_GAP)
	grid.add_theme_constant_override("v_separation", Art.COMMON_CELL_GAP)
	grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(grid)
	var attachments: Array = item.get("attachments", []) if item.get("attachments", []) is Array else []
	for raw_attachment in attachments:
		var attachment: Dictionary = raw_attachment if raw_attachment is Dictionary else {}
		var quality := _mail_attachment_quality(attachment)
		var cell := panel(Rect2(0, 0, 0, 0), Art.COMMON_CELL_KEY, grid)
		cell.custom_minimum_size = Art.COMMON_CELL_DISPLAY_SIZE
		cell.mouse_filter = Control.MOUSE_FILTER_PASS
		cell.tooltip_text = _mail_attachment_tooltip(attachment)
		var base_frame := Art.image(cell, Art.texture(Art.COMMON_CELL_KEY), Vector2.ZERO)
		base_frame.name = "CommonItemFrame"
		base_frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		base_frame.modulate = _mail_quality_background(quality)
		base_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var quality_fill := ColorRect.new()
		quality_fill.name = "QualityBackground"
		# The source quality frame is 192px with an approximately 12px inner
		# border. Scale that inset with the rendered cell so the color reaches the
		# entire interior without covering the decorative border.
		quality_fill.color = _mail_quality_background(quality)
		quality_fill.color.a = 1.0
		var quality_frame := Art.image(cell, Art.texture(_mail_quality_frame_key(quality)), Vector2.ZERO)
		quality_frame.name = "QualityFrame"
		quality_frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		quality_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
		# Equipment frames use an opaque black center. Draw the quality color after
		# the frame and inset it so the frame's visible border remains untouched.
		quality_fill.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		var mail_inset := Art.COMMON_CELL_DISPLAY_SIZE.x * 12.0 / 192.0
		quality_fill.offset_left = mail_inset
		quality_fill.offset_top = mail_inset
		quality_fill.offset_right = -mail_inset
		quality_fill.offset_bottom = -mail_inset
		quality_fill.mouse_filter = Control.MOUSE_FILTER_IGNORE
		cell.add_child(quality_fill)
		var cell_column := VBoxContainer.new()
		cell_column.alignment = BoxContainer.ALIGNMENT_CENTER
		cell_column.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		cell_column.add_theme_constant_override("separation", 0)
		cell.add_child(cell_column)
		var icon := Art.image(cell_column, _mail_attachment_texture(attachment), Vector2(58, 58))
		icon.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		var kind := P.localized_word(_mail_attachment_kind(attachment))
		text(kind, Rect2(0, 0, 0, 0), 18, P.PAPER, cell_column)
		text("× %s" % _mail_attachment_amount(attachment), Rect2(0, 0, 0, 0), 22, P.GOLD, cell_column)
	var actions := HBoxContainer.new()
	actions.alignment = BoxContainer.ALIGNMENT_END
	column.add_child(actions)
	if not bool(item.get("claimed", false)) and not attachments.is_empty():
		button(P.localized_text("领取"), Rect2(0, 0, 0, 0), _mail_action.bind(Game.claim_mail.bind(id)), false, ORANGE, actions).custom_minimum_size = Vector2(160, 54)
	var can_delete := bool(item.get("read", true)) and (bool(item.get("claimed", false)) or attachments.is_empty())
	button(P.localized_text("删除"), Rect2(0, 0, 0, 0), _mail_action.bind(Game.delete_mail.bind(id)), not can_delete, BLUE, actions).custom_minimum_size = Vector2(160, 54)

func _mail_action(action: Callable) -> void:
	host.mail_modal_lock = true
	await action.call()
	var modal := get_node_or_null("MailModal")
	if modal != null:
		_refresh_mail_claimed_resources()
		_update_mail_row_states(modal)
		_refresh_mail_detail(modal)
	host.mail_modal_lock = false

func _refresh_mail_claimed_resources() -> void:
	var wallet_label := get_node_or_null("WalletGold") as Label
	if wallet_label != null:
		wallet_label.text = "%s %s" % [P.localized_text("金币"), Game.lobby.get("wallet", {}).get("gold", 0)]

func _mail_attachment_texture(attachment: Dictionary) -> Texture2D:
	var kind := _mail_attachment_kind(attachment)
	if kind == "Equipment":
		var raw_id := str(attachment.get("itemId", attachment.get("ItemId", attachment.get("item_id", ""))))
		var parts := raw_id.split("|", false)
		if parts.size() == 3:
			var quality := parts[0].capitalize()
			var element := parts[1].to_lower()
			var slot := parts[2].to_lower()
			var equipment_key := "Equipment/%s/%s_%s.png" % [quality, slot, element]
			var equipment_texture := Art.texture(equipment_key)
			if equipment_texture != null: return equipment_texture
	if kind == "Card" and not str(attachment.get("itemId", "")).is_empty():
		return Art.card(str(attachment.get("itemId", "")))
	if kind in ["AdvancedBag", "TopBag"]: return Art.product(kind)
	if kind == "Diamond": return Art.texture("UI/Item/exploration_prep_item_icon_gold.png")
	return _item(kind)

func _mail_attachment_kind(attachment: Dictionary) -> String:
	return str(attachment.get("kind", attachment.get("Kind", "Item")))

func _mail_attachment_quality(attachment: Dictionary) -> String:
	var raw := str(attachment.get("quality", attachment.get("Quality", "")))
	if raw.is_empty() and _mail_attachment_kind(attachment) == "Equipment":
		var item_id := str(attachment.get("itemId", attachment.get("ItemId", attachment.get("item_id", ""))))
		var parts := item_id.split("|", false)
		if not parts.is_empty(): raw = parts[0]
	if not raw.is_empty():
		var quality := raw.capitalize()
		if quality == "Common": return "White"
		if quality in ["White", "Green", "Blue", "Purple", "Orange", "Red"]: return quality
	return Art.item_quality_name(attachment)

func _mail_quality_frame_key(quality: String) -> String:
	return "UI/Prep/exploration_prep_equipment_slot_frame_%s.png" % quality.to_lower()

func _mail_quality_background(quality: String) -> Color:
	if quality == "Common": return Color("73777a")
	return Art.quality_color(quality).darkened(0.35)

func _mail_attachment_amount(attachment: Dictionary) -> int:
	return int(attachment.get("amount", attachment.get("Amount", 1)))

func _mail_attachment_tooltip(attachment: Dictionary) -> String:
	var kind := _mail_attachment_kind(attachment)
	var amount := _mail_attachment_amount(attachment)
	var lines: Array[String] = [P.localized_word(kind), "%s: %s" % [P.localized("tooltip_quantity"), amount]]
	if kind == "Equipment":
		var raw_id := str(attachment.get("itemId", attachment.get("ItemId", attachment.get("item_id", ""))))
		var parts := raw_id.split("|", false)
		if parts.size() == 3:
			lines.insert(0, "%s · %s · %s" % [P.localized_word(parts[0]), P.localized_word(parts[1]), P.localized_word(parts[2])])
			lines.append("%s: %s" % [P.localized("tooltip_quality"), P.localized_word(parts[0])])
			lines.append("%s: %s" % [P.localized("tooltip_element"), P.localized_word(parts[1])])
			lines.append("%s: %s" % [P.localized("tooltip_slot"), P.localized_word(parts[2])])
	return "\n".join(lines)

func _codex() -> void:
	Codex.build(self, host)

func _deck_builder() -> void:
	DeckBuilder.build(self, host)

func _unhandled_key_input(event: InputEvent) -> void:
	if host != null and host.screen == "cards" and not host._codex_card.is_empty() and event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		if not host._codex_mutating:
			Codex.close_details(self, host)

func _loadout(rect: Rect2, editable: bool, snapshot: Dictionary = {}) -> void:
	var hero_class: String = snapshot.get("heroClass", Game.hero_class)
	var equipment_ids: Array = snapshot.get("equipmentIds", host.gear_draft if editable else Game.loadout().get("equipmentIds", []))
	var equipment_values: Array = snapshot.get("equipmentSnapshots") if snapshot.get("equipmentSnapshots") is Array else host.inventory.get("equipments", [])
	picture(Art.portrait(hero_class), Rect2(rect.position + Vector2(rect.size.x * 0.26, 105), Vector2(rect.size.x * 0.48, 535))).name = "HeroPortrait"
	text(P.CLASSES[hero_class][0], Rect2(rect.position + Vector2(45, 26), Vector2(400, 60)), 36, P.GOLD)
	var slots := ["Head", "Chest", "Hands", "Legs", "Feet"]
	var locations := [Vector2(40, 133), Vector2(40, 320), Vector2(40, 507), Vector2(rect.size.x - 165, 133), Vector2(rect.size.x - 165, 320)]
	for i in range(5):
		var id: Variant = equipment_ids[i] if i < equipment_ids.size() else null
		var item: Dictionary = {}
		for owned in equipment_values:
			if owned.instanceId == id: item = owned
		var point: Vector2 = rect.position + locations[i]
		var quality: String = str(item.get("quality", "common")).to_lower()
		var slot_color := _mail_quality_background(quality.capitalize()) if id != null else Art.UNEQUIPPED_SLOT_COLOR
		var slot_base := panel(Rect2(point, Vector2(120, 120)), Art.COMMON_CELL_KEY)
		slot_base.name = "CommonItemFrame_%s" % slots[i]
		slot_base.mouse_filter = Control.MOUSE_FILTER_IGNORE
		slot_base.add_theme_stylebox_override("panel", Art.style(Art.COMMON_CELL_KEY, slot_color))
		var slot_frame := Art.image(self, Art.texture(_mail_quality_frame_key(quality.capitalize())), Vector2.ZERO)
		slot_frame.name = "QualityFrame_%s" % slots[i]
		slot_frame.position = point
		slot_frame.size = Vector2(120, 120)
		slot_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
		slot_frame.modulate = Color.WHITE if id != null else Art.UNEQUIPPED_FRAME_MODULATE
		var slot_fill := ColorRect.new()
		slot_fill.name = "QualityBackground_%s" % slots[i]
		slot_fill.color = slot_color
		slot_fill.color.a = 1.0
		var slot_inset := 120.0 * 12.0 / 192.0
		slot_fill.position = point + Vector2(slot_inset, slot_inset)
		slot_fill.size = Vector2(120.0 - slot_inset * 2.0, 120.0 - slot_inset * 2.0)
		slot_fill.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(slot_fill)
		var slot := Button.new()
		slot.flat = true
		slot.position = point
		slot.size = Vector2(120, 120)
		slot.disabled = not editable or id == null
		slot.pressed.connect(func(): host.gear_draft.resize(5); host.gear_draft[i] = null; host._render())
		for state in ["normal", "hover", "pressed", "disabled"]:
			slot.add_theme_stylebox_override(state, StyleBoxEmpty.new())
		add_child(slot)
		slot.tooltip_text = host.EquipmentDetails.description(item) if not item.is_empty() else P.word(slots[i]) + P.localized("equipment_unequipped_suffix")
		var equipment_image := Art.equipment_texture(item) if not item.is_empty() else _item(slots[i])
		var equipment_icon := picture(equipment_image, Rect2(point + Vector2(18, 12), Vector2(84, 84)))
		equipment_icon.name = ("EquippedItem_" if id != null else "UnequippedItem_") + slots[i]
		equipment_icon.modulate = Color.WHITE if id != null else Art.UNEQUIPPED_ITEM_MODULATE
		var caption: String = host.EquipmentDetails.title(item) if id != null and str(item.get("effectAffix", item.get("effect_affix", ""))) not in ["", "<null>"] else P.word(slots[i]) + (" +%s" % item.get("level", 0) if id != null else "")
		var caption_label := text(caption, Rect2(point + Vector2(2, 125), Vector2(165, 48)), 21, P.MUTED)
		caption_label.name = "EquippedCaption_%s" % slots[i]
	var weapon_pos := rect.position + Vector2(rect.size.x - 165, 507)
	var weapon_base := panel(Rect2(weapon_pos, Vector2(120, 120)), Art.COMMON_CELL_KEY)
	weapon_base.name = "CommonItemFrame_Weapon"
	weapon_base.mouse_filter = Control.MOUSE_FILTER_IGNORE
	weapon_base.add_theme_stylebox_override("panel", Art.style(Art.COMMON_CELL_KEY, _mail_quality_background("Orange")))
	var weapon_frame := Art.image(self, Art.texture(_mail_quality_frame_key("Orange")), Vector2.ZERO)
	weapon_frame.name = "QualityFrame_Weapon"
	weapon_frame.position = weapon_pos
	weapon_frame.size = Vector2(120, 120)
	weapon_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var weapon_fill := ColorRect.new()
	weapon_fill.name = "QualityBackground_Weapon"
	weapon_fill.color = _mail_quality_background("Orange")
	weapon_fill.color.a = 1.0
	var weapon_inset := 120.0 * 12.0 / 192.0
	weapon_fill.position = weapon_pos + Vector2(weapon_inset, weapon_inset)
	weapon_fill.size = Vector2(120.0 - weapon_inset * 2.0, 120.0 - weapon_inset * 2.0)
	weapon_fill.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(weapon_fill)
	picture(Art.texture("UI/Item/exploration_prep_item_icon_weapon_%s.png" % hero_class.to_lower()), Rect2(weapon_pos + Vector2(12, 12), Vector2(96, 96)))
	var weapon_caption_offset := Vector2(27, 127) if editable else Vector2(-8, 127)
	var weapon_caption := text("本命 +%s · 锁定" % snapshot.classWeaponLevel if snapshot.has("classWeaponLevel") else "本命 · 锁定", Rect2(weapon_pos + weapon_caption_offset, Vector2(180, 40)), 21, P.GOLD)
	weapon_caption.name = "SignatureWeaponCaption"

func _preparation() -> void:
	var locked: bool = not Game.preparation.is_empty()
	var snap: Dictionary = Game.preparation.get("snapshot", {})
	panel(Rect2(28, 122, 752, 900))
	panel(Rect2(798, 122, 1094, 900))
	_loadout(Rect2(45, 140, 715, 720), false, snap)
	var equipped_items: Array = []
	if snap.get("equipmentSnapshots") is Array:
		equipped_items = snap.get("equipmentSnapshots", [])
	else:
		var equipped_ids: Array = Game.loadout().get("equipmentIds", [])
		for item in host.inventory.get("equipments", []):
			if item.get("instanceId", "") in equipped_ids: equipped_items.append(item)
	_equipment_summary(equipped_items, Rect2(65, 822, 680, 178), int(snap.get("maximumHp", P.CLASSES[Game.hero_class][2])))
	text(P.localized("bag"), Rect2(845, 145, 550, 65), 38, P.GOLD)
	var consumables: Dictionary = host.inventory.get("consumables", {})
	var stock := {"Advanced": int(consumables.get("advancedBagCount", 0)), "Top": int(consumables.get("topBagCount", 0))}
	if not locked and host.bag_tier != "Free" and stock.get(host.bag_tier, 0) <= 0:
		host.bag_tier = "Free"
	text(P.localized("bag_stock_summary") % [stock.Advanced, stock.Top], Rect2(1390, 162, 440, 38), 23, P.MUTED)
	var tier: String = snap.get("backpackTier", host.bag_tier)
	var capacity: int = int(snap.get("backpackCapacity", {"Free": 20, "Advanced": 28, "Top": 36}.get(tier, 20)))
	var safe_slots: Array = snap.get("safeSlotIndexes", [] if tier == "Free" else ([27] if tier == "Advanced" else [33, 34, 35]))
	var safe_slot_lookup: Dictionary = {}
	var slot_order: Array = []
	for value in safe_slots:
		var safe_index := int(value)
		if safe_index >= 0 and safe_index < capacity and not safe_slot_lookup.has(safe_index):
			safe_slot_lookup[safe_index] = true
			slot_order.append(safe_index)
	for slot_index in range(capacity):
		if not safe_slot_lookup.has(slot_index): slot_order.append(slot_index)
	for i in range(3):
		var key: String = ["Free", "Advanced", "Top"][i]
		var title_key: String = ["bag_option_free", "bag_option_advanced", "bag_option_top"][i]
		var title: String = P.localized(title_key)
		# Free is the built-in tier and is not represented in consumables; only
		# paid backpack tiers are gated by their inventory counts.
		var available_count := 0 if i == 0 else int(stock.get(key, 0))
		var unavailable: bool = locked or (i > 0 and available_count <= 0)
		var tab := button(title if i == 0 else "", Rect2(845 + i * 328, 219, 307, 93), func(): host.bag_tier = key; host._render(), unavailable, ORANGE if tier == key else BLUE)
		tab.name = "Backpack_" + key
		tab.set_meta("sound_cue", "ui_tab")
		if i > 0:
			picture(Art.product(key + "Bag"), Rect2(860 + i * 328, 226, 68, 78)).name = "BackpackIcon_" + key
			text(title.split("\n")[0], Rect2(937 + i * 328, 228, 202, 37), 25, P.MUTED if unavailable else P.PAPER)
			text(title.split("\n")[1], Rect2(937 + i * 328, 267, 202, 32), 20, P.GOLD if tier == key else P.MUTED)
		tab.tooltip_text = P.localized_text("持有 %s 个" % available_count)
	var row_count := int(ceil(float(capacity) / 6.0))
	var bag_scroll := _scroll(Rect2(845, 342, 1000, 408))
	bag_scroll.name = "PreparationBackpackScroll"
	var bag_content := Control.new()
	bag_content.name = "PreparationBackpackGrid"
	bag_content.custom_minimum_size = Vector2(970, maxi(0, row_count * 104 - Art.COMMON_CELL_GAP))
	bag_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bag_content.mouse_filter = Control.MOUSE_FILTER_PASS
	bag_scroll.add_child(bag_content)
	for display_index in range(capacity):
		var slot_index: int = int(slot_order[display_index])
		var point := Vector2((display_index % 6) * 163, int(display_index / 6) * 104)
		var slot := Control.new()
		slot.name = "PreparationBackpackSlot_%s" % slot_index
		slot.position = point
		slot.size = Art.COMMON_CELL_DISPLAY_SIZE
		slot.custom_minimum_size = Art.COMMON_CELL_DISPLAY_SIZE
		slot.mouse_filter = Control.MOUSE_FILTER_IGNORE
		slot.tooltip_text = P.localized("equipment_safe_slots") % (slot_index + 1) if safe_slot_lookup.has(slot_index) else str(slot_index + 1)
		bag_content.add_child(slot)
		if safe_slot_lookup.has(slot_index):
			Art.add_safe_slot_frame(slot)
		else:
			panel(Rect2(Vector2.ZERO, Art.COMMON_CELL_DISPLAY_SIZE), Art.COMMON_CELL_KEY, slot)
			text(str(slot_index + 1), Rect2(8, 8, 80, 48), 19, P.MUTED, slot)
	picture(_item("HealthPotion"), Rect2(850, 775, 64, 74))
	text(P.localized("health_potion_summary") % consumables.get("healthPotionCount", 0), Rect2(930, 776, 630, 45), 25)
	var count := SpinBox.new()
	count.max_value = mini(2, int(consumables.get("healthPotionCount", 0)))
	count.value = snap.get("potionCount", host.potion_count)
	count.editable = not locked
	count.value_changed.connect(func(value): host.potion_count = int(value))
	add_child(count)
	count.position = Vector2(1560, 773)
	count.size = Vector2(270, 66)
	if locked:
		button("取消匹配 / 准备", Rect2(850, 915, 410, 61), Game.cancel_preparation, Game.busy)
		button("正在匹配…" if not Game.ticket.is_empty() else "开始匹配", Rect2(1310, 915, 520, 61), Game.enqueue, Game.busy or not Game.gateway.online or not Game.ticket.is_empty(), ORANGE)
	else:
		button("确认探索准备", Rect2(1100, 915, 730, 61), func(): Game.prepare(host.bag_tier, host.potion_count), Game.busy, ORANGE)

func _gear() -> void:
	_loadout(Rect2(90, 135, 1030, 750), true)
	_equipment_summary(host._equipped_items())
	var save_loadout_button := button("保存穿戴", Rect2(410, 939, 385, 68), func(): host._mutate("/loadouts/" + Game.hero_class, HTTPClient.METHOD_PUT, {"equipmentIds": host.gear_draft, "expectedVersion": Game.loadout().get("version", 0)}), Game.busy, ORANGE)
	save_loadout_button.name = "SaveLoadoutButton"
	panel(Rect2(1190, 136, 688, 886))
	text("仓库装备", Rect2(1235, 164, 520, 60), 36, P.GOLD)
	var scroll := DragScroll.new()
	scroll.name = "EquipmentInventoryScroll"
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	add_child(scroll)
	scroll.position = Vector2(1225, 255)
	scroll.size = Vector2(620, 625)
	var list := VBoxContainer.new()
	list.name = "EquipmentInventoryList"
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(list)
	for item in host.inventory.get("equipments", []):
		var row := HBoxContainer.new()
		list.add_child(row)
		Art.image(row, Art.equipment_texture(item) if Art.equipment_texture(item) != null else _item(item.slot), Vector2(68, 70))
		var selected: bool = item.get("instanceId", "") in host.gear_draft
		var entry_text: String = P.localized("equipment_worn_prefix" if selected else "equipment_equip_prefix") + host._equipment_name(item)
		var entry: Button = host._button(row, entry_text, func():
			if scroll.can_activate():
				if selected: host._equip(item)
				elif host._draft_high_quality_limit_would_block(item): host._toast(P.localized("loadout_high_quality_limit"))
				else: host._show_equipment_details(item, func(): host._equip(item)),
			Game.busy or item.get("location") not in ["Inventory", "Equipped"], BLUE if selected else ORANGE)
		entry.name = "EquipmentEntry_" + str(item.get("instanceId", ""))
		entry.tooltip_text = host.EquipmentDetails.description(item) + P.localized("equipment_draft_worn_tip" if selected else "equipment_draft_equip_tip")
		entry.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.set_deferred("scroll_vertical", host._equipment_scroll)
	scroll.get_v_scroll_bar().value_changed.connect(func(value): host._equipment_scroll = int(value))
	if list.get_child_count() == 0: text("仓库暂无装备\n探索撤离后可带回战利品", Rect2(1255, 362, 530, 160), 28, P.MUTED)
	var enhance_button := button("碎片强化", Rect2(1260, 930, 530, 64), host._navigate.bind("enhance"))
	enhance_button.set_meta("sound_cue", "")

func _equipment_summary(loadout: Array, rect: Rect2 = Rect2(225, 760, 755, 165), maximum_hp: int = -1) -> void:
	var compact := rect.size.x < 720.0
	var margin := 30.0 if compact else 40.0
	var gap := 30.0 if compact else 45.0
	var column_width := (rect.size.x - margin * 2.0 - gap) / 2.0
	var first_x := rect.position.x + margin
	var second_x := first_x + column_width + gap
	var title_y := rect.position.y + 22.0
	var body_y := rect.position.y + 54.0
	var body_height := 90.0 if compact else rect.size.y - 84.0
	var summary_panel := panel(rect)
	summary_panel.name = "EquipmentSummaryPanel"
	var attribute_title := text(P.localized("equipment_summary_title"), Rect2(first_x, title_y, column_width, 28), 21, P.GOLD)
	attribute_title.name = "EquipmentSummaryTitle"
	var set_title := text(P.localized("equipment_set_summary_title"), Rect2(second_x, title_y, column_width, 28), 21, P.GOLD)
	set_title.name = "EquipmentSetSummaryTitle"
	var attribute_lines := _equipment_attribute_lines(loadout)
	if maximum_hp >= 0: attribute_lines.push_front("%s %s" % [P.localized("hp"), maximum_hp])
	var attribute_text := "\n".join(attribute_lines) if not attribute_lines.is_empty() else P.localized("equipment_no_attributes")
	_equipment_summary_scroll("EquipmentAttributeScroll", "EquipmentAttributeSummary", attribute_text, Rect2(first_x, body_y, column_width, body_height), 17, P.PAPER)
	var set_lines := _equipment_set_lines(loadout)
	var set_text := "\n".join(set_lines) if not set_lines.is_empty() else P.localized("equipment_no_sets")
	_equipment_summary_scroll("EquipmentSetScroll", "EquipmentSetSummary", set_text, Rect2(second_x, body_y, column_width, body_height), 16, P.MUTED)

func _equipment_summary_scroll(scroll_name: String, label_name: String, value: String, rect: Rect2, font_size: int, color: Color) -> ScrollContainer:
	var scroll := DragScroll.new()
	scroll.name = scroll_name
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_NEVER
	add_child(scroll)
	scroll.position = rect.position
	scroll.size = rect.size
	var label := Label.new()
	label.name = label_name
	label.text = value
	label.add_theme_font_override("font", P.font_for_text(value, font_size))
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.mouse_filter = Control.MOUSE_FILTER_PASS
	var physical_lines := maxi(1, value.count("\n") + 1)
	label.custom_minimum_size = Vector2(rect.size.x, maxf(rect.size.y, physical_lines * 30.0))
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.tooltip_text = value
	scroll.add_child(label)
	return scroll

func _equipment_attribute_lines(loadout: Array) -> Array[String]:
	var totals := EquipmentCompareModel.aggregate_attributes(loadout)
	var lines: Array[String] = []
	for element in ["Fire", "Wood", "Water", "Metal", "Earth"]:
		var damage := float(totals.get("damage_" + element, 0.0))
		var resistance := float(totals.get("resistance_" + element, 0.0))
		if is_zero_approx(damage) and is_zero_approx(resistance): continue
		var values: Array[String] = []
		if not is_zero_approx(damage): values.append("%s %s" % [P.localized("battle_attack_bonus"), _summary_percent(damage)])
		if not is_zero_approx(resistance): values.append("%s %s" % [P.localized("resistance"), _summary_percent(resistance)])
		lines.append("%s · %s" % [P.word(element), " · ".join(values)])
	var secondary: Array[String] = []
	var draw_interval := float(totals.get("draw_interval", 0.0))
	var forced_escape := float(totals.get("forced_escape", 0.0))
	if not is_zero_approx(draw_interval): secondary.append("%s %s" % [P.localized("battle_draw_interval_seconds"), _summary_percent(draw_interval)])
	if not is_zero_approx(forced_escape): secondary.append("%s %s" % [P.localized("force_escape"), _summary_percent(forced_escape)])
	if not secondary.is_empty(): lines.append(" · ".join(secondary))
	return lines

func _equipment_set_lines(loadout: Array) -> Array[String]:
	var lines: Array[String] = []
	for state in EquipmentCompareModel.present_set_states(loadout):
		var status := P.localized("battle_active") if state.active else P.localized("battle_inactive")
		var line := P.localized("equipment_set_progress") % [P.word(state.kind), state.count, state.required, status]
		if state.active:
			match str(state.kind):
				"Piercing":
					line += "\n  " + P.localized("equipment_set_piercing") % _summary_percent(float(state.values.get("piercing_percent", 0.0)))
				"Bulwark":
					line += "\n  " + P.localized("equipment_set_bulwark") % [_summary_percent(float(state.values.get("bulwark_shield_percent", 0.0))), _summary_percent(float(state.values.get("bulwark_reduction_percent", 0.0)))]
				"Vitality":
					line += "\n  " + P.localized("equipment_set_vitality") % [_summary_percent(float(state.values.get("vitality_heal_percent", 0.0))), _summary_percent(float(state.values.get("vitality_overcap_percent", 0.0)))]
		else:
			line += "\n  " + P.localized("equipment_set_%s_inactive" % str(state.kind).to_lower())
		lines.append(line)
	return lines

func _summary_percent(value: float) -> String:
	var prefix := "+" if value > 0.0 else ""
	return prefix + host.EquipmentDetails.percent(value) + "%"

func _enhance() -> void:
	panel(Rect2(30, 132, 470, 882))
	panel(Rect2(525, 130, 770, 884))
	panel(Rect2(1320, 132, 570, 882))
	text(P.localized("enhance_select_item"), Rect2(70, 166, 390, 58), 34, P.GOLD)
	button("本命武器 · " + P.CLASSES[Game.hero_class][1], Rect2(66, 254, 393, 94), func(): host._enhance_item = ""; host._render(), false, ORANGE if host._enhance_item.is_empty() else BLUE)
	var scroll := _scroll(Rect2(64, 378, 405, 602))
	var list := VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(list)
	var selected: Dictionary = {}
	for item in host.inventory.get("equipments", []):
		host._button(list, host._equipment_name(item), func(): host._enhance_item = item.instanceId; host._render(), item.get("location") not in ["Inventory", "Equipped"])
		if item.instanceId == host._enhance_item: selected = item
	var weapon: Dictionary = {}
	for entry in Game.lobby.get("classWeapons", []):
		if entry.heroClass == Game.hero_class: weapon = entry
	var level: int = int(selected.get("level", weapon.get("level", 0)))
	host._read_enhancement_quote(selected, weapon)
	var quote: Dictionary = host._enhancement_quote
	var title: String = host._equipment_name(selected) if not selected.is_empty() else P.CLASSES[Game.hero_class][1]
	var title_label := text(title, Rect2(625, 245, 570, 64), 42, P.GOLD)
	title_label.name = "EnhanceTitle"
	title_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var image: Texture2D = Art.equipment_texture(selected) if not selected.is_empty() else Art.texture("UI/Item/exploration_prep_item_icon_weapon_%s.png" % Game.hero_class.to_lower())
	picture(image, Rect2(720, 315, 350, 350))
	var benefit: String = host.EquipmentDetails.enhancement_text(selected) if not selected.is_empty() else P.localized("enhance_current_next") % [host._weapon_benefit(level), host._weapon_benefit(mini(5, level + 1))]
	text(benefit if level < 5 else P.localized("enhance_max_level"), Rect2(591, 690, 642, 252), 23, P.TEAL)
	if not selected.is_empty():
		button(preload("res://ui/numerical_details.gd").text("title"), Rect2(730, 940, 350, 54), func(): preload("res://ui/numerical_details.gd").show_compare(host, host._equipped_items(), selected, true))
	text(P.localized("enhance_progress"), Rect2(1375, 175, 450, 70), 38, P.GOLD)
	_enhance_progress(level)
	picture(_item("EquipmentFragments"), Rect2(1430, 439, 90, 108))
	text(P.localized("enhance_fragments_summary") % Game.lobby.get("materials", {}).get("equipmentFragments", 0), Rect2(1535, 445, 300, 115), 30)
	var cost: String = P.localized("enhance_loading_cost") if quote.is_empty() else P.localized("enhance_cost") % [quote.get("fragmentCost", 0), quote.get("availableMaterialCount", 0), quote.get("materialCount", 0)]
	if quote.get("error", false): cost = P.localized("enhance_quote_error")
	elif not quote.is_empty() and not quote.get("canEnhance", false) and level < 5: cost += "\n" + P.localized("enhance_requirement_error")
	text(cost, Rect2(1370, 604, 470, 176), 25, P.MUTED)
	button(P.localized("enhance_max_button") if level >= 5 else P.localized("enhance_to_button") % (level + 1), Rect2(1380, 823, 440, 86), func():
		if not selected.is_empty(): host._enhance(selected)
		else: host._enhance_weapon(), Game.busy or level >= 5 or not quote.get("canEnhance", false), ORANGE)

func _enhance_progress(level: int) -> void:
	var achieved := clampi(level, 0, 5)
	var count_label := text("%s / 5" % achieved, Rect2(1378, 253, 445, 43), 25, P.PAPER)
	count_label.name = "EnhanceProgressCount"
	count_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	var track_rect := Rect2(1378, 367, 445, 20)
	var track_style := StyleBoxFlat.new()
	track_style.bg_color = Color("#071b23")
	track_style.border_color = Color("#846341")
	track_style.set_border_width_all(2)
	track_style.set_corner_radius_all(9)
	var track := Panel.new()
	track.name = "EnhanceProgressTrack"
	track.add_theme_stylebox_override("panel", track_style)
	track.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(track)
	track.position = track_rect.position
	track.size = track_rect.size
	var stage_width := track_rect.size.x / 5.0
	if achieved > 0:
		var fill_style := StyleBoxFlat.new()
		fill_style.bg_color = Color("#db9140")
		fill_style.border_color = P.GOLD
		fill_style.set_border_width_all(2)
		fill_style.set_corner_radius_all(7)
		var fill := Panel.new()
		fill.name = "EnhanceProgressFill"
		fill.add_theme_stylebox_override("panel", fill_style)
		fill.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(fill)
		fill.position = track_rect.position + Vector2(3, 3)
		var current_marker_x := track_rect.position.x + stage_width * (float(achieved) - 0.5)
		fill.size = Vector2(current_marker_x - fill.position.x, track_rect.size.y - 6)
	for i in range(5):
		var marker_x := track_rect.position.x + stage_width * (float(i) + 0.5)
		var marker_style := StyleBoxFlat.new()
		marker_style.bg_color = P.GOLD if i < achieved else Color("#183440")
		marker_style.border_color = Color("#eac380") if i < achieved else Color("#7b756a")
		marker_style.set_border_width_all(2)
		marker_style.set_corner_radius_all(10)
		var marker := Panel.new()
		marker.name = "EnhanceProgressMarker_%s" % (i + 1)
		marker.add_theme_stylebox_override("panel", marker_style)
		marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(marker)
		marker.position = Vector2(marker_x - 10, track_rect.position.y - 1)
		marker.size = Vector2(20, 22)
		var label := text("+%s" % (i + 1), Rect2(marker_x - 36, 298, 72, 52), 29, P.GOLD if i < achieved else P.MUTED)
		label.name = "EnhanceProgressLabel_%s" % (i + 1)
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

func _shop() -> void:
	panel(Rect2(28, 138, 1864, 864))
	var consumables: Dictionary = host.inventory.get("consumables", {})
	var paid_bags: int = int(consumables.get("advancedBagCount", 0)) + int(consumables.get("topBagCount", 0))
	var scroll := DragScroll.new()
	scroll.name = "ShopScroll"
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)
	scroll.position = Vector2(55, 210)
	scroll.size = Vector2(1810, 700)
	var row := HBoxContainer.new()
	row.name = "ShopProductRow"
	row.add_theme_constant_override("separation", 20)
	scroll.add_child(row)
	for item in host.shop.get("products", []):
		var parsed: Variant = item.get("payload", {})
		var payload: Dictionary = parsed if parsed is Dictionary else {}
		var kind: String = item.get("kind", "")
		var product_title := _product_title(kind, payload)
		var item_panel := Panel.new()
		item_panel.name = "Product_" + str(item.productId)
		item_panel.set_meta("kind", kind)
		item_panel.set_meta("payload", str(item.get("payload", "")))
		item_panel.custom_minimum_size = Vector2(240, 640)
		item_panel.add_theme_stylebox_override("panel", Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png"))
		row.add_child(item_panel)
		var title := Label.new()
		title.text = P.localized_text(product_title)
		title.add_theme_font_override("font", P.font("title"))
		title.position = Vector2(20, 32)
		title.size = Vector2(200, 70)
		title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		title.mouse_filter = Control.MOUSE_FILTER_IGNORE
		item_panel.add_child(title)
		var image := Art.image(item_panel, _product_art(kind, payload), Vector2.ZERO)
		image.name = "ProductArt"
		var is_guaranteed_card: bool = kind == "Cards" and payload.has("cardId")
		if is_guaranteed_card:
			_shop_card_presentation(item_panel, image, payload)
		else:
			image.position = Vector2(30, 127)
			image.size = Vector2(180, 230)
		var detail := Label.new()
		detail.name = "ShopDetail"
		var amount: int = int(payload.get("amount", payload.get("count", 0)))
		var quantity_line := (P.localized("shop_quantity_line") % amount) + "\n" if amount > 0 else ""
		detail.text = quantity_line + (P.localized("shop_purchase_count") % [item.purchased, item.limit]) + "\n" + (P.localized("shop_price") % item.priceGold)
		detail.position = Vector2(20, 468) if is_guaranteed_card else Vector2(20, 371)
		detail.size = Vector2(200, 70) if is_guaranteed_card else Vector2(200, 160)
		detail.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		detail.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		detail.mouse_filter = Control.MOUSE_FILTER_IGNORE
		item_panel.add_child(detail)
		var is_bag: bool = kind in ["AdvancedBag", "TopBag"]
		var stock_full: bool = is_bag and paid_bags + maxi(1, amount) > 3
		var stock_unknown: bool = is_bag and not host._shop_inventory_ready
		var already_owned: bool = is_guaranteed_card and bool(item.get("alreadyOwned", false))
		var buy_text := P.localized("refresh_inventory") if stock_unknown else (P.localized("inventory_full") if stock_full else (P.localized("activated") if already_owned else P.localized("buy")))
		var buy: Button = host._button(item_panel, buy_text, func(): host._purchase_shop_item(item, product_title), Game.busy or stock_unknown or stock_full or already_owned or int(item.purchased) >= int(item.limit) or int(item.priceGold) > int(Game.lobby.get("wallet", {}).get("gold", 0)))
		buy.name = "Purchase"
		Art.button(buy, ORANGE)
		buy.position = Vector2(26, 546)
		buy.size = Vector2(188, 66)
	if row.get_child_count() == 0: text("暂无商品，请稍后刷新", Rect2(640, 440, 790, 95), 34, P.MUTED)
	var stock_key := "shop_stock_summary" if host._shop_inventory_ready else "shop_stock_refresh"
	var stock_text := P.localized(stock_key) % paid_bags if host._shop_inventory_ready else P.localized(stock_key)
	text(stock_text, Rect2(85, 908, 950, 34), 20, P.MUTED).name = "ShopStockSummary"
	var refresh_used := int(host.shop.get("refreshesUsed", 0))
	var refresh_limit := int(host.shop.get("refreshLimit", 0))
	var refresh_remaining := maxi(0, refresh_limit - refresh_used)
	text("每日刷新次数：剩余 %s / %s" % [refresh_remaining, refresh_limit], Rect2(85, 944, 950, 42), 24, P.GOLD)
	var refresh_button := button(P.localized("refresh"), Rect2(1630, 929, 190, 54), host._refresh_shop, Game.busy or refresh_remaining <= 0, ORANGE)
	refresh_button.name = "RefreshShopButton"
	host._restore_shop_scroll(scroll)

func sync_shop_state(changed_product_id: String = "") -> bool:
	var row := get_node_or_null("ShopScroll/ShopProductRow") as HBoxContainer
	if row == null: return false
	var products: Array = host.shop.get("products", [])
	if row.get_child_count() != products.size(): return false
	for index in products.size():
		var product: Dictionary = products[index]
		var panel_node := row.get_child(index) as Panel
		if panel_node == null or panel_node.name != "Product_" + str(product.get("productId", "")): return false
		if panel_node.get_meta("kind", "") != product.get("kind", "") or panel_node.get_meta("payload", "") != str(product.get("payload", "")): return false
	var consumables: Dictionary = host.inventory.get("consumables", {})
	var paid_bags: int = int(consumables.get("advancedBagCount", 0)) + int(consumables.get("topBagCount", 0))
	var gold: int = int(Game.lobby.get("wallet", {}).get("gold", 0))
	for index in products.size():
		var product: Dictionary = products[index]
		var panel_node := row.get_child(index) as Panel
		var detail := panel_node.get_node_or_null("ShopDetail") as Label
		var buy := panel_node.get_node_or_null("Purchase") as Button
		if detail == null or buy == null: return false
		var parsed: Variant = product.get("payload", {})
		var payload: Dictionary = parsed if parsed is Dictionary else {}
		var amount: int = int(payload.get("amount", payload.get("count", 0)))
		if changed_product_id.is_empty() or str(product.get("productId", "")) == changed_product_id:
			var quantity_line := (P.localized("shop_quantity_line") % amount) + "\n" if amount > 0 else ""
			detail.text = quantity_line + (P.localized("shop_purchase_count") % [product.get("purchased", 0), product.get("limit", 0)]) + "\n" + (P.localized("shop_price") % product.get("priceGold", 0))
		var is_bag: bool = product.get("kind", "") in ["AdvancedBag", "TopBag"]
		var stock_full: bool = is_bag and paid_bags + maxi(1, amount) > 3
		var stock_unknown: bool = is_bag and not host._shop_inventory_ready
		var already_owned: bool = product.get("kind", "") == "Cards" and payload.has("cardId") and bool(product.get("alreadyOwned", false))
		buy.text = P.localized("refresh_inventory") if stock_unknown else (P.localized("inventory_full") if stock_full else (P.localized("activated") if already_owned else P.localized("buy")))
		buy.disabled = Game.busy or stock_unknown or stock_full or already_owned or int(product.get("purchased", 0)) >= int(product.get("limit", 0)) or int(product.get("priceGold", 0)) > gold
	var wallet_label := get_node_or_null("WalletGold") as Label
	if wallet_label != null: wallet_label.text = "%s %s" % [P.localized_text("金币"), gold]
	var stock_label := get_node_or_null("ShopStockSummary") as Label
	if stock_label != null:
		var stock_key := "shop_stock_summary" if host._shop_inventory_ready else "shop_stock_refresh"
		stock_label.text = P.localized(stock_key) % paid_bags if host._shop_inventory_ready else P.localized(stock_key)
	return true

func _shop_card_presentation(item_panel: Panel, image: TextureRect, payload: Dictionary) -> void:
	var card_id := str(payload.get("cardId", ""))
	var card_info: Dictionary = host.cards.get(card_id, {})
	var quality := str(card_info.get("quality", payload.get("quality", "White"))).capitalize()
	if quality not in ["White", "Green", "Blue", "Purple", "Orange", "Red"]: quality = "White"
	# Match the external CardView's 218x376 frame and 190x285 art window,
	# scaled to fit the shop product column without distorting the border.
	var scale_factor := 206.0 / 218.0
	image.position = Vector2(17, 110) + Vector2(14, 14) * scale_factor
	image.size = Vector2(190, 285) * scale_factor
	var frame := Art.image(item_panel, Art.texture("UI/Codex/qframe_%s.png" % quality.to_lower()), Vector2.ZERO)
	frame.name = "ProductCardFrame"
	frame.position = Vector2(17, 110)
	frame.size = Vector2(206, 376 * scale_factor)
	frame.stretch_mode = TextureRect.STRETCH_SCALE
	if frame.texture == null: frame.texture = Art.texture("UI/Codex/qframe_common.png")
	# Shop cards have their own scaled layout. Keep the shop-only title offset
	# independent from CardView so codex/deck cards retain their original position.
	var card_name := _shop_card_face_label(item_panel, CardDetails.localized_name(card_id, card_info), Rect2(40, 352, 160, 31), 18, P.GOLD)
	card_name.name = "ShopCardName"
	card_name.add_theme_font_override("font", P.font("title"))
	var effect: String = host.card_description(card_id, "face")
	if effect.is_empty():
		var tooltip_parts: PackedStringArray = host._card_text(card_id).split("\n\n", true, 1)
		effect = tooltip_parts[1] if tooltip_parts.size() > 1 else ""
	var effect_label := _shop_card_face_label(item_panel, effect, Rect2(40, 385, 160, 50), 13, P.PAPER, 2)
	effect_label.name = "ShopCardEffect"
	var tooltip: String = host._card_text(card_id)
	item_panel.tooltip_text = P.localized_text(tooltip + "\n品质：%s色" % P.word(quality))

func _shop_card_face_label(item_panel: Panel, value: String, rect: Rect2, font_size: int, color: Color, max_lines: int = 1) -> Label:
	var label := Label.new()
	var display_text := P.localized_text(value)
	label.text = display_text
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY if max_lines > 1 else TextServer.AUTOWRAP_OFF
	label.max_lines_visible = max_lines
	label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	label.clip_text = true
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var typeface := P.font_for_text(display_text, font_size)
	label.add_theme_font_override("font", typeface)
	var line_height := rect.size.y / float(max_lines)
	var fit_width := -1.0 if max_lines > 1 else rect.size.x - 8.0
	label.add_theme_font_size_override("font_size", P.fit_font_size(typeface, font_size, line_height, fit_width, display_text))
	label.add_theme_color_override("font_color", color)
	item_panel.add_child(label)
	label.position = rect.position
	label.size = rect.size
	return label

func _product_title(kind: String, payload: Dictionary) -> String:
	if kind == "Cards":
		if payload.has("cardId"):
			var card_id := str(payload.cardId)
			return CardDetails.localized_name(card_id, host.cards.get(card_id, {}))
		return P.localized("word_card_pack")
	if kind == "ClassSoul" and payload.get("heroClass", "") in P.CLASSES:
		return P.localized("word_%s_soul" % str(payload.heroClass).to_lower())
	return P.product_name(kind)

func _product_art(kind: String, payload: Dictionary) -> Texture2D:
	if kind == "Cards" and payload.has("cardId"):
		var illustration := Art.card(str(payload.cardId))
		if illustration != null: return illustration
	var dedicated := Art.product(kind)
	if dedicated != null: return dedicated
	if kind == "ClassSoul":
		var hero_class: String = payload.get("heroClass", "")
		return _item(hero_class + "Soul") if hero_class in P.CLASSES else null
	return _item(kind)

func _market() -> void:
	panel(Rect2(28, 135, 1300, 884))
	panel(Rect2(1344, 135, 546, 884))
	text("购买 / 我的挂单", Rect2(76, 164, 770, 57), 34, P.GOLD)
	text("物品                                     金币             操作", Rect2(76, 238, 1140, 50), 24, P.MUTED)
	var scroll := _scroll(Rect2(68, 316, 1210, 635))
	var list := VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(list)
	for listing in host.listings:
		var row := HBoxContainer.new()
		list.add_child(row)
		var gear: Dictionary = listing.get("equipment", {}) if listing.get("equipment") is Dictionary else {}
		var name: Button = host._button(row, host._equipment_name(gear) if not gear.is_empty() else "装备详情暂不可用", func(): host._show_equipment_details(gear), gear.is_empty())
		name.tooltip_text = host.EquipmentDetails.description(gear) if not gear.is_empty() else ""
		name.custom_minimum_size.x = 660
		host._label(row, "%s" % listing.priceGold, 30, P.GOLD).custom_minimum_size.x = 240
		if listing.sellerId == Game.lobby.get("player", {}).get("userId", ""):
			host._button(row, "下架", func(): host._mutate("/market/listings/" + listing.listingId, HTTPClient.METHOD_DELETE), Game.busy)
		else:
			host._button(row, "购买", func(): host._confirm("花费 %s 金币购买 %s？" % [listing.priceGold, host._equipment_name(gear)], func(): host._mutate("/market/" + listing.listingId + "/purchase?expectedVersion=" + str(int(listing.version)), HTTPClient.METHOD_POST)), Game.busy or gear.is_empty() or int(listing.priceGold) > int(Game.lobby.get("wallet", {}).get("gold", 0)))
	if list.get_child_count() == 0: text("集市暂时没有挂单", Rect2(356, 453, 730, 100), 32, P.MUTED)
	text("本次上架", Rect2(1390, 175, 440, 67), 34, P.GOLD)
	var choices := OptionButton.new()
	choices.add_item(P.localized("select_stored_equipment"))
	var items: Array = []
	for item in host.inventory.get("equipments", []):
		if item.get("isBound", false) or item.get("location") != "Inventory": continue
		items.append(item)
		choices.add_item(host._equipment_name(item))
		if item.instanceId == host._market_item: choices.selected = items.size()
	if not items.any(func(item): return item.instanceId == host._market_item): host._market_item = ""
	choices.item_selected.connect(func(index): host._market_item = items[index - 1].instanceId if index > 0 else ""; host._render())
	add_child(choices)
	choices.position = Vector2(1385, 320)
	choices.size = Vector2(460, 66)
	text("上架单价", Rect2(1390, 449, 440, 50), 27)
	var price := SpinBox.new()
	price.min_value = 1
	price.max_value = 100000000
	price.value = host._market_price
	price.value_changed.connect(func(value): host._market_price = int(value))
	add_child(price)
	price.position = Vector2(1385, 515)
	price.size = Vector2(460, 72)
	text("手续费 10%（至少 1 金币）\n上架上限 8 件 · 最长 48 小时", Rect2(1390, 643, 455, 121), 25, P.MUTED)
	button("上架物品", Rect2(1400, 868, 435, 88), func():
		var selected_id: String = host._market_item
		var price_gold: int = host._market_price
		host._confirm("确认以 %s 金币上架？" % price_gold, func(): host._mutate("/market/listings", HTTPClient.METHOD_POST, {"equipmentId": selected_id, "priceGold": price_gold})), Game.busy or host._market_item.is_empty(), ORANGE)

func _ready_prompt() -> void:
	panel(Rect2(520, 245, 880, 600))
	text("旅人集结", Rect2(725, 312, 600, 90), 54, P.GOLD)
	text("已确认 %s / %s" % [Game.ready_prompt.get("ready_players", 0), Game.ready_prompt.get("required_players", 1)], Rect2(720, 455, 600, 80), 36)
	var deadline: float = float(Game.ready_prompt.get("deadline_unix_ms", 0)) / 1000.0
	var remaining := text("", Rect2(720, 552, 600, 60), 28, P.TEAL)
	var update_time: Callable = func(): remaining.text = P.localized_text("确认剩余 %s 秒" % maxi(0, int(deadline - Time.get_unix_time_from_system())))
	update_time.call()
	var timer := Timer.new()
	timer.wait_time = 0.25
	timer.timeout.connect(update_time)
	add_child(timer)
	timer.start()
	button("准备就绪", Rect2(690, 668, 540, 100), func(): Game.gateway.send("room.ready"), not Game.gateway.online, ORANGE)
