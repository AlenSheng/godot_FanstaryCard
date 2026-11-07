extends RefCounted

const P=preload("res://ui/palette.gd")
const Details=preload("res://ui/equipment_details.gd")
const Visual=preload("res://ui/item_visual.gd")

static func build(ui: Control,host: Control,player: Dictionary) -> void:
	ui.panel(Rect2(218,141,1484,818)).name="RedRewardPanel"
	_label(ui,P.localized("season_red_title"),Rect2(310,180,1300,70),42,P.GOLD)
	var pending: Variant=player.get("pending_red_item")
	if not pending is Dictionary or pending.is_empty():
		_label(ui,P.localized("season_red_wait"),Rect2(400,400,1120,200),32,P.PAPER)
		return
	var item: Dictionary=pending
	var context := str(Game.room.get("room_id",""))+":"+str(item.get("item_id",""))
	if host.get_meta("red_reward_context","")!=context:
		host.set_meta("red_reward_context",context)
		host.set_meta("red_reward_stage","")
		host.set_meta("red_reward_replacement","")
	var selected := str(host.get_meta("red_reward_replacement",""))
	var previous: Dictionary={}
	for candidate in player.get("inventory",[]):
		if str(candidate.get("item_id",""))==selected: previous=candidate
	var stage := str(host.get_meta("red_reward_stage",""))
	if stage=="confirm" and not previous.is_empty():
		_card(ui,previous,Rect2(315,290,610,325))
		_card(ui,item,Rect2(995,290,610,325))
		_label(ui,P.localized("season_red_confirm"),Rect2(350,650,1220,125),28,P.PAPER)
		ui.button(P.localized("back"),Rect2(400,815,480,72),func(): _stage(host,"replace")).name="RedReplaceBack"
		ui.button(P.localized("confirm"),Rect2(1040,815,480,72),func(): _claim(item,selected),not Game.allowed("reward.choice.claim")).name="RedReplaceConfirm"
	elif stage=="replace":
		_label(ui,P.localized("season_red_select"),Rect2(335,275,1250,90),30,P.PAPER)
		var scroll: ScrollContainer=ui._scroll(Rect2(335,390,1250,365))
		scroll.name="RedReplacementScroll"
		var rows := VBoxContainer.new()
		rows.size_flags_horizontal=Control.SIZE_EXPAND_FILL
		rows.add_theme_constant_override("separation",12)
		scroll.add_child(rows)
		for candidate in player.get("inventory",[]):
			var row := Button.new()
			row.name="RedReplacement_"+str(candidate.get("slot_index",rows.get_child_count()))
			row.custom_minimum_size=Vector2(1180,78)
			row.text=Details.title(candidate)+(" · "+P.localized("safe_slot_suffix") if bool(candidate.get("is_safe",false)) else "")
			preload("res://ui/art.gd").button(row,"UI/CardCodex/card_codex_action_button_blue.png")
			row.clip_text=true
			row.pressed.connect(func(): host.set_meta("red_reward_replacement",str(candidate.item_id));_stage(host,"confirm"))
			rows.add_child(row)
			P.fit_control_font(row,row.get_theme_font("font"),26,60.0)
		ui.button(P.localized("back"),Rect2(700,815,520,72),func(): _stage(host,"")).name="RedPickerBack"
	else:
		_card(ui,item,Rect2(390,295,1140,325))
		_label(ui,P.localized("season_red_hold"),Rect2(350,650,1220,125),28,P.PAPER)
		ui.button(P.localized("season_red_replace"),Rect2(650,815,620,72),func(): _stage(host,"replace"),not Game.allowed("reward.choice.claim")).name="RedOpenReplacement"

static func _label(ui: Control,value: String,rect: Rect2,size: int,color: Color) -> void:
	var label: Label=ui.text(value,rect,size,color)
	label.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment=VERTICAL_ALIGNMENT_CENTER

static func _card(ui: Control,item: Dictionary,rect: Rect2) -> void:
	var icon := Visual.item(ui,item,Vector2(144,144),false)
	icon.position=rect.position+Vector2(18,24)
	icon.size=Vector2(144,144)
	_label(ui,Details.title(item),Rect2(rect.position+Vector2(180,10),Vector2(rect.size.x-198,60)),30,P.GOLD)
	var scroll: ScrollContainer=ui._scroll(Rect2(rect.position+Vector2(180,85),Vector2(rect.size.x-198,225)))
	scroll.name="RedDescriptionScroll_"+str(item.get("item_id","preview"))
	var column := VBoxContainer.new()
	column.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	column.custom_minimum_size.x=rect.size.x-226
	scroll.add_child(column)
	var lines := Details.description(item).split("\n")
	if lines.size()>1: lines.remove_at(0)
	var label := Label.new()
	label.name="RedDescription"
	label.text="\n".join(lines)
	label.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	label.mouse_filter=Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_override("font",P.font_for_text(label.text,24))
	label.add_theme_font_size_override("font_size",24)
	label.add_theme_color_override("font_color",P.TEAL)
	column.add_child(label)
	P.apply_text_direction(label)

static func _stage(host: Control,value: String) -> void:
	host.set_meta("red_reward_stage",value)
	host._schedule_render()

static func _claim(item: Dictionary,replacement: String) -> void:
	var player: Dictionary=Game.room.get("player",{})
	var pending: Variant=player.get("pending_red_item")
	if not pending is Dictionary or pending.get("item_id")!=item.get("item_id"): return
	for candidate in player.get("inventory",[]):
		if candidate.get("item_id")==replacement:
			Game.command("reward.choice.claim",{"option_id":"red:"+str(item.item_id),"replace_item_id":replacement})
			return
