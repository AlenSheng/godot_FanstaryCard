extends RefCounted

const P=preload("res://ui/palette.gd")
const Model=preload("res://ui/season_journey_model.gd")
const Dates=preload("res://ui/season_activity_model.gd")
const Controller=preload("res://ui/season_journey_controller.gd")

static func build(ui: Control,host: Control) -> void:
	var c: Controller=host.journey_controller
	c.attach(host)
	host.journey_reward_controller.attach(host)
	ui.panel(Rect2(28,130,1862,892)).name="JourneyPanel"
	ui.button(P.localized("sync"),Rect2(1240,154,272,64),c.reload.bind(false),Game.busy or c.loading).name="JourneyRefresh"
	ui.button(P.localized("journey_rewards_title"),Rect2(1560,154,272,64),host.journey_reward_controller.open_rewards.bind(str(c.state.get("seasonId",""))),Game.busy or c.loading or str(c.state.get("seasonId","")).is_empty()).name="JourneyRewardEntry"
	if not c.seasons.is_empty():
		var picker := OptionButton.new();picker.name="JourneySeason"
		picker.clip_text=true;picker.text_overrun_behavior=TextServer.OVERRUN_TRIM_ELLIPSIS
		picker.add_theme_font_override("font",P.font("ui"));picker.add_theme_font_size_override("font_size",28)
		for index in c.seasons.size():
			picker.add_item(Model.season_label(c.seasons[index]))
			if c.seasons[index].get("seasonId")==c.state.get("seasonId"): picker.select(index)
		picker.disabled=Game.busy or c.loading;picker.item_selected.connect(c.choose)
		ui.add_child(picker);picker.position=Vector2(76,154);picker.size=Vector2(1130,64);P.apply_text_direction(picker)
	else: ui.text(P.localized("journey_title"),Rect2(76,154,1130,64),34,P.GOLD)
	var state: Dictionary=c.state
	if state.is_empty() or c.failed or not Model.available(state):
		var key: String="loading" if c.loading else "journey_unavailable" if c.failed else Model.state_key(str(state.get("state","None")))
		ui.text(P.localized(key),Rect2(200,390,1520,170),32,P.GOLD).name="JourneyState"
		if int(state.get("experience",0))>0: ui.text(Model.display_text(P.localized("journey_recorded") % state.experience),Rect2(200,580,1520,100),28,P.PAPER)
		return
	ui.text(P.localized(Model.state_key(str(state.state)))+" · "+Dates.window_label(state),Rect2(76,236,1756,46),26,P.MUTED).name="JourneyWindow"
	ui.text(Model.display_text(P.localized("journey_summary") % [state.level,state.experience,state.maximumExperience]),Rect2(76,292,1060,58),32,P.GOLD).name="JourneySummary"
	var next_text: String=P.localized("journey_maximum") if int(state.level)==30 else P.localized("journey_next") % [state.experienceIntoLevel,state.experienceToNext]
	ui.text(Model.display_text(next_text),Rect2(1160,292,672,58),26,P.TEAL).name="JourneyNext"
	var bar := ProgressBar.new();bar.name="JourneyProgress";bar.show_percentage=false;bar.min_value=0;bar.max_value=maxi(1,int(state.maximumExperience));bar.value=int(state.experience)
	bar.add_theme_stylebox_override("background",P.box(P.INK,P.MUTED,1));bar.add_theme_stylebox_override("fill",P.box(P.TEAL,P.TEAL,1))
	ui.add_child(bar);bar.position=Vector2(76,360);bar.size=Vector2(1756,24);bar.mouse_filter=Control.MOUSE_FILTER_IGNORE
	var catch_up: String=P.localized("journey_catchup") % state.referenceExperience if state.get("catchUpActive",false) else P.localized("journey_no_catchup")
	ui.text(Model.display_text(P.localized("journey_sources")),Rect2(76,396,1756,44),24,P.PAPER).name="JourneySources"
	ui.text(Model.display_text(catch_up),Rect2(76,444,1756,44),24,P.TEAL).name="JourneyCatchUp"
	ui.text(P.localized("journey_levels"),Rect2(76,510,884,44),28,P.GOLD)
	ui.text(P.localized("journey_contracts"),Rect2(1016,510,816,44),28,P.GOLD)
	var level_scroll: ScrollContainer=ui._scroll(Rect2(76,574,884,358));level_scroll.name="JourneyLevelsScroll"
	var level_list := _list(level_scroll)
	for row in state.levels:
		var lines := _row(level_list,"JourneyLevel"+str(row.level))
		host._label(lines,Model.display_text(P.localized("journey_level") % [row.level,P.localized("journey_main" if row.stage=="Main" else "journey_collection")]),26,P.TEAL if row.reached else P.GOLD)
		host._label(lines,Model.display_text(P.localized("journey_level_cost") % [row.requiredExperience,row.cumulativeExperience]),23,P.PAPER)
		if row.reached: host._label(lines,P.localized("journey_completed"),22,P.TEAL)
	if c.level_scroll<0: _focus_level.bind(level_scroll,level_list,int(state.level),c).call_deferred()
	else: level_scroll.set_deferred("scroll_vertical",c.level_scroll)
	level_scroll.get_v_scroll_bar().value_changed.connect(c.save_level_scroll)
	var contract_scroll: ScrollContainer=ui._scroll(Rect2(1016,574,816,358));contract_scroll.name="JourneyContractsScroll"
	var contract_list := _list(contract_scroll)
	if state.contracts.is_empty(): host._label(contract_list,P.localized("journey_no_contracts"),26,P.MUTED)
	for row in state.contracts:
		var lines := _row(contract_list,"JourneyContract"+str(row.week)+"_"+str(row.contractId))
		host._label(lines,Model.display_text(P.localized("journey_contract_title") % [row.week,Model.contract_title(str(row.completionKind))]),25,P.GOLD)
		host._label(lines,Model.display_text(P.localized("journey_contract_progress") % [row.progress,row.target,row.experienceReward]),23,P.PAPER)
		var status: String=P.localized("journey_contract_done") % row.experienceCredited if row.state=="Completed" else P.localized("journey_expired" if row.state=="Expired" else "journey_open")
		host._label(lines,Model.display_text(status),22,P.TEAL if row.state=="Completed" else P.MUTED)
	contract_scroll.set_deferred("scroll_vertical",c.contract_scroll);contract_scroll.get_v_scroll_bar().value_changed.connect(c.save_contract_scroll)
	ui.text(P.localized("journey_stages"),Rect2(76,946,1130,64),24,P.MUTED).name="JourneyStages"
	if c.next_offset!=null: ui.button(P.localized("activity_more_history"),Rect2(1240,946,592,62),c.reload.bind(true),Game.busy or c.loading).name="JourneyMoreHistory"

