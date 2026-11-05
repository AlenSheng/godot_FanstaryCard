extends RefCounted

const P = preload("res://ui/palette.gd")
const Model = preload("res://ui/season_journey_reward_model.gd")
const Journey = preload("res://ui/season_journey_model.gd")
const Dates = preload("res://ui/season_activity_model.gd")
const CosmeticArt = preload("res://ui/season_cosmetic_art.gd")

static func _source_label(host: Control, source: String) -> String:
	for season in host.journey_controller.seasons:
		if season.get("seasonId") == source:
			return Journey.season_label(season)
	return P.localized("journey_rewards_title")

static func _title(row: Dictionary) -> String:
	if row.get("kind") == "Cosmetic":
		return P.localized("journey_cosmetic_" + str(row.get("cosmeticId", "")).replace("-", "_") + "_name")
	return P.localized({"EquipmentFragments": "journey_reward_fragments", "WarriorSoul": "journey_reward_warrior", "ClassSoul": "journey_reward_class", "CardPack": "journey_reward_pack"}.get(str(row.get("kind", "")), "journey_unavailable"))

static func _origin_label(host: Control, season_id: String) -> String:
	var label := season_id
	for season in host.journey_controller.seasons:
		if season.get("seasonId") == season_id:
			label = Journey.season_label(season)
			break
	return Journey.display_text(P.localized("journey_origin_season") % label)

static func _collected_label(timestamp: String) -> String:
	var date := Dates.date_label(timestamp)
	if str(P.languages()[P.language()].get("direction", "ltr")) == "rtl":
		# Keep the complete ISO date and time together in an RTL sentence.
		date = String.chr(0x2066) + date + String.chr(0x2069)
	return P.localized("journey_collected") + " · " + date

static func _list(ui: Control, rect: Rect2, name: String) -> Dictionary:
	var scroll: ScrollContainer = ui._scroll(rect)
	scroll.name = name
	var list := VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list.add_theme_constant_override("separation", 14)
	scroll.add_child(list)
	return {"scroll": scroll, "list": list}

static func _row(parent: VBoxContainer, name: String) -> HBoxContainer:
	var panel := PanelContainer.new()
	panel.name = name
	panel.custom_minimum_size.y = 172
	var style := P.box(Color("17343b"), Color("8c6943"), 1)
	for side in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]:
		style.set_content_margin(side, 18)
	panel.add_theme_stylebox_override("panel", style)
	parent.add_child(panel)
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 20)
	panel.add_child(line)
	return line

static func _lines(parent: HBoxContainer) -> VBoxContainer:
	var lines := VBoxContainer.new()
	lines.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lines.add_theme_constant_override("separation", 8)
	parent.add_child(lines)
	return lines

static func _menu() -> OptionButton:
	var picker := OptionButton.new()
	picker.add_theme_font_override("font", P.font("ui"))
	picker.add_theme_font_size_override("font_size", 26)
	picker.add_theme_stylebox_override("normal", P.box(Color("17343b"), P.GOLD, 1))
	var popup := picker.get_popup()
	var menu_theme := Theme.new()
	menu_theme.set_stylebox("panel", "PopupMenu", P.box(Color("142b31"), P.GOLD, 2))
	menu_theme.set_stylebox("hover", "PopupMenu", P.box(Color("28515a"), P.GOLD, 1))
	menu_theme.set_font("font", "PopupMenu", P.font("ui"))
	menu_theme.set_font_size("font_size", "PopupMenu", 26)
	menu_theme.set_color("font_color", "PopupMenu", P.PAPER)
	popup.theme = menu_theme
	P.apply_text_direction(picker)
	return picker

