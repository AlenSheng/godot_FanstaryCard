extends RefCounted

const P=preload("res://ui/palette.gd")
const Details=preload("res://ui/equipment_details.gd")
const Model=preload("res://ui/season_crafting_model.gd")
const BLUE="UI/CardCodex/card_codex_action_button_blue.png"
const ORANGE="UI/CardCodex/card_codex_action_button_orange.png"

static func build(ui: Control,host: Control) -> void:
	var state: Dictionary=host._crafting_state
	ui.panel(Rect2(50,135,1820,200))
	if state.get("loading",false):
		ui.text(P.localized("loading"),Rect2(100,190,1600,70),32,P.GOLD)
		return
	if state.get("unavailable",false) or state.get("notJoined",false) or state.get("error",false) or state.is_empty():
		var key: String="season_craft_error" if state.get("error",false) else "season_craft_join" if state.get("notJoined",false) else "season_craft_unavailable"
		ui.text(P.localized(key),Rect2(100,168,1660,92),28,P.PAPER,null,false)
		ui.button(P.localized("back"),Rect2(660,390,600,76),host._navigate.bind("prep" if state.get("notJoined",false) else "gear"))
		if state.get("error",false):ui.button(P.localized("season_craft_refresh"),Rect2(660,490,600,76),host._reload_crafting)
		return
	var wallet: Dictionary=state.get("wallet",{})
	ui.text(P.localized("season_craft_wallet") % [wallet.get("blueprintMarks",0),wallet.get("orangeBlueprintMarks",0)],Rect2(90,155,1730,52),32,P.GOLD,null,false)
	ui.text(P.localized("season_craft_income_hint"),Rect2(90,213,1730,110),23,P.MUTED,null,false)
	ui.button(P.localized("season_craft_tab_make"),Rect2(60,343,510,62),func():host._crafting_tab="craft";host._schedule_render(),false,ORANGE if host._crafting_tab=="craft" else BLUE)
	ui.button(P.localized("season_craft_tab_recipes"),Rect2(585,343,510,62),func():host._crafting_tab="recipes";host._schedule_render(),false,ORANGE if host._crafting_tab=="recipes" else BLUE)
	ui.button(P.localized("season_craft_refresh"),Rect2(1450,343,410,62),host._reload_crafting,Game.busy)
	if host._crafting_tab=="craft":_craft(ui,host,state)
	else:_recipes(ui,host,state)

static func _craft(ui: Control,host: Control,state: Dictionary) -> void:
	ui.panel(Rect2(50,414,860,598));ui.panel(Rect2(940,414,930,598))
	_picker(ui,host,"season_craft_quality","quality",["Purple","Orange"],440)
	_picker(ui,host,"season_craft_slot","slot",["Head","Chest","Hands","Legs","Feet"],540)
	_picker(ui,host,"season_craft_element","element",["Fire","Wood","Earth","Metal","Water"],640)
	_picker(ui,host,"season_craft_effect","wishedEffect",["Piercing","Bulwark","Vitality"],740)
	ui.text(P.localized("season_craft_no_red"),Rect2(90,824,770,120),24,P.MUTED,null,false)
	var selected: Dictionary=host._crafting_selection
	var offer: Dictionary={}
	for row in state.get("offers",[]):
		if row.get("quality")==selected.quality:offer=row
	var payment: Dictionary=Model.payment(offer,state.get("wallet",{}))
	var failures: int=Model.wish_progress(state,selected)
	var until: int=maxi(1,int(offer.get("wishAttempts",3))-failures)
	var title: String="%s · %s · %s" % [P.word(selected.quality),P.word(selected.element),P.word(selected.slot)]
	ui.text(title,Rect2(990,440,815,96),34,P.GOLD,null,false)
	ui.text(P.localized("season_craft_cost") % [payment.blueprints,payment.orangeBlueprints],Rect2(990,550,815,90),28,P.PAPER,null,false)
	ui.text(P.localized("season_craft_wish_progress") % [P.word(selected.wishedEffect),failures,until],Rect2(990,654,815,146),26,P.TEAL,null,false)
	var unlocked: bool=int(state.get("maximumDifficulty",0))>=int(offer.get("minimumDifficulty",6))
	if not unlocked:ui.text(P.localized("season_craft_tier_locked") % offer.get("minimumDifficulty",1),Rect2(990,805,815,70),24,P.MUTED,null,false)
	elif not payment.canAfford:ui.text(P.localized("season_craft_insufficient"),Rect2(990,805,815,70),24,P.MUTED,null,false)
	ui.button(P.localized("season_craft_make"),Rect2(1110,916,590,70),host._confirm_craft,Game.busy or not unlocked or not payment.canAfford,ORANGE)

static func _picker(ui: Control,host: Control,label: String,field: String,values: Array,y: float) -> void:
	ui.text(P.localized(label),Rect2(95,y,275,70),28,P.GOLD,null,false)
	var picker := OptionButton.new()
	picker.name="CraftingSelect_"+field
	picker.theme=P.theme()
	picker.add_theme_font_override("font",P.font("ui"))
	picker.add_theme_font_size_override("font_size",28)
	for value in values:picker.add_item(P.word(value))
	picker.select(maxi(0,values.find(host._crafting_selection.get(field))))
	picker.disabled=Game.busy
	ui.add_child(picker);picker.position=Vector2(390,y);picker.size=Vector2(470,68)
	picker.item_selected.connect(func(index):host._craft_choose(field,str(values[index])))
	P.apply_text_direction(picker)