static func _list(scroll: ScrollContainer) -> VBoxContainer:
	var list := VBoxContainer.new();list.size_flags_horizontal=Control.SIZE_EXPAND_FILL;list.add_theme_constant_override("separation",12)
	scroll.add_child(list);return list

static func _focus_level(scroll: ScrollContainer,list: VBoxContainer,level: int,c: Controller) -> void:
	if not is_instance_valid(scroll) or not is_instance_valid(list) or list.get_child_count()==0: return
	var tree := scroll.get_tree()
	# Font fitting and container sorting settle on successive frames. Measuring
	# before those passes can land several levels below the requested row.
	await tree.process_frame
	await tree.process_frame
	if not is_instance_valid(scroll) or not is_instance_valid(list) or c.level_scroll>=0: return
	var index := clampi(level-1,0,list.get_child_count()-1)
	scroll.scroll_vertical=int((list.get_child(index) as Control).position.y)

static func _row(parent: VBoxContainer,name: String) -> VBoxContainer:
	var panel := PanelContainer.new();panel.name=name;panel.mouse_filter=Control.MOUSE_FILTER_IGNORE
	var style := P.box(Color("17343b"),Color("47626a"),1)
	for side in [SIDE_LEFT,SIDE_TOP,SIDE_RIGHT,SIDE_BOTTOM]: style.set_content_margin(side,14)
	panel.add_theme_stylebox_override("panel",style);parent.add_child(panel)
	var lines := VBoxContainer.new();lines.add_theme_constant_override("separation",6);lines.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	panel.add_child(lines);return lines