static func build_rewards(ui: Control, host: Control) -> void:
	var c = host.journey_reward_controller
	c.attach(host)
	ui.panel(Rect2(28, 130, 1862, 892)).name = "JourneyRewardsPanel"
	ui.text(_source_label(host, c.source), Rect2(76, 154, 920, 64), 30, P.GOLD).name = "JourneyRewardSource"
	var picker := _menu()
	picker.name = "JourneyRewardClass"
	picker.add_item(P.localized("journey_choose_class"))
	for hero in Model.HEROES:
		picker.add_item(P.localized("class_" + str(hero).to_lower()))
	picker.select(0 if c.hero.is_empty() else Model.HEROES.find(c.hero) + 1)
	picker.disabled = Game.busy or c.loading or c.writing
	picker.item_selected.connect(c.choose_hero)
	ui.add_child(picker)
	picker.position = Vector2(1040, 154)
	picker.size = Vector2(320, 64)
	ui.button(P.localized("sync"), Rect2(1400, 154, 190, 64), c.reload, Game.busy or c.loading or c.writing).name = "JourneyRewardRefresh"
	ui.button(P.localized("journey_cosmetics_title"), Rect2(1620, 154, 212, 64), c.open_cosmetics, Game.busy or c.writing).name = "JourneyCosmeticsEntry"
	ui.text(P.localized("journey_reward_hint"), Rect2(76, 238, 1756, 64), 26, P.PAPER).name = "JourneyRewardHint"
	if not c.notice.is_empty() and c.rewards.get("state") != "Unavailable":
		ui.text(c.notice, Rect2(76, 308, 1756, 50), 25, P.TEAL).name = "JourneyRewardNotice"
	var state: Dictionary = c.rewards
	if c.loading or c.failed or state.is_empty() or state.get("state") in ["None", "Disabled"]:
		ui.text(P.localized("loading" if c.loading else "journey_unavailable" if c.failed or state.is_empty() else "journey_disabled" if state.get("state") == "Disabled" else "journey_none"), Rect2(200, 420, 1520, 160), 32, P.GOLD).name = "JourneyRewardState"
		return
	if state.get("state") == "Unavailable":
		ui.text(P.localized("journey_unavailable"), Rect2(76, 308, 1756, 50), 25, P.GOLD).name = "JourneyRewardUnavailable"
	var nodes := _list(ui, Rect2(76, 374, 1756, 620), "JourneyRewardScroll")
	for row in state.get("rewards", []):
		var line := _row(nodes.list, "JourneyRewardLevel" + str(row.level))
		var lines := _lines(line)
		host._label(lines, Journey.display_text(P.localized("journey_reward_level") % row.level), 27, P.GOLD)
		host._label(lines, Journey.display_text(P.localized("journey_reward_amount") % [_title(row), row.amount]), 28, P.PAPER)
		var status: String = P.localized({"Locked": "journey_reward_locked", "Pending": "journey_reward_pending", "Claimed": "journey_reward_claimed", "Unavailable": "journey_unavailable"}.get(str(row.state), "journey_unavailable"))
		host._label(lines, status, 24, P.TEAL if row.state == "Claimed" else P.MUTED)
		var blocked: bool = Game.busy or c.loading or c.writing or c.failed or state.get("state") not in ["Active", "Ended"] or Model.claim_body(row, c.hero).is_empty()
		var claim: Button = host._button(line, P.localized("journey_claim_button"), c.confirm_claim.bind(row), blocked)
		claim.name = "ClaimJourneyLevel" + str(row.level)
		claim.custom_minimum_size = Vector2(240, 72)
		claim.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	nodes.scroll.set_deferred("scroll_vertical", c.reward_scroll)
	nodes.scroll.get_v_scroll_bar().value_changed.connect(c.save_reward_scroll)