static func _recipes(ui: Control,host: Control,state: Dictionary) -> void:
	for x in [50,660,1270]:ui.panel(Rect2(x,414,590,598))
	ui.text(P.localized("season_craft_samples"),Rect2(90,442,510,55),30,P.GOLD)
	ui.text(P.localized("season_craft_templates"),Rect2(700,442,510,55),30,P.GOLD)
	ui.text(P.localized("season_craft_bodies"),Rect2(1310,442,510,55),30,P.GOLD)
	var samples := _column(ui,Rect2(88,510,510,460))
	var season_id: String=str(state.get("season",{}).get("seasonId",""))
	for item in host.inventory.get("equipments",[]):
		if item.get("seasonId")!=season_id or item.get("quality") not in ["Purple","Orange"]:continue
		var eligible: bool=Model.learnable(item,season_id)
		_list_button(samples,Details.title(item)+"\n"+P.localized(Model.sample_status(item)),host._confirm_learn.bind(item),Game.busy or not eligible)
	if samples.get_child_count()==0:_label(samples,P.localized("season_craft_samples_empty"))
	var recipes := _column(ui,Rect2(698,510,510,460))
	var selected: Dictionary={}
	for recipe in state.get("recipes",[]):
		if str(recipe.recipeId)==host._craft_recipe:selected=recipe
		var label: String=Details.title(recipe)+"\n"+P.localized("season_craft_level_zero")
		_list_button(recipes,label,host._craft_select_recipe.bind(str(recipe.recipeId)),Game.busy,str(recipe.recipeId)==host._craft_recipe)
	if recipes.get_child_count()==0:_label(recipes,P.localized("season_craft_recipes_empty"))
	var bodies := _column(ui,Rect2(1308,510,510,164))
	if selected.is_empty():_label(bodies,P.localized("season_craft_choose_recipe"))
	else:
		for item in host.inventory.get("equipments",[]):
			if Model.rebuild_body(item,selected):_list_button(bodies,Details.title(item),host._craft_select_body.bind(item),Game.busy,str(item.get("instanceId",""))==host._craft_body)
		if bodies.get_child_count()==0:_label(bodies,P.localized("season_craft_bodies_empty"))
	var quote: Dictionary=host._craft_quote
	var preview := _column(ui,Rect2(1308,690,510,178))
	preview.get_parent().name="CraftingPreviewScroll"
	if quote.get("loading",false):_label(preview,P.localized("loading"))
	elif quote.get("error",false):_label(preview,P.localized("season_craft_error"))
	elif quote.get("before") is Dictionary:
		_label(preview,P.localized("season_craft_before_after") % [Details.title(quote.before),Details.title(quote.after)])
		_label(preview,P.localized("season_craft_rebuild_cost") % [quote.get("fragmentCost",0),quote.get("availableFragments",0)])
		_label(preview,P.localized("season_craft_reset_warning"))
		if not quote.get("canReforge",false):_label(preview,P.localized("season_craft_rebuild_blocked"))
	else:_label(preview,P.localized("season_craft_choose_body"))
	if quote.get("before") is Dictionary:
		ui.button(preload("res://ui/numerical_details.gd").text("title"),Rect2(1320,880,486,46),func():preload("res://ui/numerical_details.gd").show_compare(host,[quote.before],quote.after))
	ui.button(P.localized("season_craft_rebuild"),Rect2(1320,940,486,62),host._confirm_reforge,Game.busy or not quote.get("canReforge",false),ORANGE)

static func _column(ui: Control,rect: Rect2) -> VBoxContainer:
	var scroll: ScrollContainer=ui._scroll(rect)
	var column := VBoxContainer.new()
	column.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation",12)
	scroll.add_child(column)
	return column

static func _label(parent: Control,value: String) -> void:
	var label := Label.new()
	label.text=value;label.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	label.add_theme_font_override("font",P.font_for_text(value,24))
	label.add_theme_font_size_override("font_size",24)
	label.add_theme_color_override("font_color",P.PAPER)
	parent.add_child(label);P.apply_text_direction(label)

static func _list_button(parent: Control,value: String,action: Callable,disabled: bool,selected: bool=false) -> void:
	var button := Button.new()
	button.disabled=disabled;button.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	button.custom_minimum_size.y=92
	button.pressed.connect(action)
	preload("res://ui/art.gd").button(button,ORANGE if selected else BLUE)
	parent.add_child(button)
	var label := Label.new()
	label.text=value;label.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
	label.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER;label.vertical_alignment=VERTICAL_ALIGNMENT_CENTER
	label.mouse_filter=Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_override("font",P.font_for_text(value,24))
	label.add_theme_font_size_override("font_size",24)
	label.add_theme_color_override("font_color",P.MUTED if disabled else P.PAPER)
	button.add_child(label);P.apply_text_direction(label)
	var fit := func():
		label.position=Vector2(20,10);label.size=Vector2(maxf(1,button.size.x-40),maxf(1,button.size.y-20))
		button.custom_minimum_size.y=maxf(92,label.get_line_count()*label.get_theme_font("font").get_height(24)+20)
	button.resized.connect(fit);fit.call_deferred()