static func build_cosmetics(ui: Control, host: Control) -> void:
	var c = host.journey_reward_controller
	c.attach(host)
	ui.panel(Rect2(28, 130, 1862, 892)).name = "CosmeticsPanel"
	ui.button(P.localized("journey_title"), Rect2(76, 154, 500, 64), host._navigate.bind("journey"), Game.busy or c.writing).name = "CosmeticsJourneyBack"
	ui.text(P.localized("journey_cosmetic_bound"), Rect2(620, 154, 850, 64), 25, P.PAPER).name = "CosmeticsBoundHint"
	ui.button(P.localized("sync"), Rect2(1560, 154, 272, 64), c.reload, Game.busy or c.loading or c.writing).name = "CosmeticsRefresh"
	if not c.notice.is_empty():
		ui.text(c.notice, Rect2(76, 232, 1756, 44), 24, P.TEAL).name = "CosmeticNotice"
	var inventory: Dictionary = c.inventory()
	if c.loading or c.failed or inventory.is_empty():
		ui.text(P.localized("loading" if c.loading else "journey_unavailable"), Rect2(200, 430, 1520, 160), 32, P.GOLD).name = "CosmeticState"
		return
	ui.panel(Rect2(76, 290, 550, 704)).name = "CurrentCosmeticProfile"
	ui.text(P.localized("journey_current_style"), Rect2(106, 310, 490, 54), 28, P.GOLD).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	CosmeticArt.portrait(ui, Rect2(231, 380, 240, 240), Game.hero_class, CosmeticArt.equipped("AvatarFrame"), "Profile")
	var player_name: Label = ui.text(str(Game.lobby.get("player", {}).get("displayName", "")), Rect2(106, 634, 490, 54), 28, P.PAPER, null, true, false)
	player_name.name = "CosmeticPlayerName"
	player_name.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var equipped_title: Label = ui.text(CosmeticArt.title(), Rect2(106, 695, 490, 80), 27, P.TEAL, null, true, false)
	equipped_title.name = "EquippedProfileTitle"
	equipped_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var back := CosmeticArt.texture(CosmeticArt.equipped("CardBack"))
	if back != null:
		ui.picture(back, Rect2(291, 788, 120, 180)).name = "EquippedProfileCardBack"
	else:
		ui.text(P.localized("journey_default_style"), Rect2(126, 824, 450, 70), 25, P.MUTED).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var nodes := _list(ui, Rect2(680, 290, 1152, 704), "CosmeticOwnedScroll")
	if inventory.owned.is_empty():
		host._label(nodes.list, P.localized("journey_cosmetics_empty"), 30, P.MUTED)
	for row in inventory.owned:
		var line := _row(nodes.list, "OwnedCosmetic_" + str(row.cosmeticId))
		line.custom_minimum_size.y = 194
		var image := CosmeticArt.texture(str(row.cosmeticId))
		if image != null:
			var picture := TextureRect.new()
			picture.texture = image
			picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			picture.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			picture.custom_minimum_size = Vector2(108, 150)
			line.add_child(picture)
		var lines := _lines(line)
		host._label(lines, P.localized(str(row.nameKey)), 28, P.GOLD)
		host._label(lines, P.localized(str(row.descriptionKey)), 24, P.PAPER)
		if row.kind == "Collection":
			host._label(lines, _collected_label(str(row.acquiredAt)), 23, P.TEAL)
		else:
			var equipped: bool = CosmeticArt.equipped(str(row.kind)) == row.cosmeticId
			var select: Button = host._button(line, P.localized("journey_unequip" if equipped else "journey_equip"), c.select_cosmetic.bind(str(row.kind), null if equipped else row.cosmeticId), Game.busy or c.loading or c.writing or c.failed)
			select.name = "SelectCosmetic_" + str(row.cosmeticId)
			select.custom_minimum_size = Vector2(200, 72)
			select.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		host._label(lines, _origin_label(host, str(row.sourceSeasonId)), 23, P.MUTED).name = "CosmeticOrigin_" + str(row.cosmeticId)
	nodes.scroll.set_deferred("scroll_vertical", c.cosmetic_scroll)
	nodes.scroll.get_v_scroll_bar().value_changed.connect(c.save_cosmetic_scroll)
