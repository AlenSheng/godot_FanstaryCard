extends RefCounted

const P=preload("res://ui/palette.gd")
const Model=preload("res://ui/season_activity_model.gd")
const Controller=preload("res://ui/season_activity_controller.gd")
const BLUE="UI/CardCodex/card_codex_action_button_blue.png"

static func build(ui: Control,host: Control) -> void:
	var c: Controller=host.activity_controller
	c.attach(host)
	ui.panel(Rect2(28,130,1862,892)).name="ActivityPanel"
	ui.text(P.localized("activity_rules"),Rect2(72,152,1480,76),26,P.PAPER).name="ActivityRules"
	ui.button(P.localized("sync"),Rect2(1580,158,252,62),c.reload.bind(false),Game.busy or c.loading).name="ActivityRefresh"
	ui.button(P.localized("journey_short"),Rect2(1240,246,272,66),host._navigate.bind("journey"),Game.busy).name="ActivityJourney"
	if c.events.is_empty():
		ui.text(P.localized("loading" if c.loading else "activity_unavailable" if c.failed else "activity_empty"),Rect2(210,380,1500,180),34,P.GOLD)
		return
	var picker := OptionButton.new()
	picker.name="ActivitySelector";picker.clip_text=true;picker.text_overrun_behavior=TextServer.OVERRUN_TRIM_ELLIPSIS
	picker.add_theme_font_override("font",P.font("ui"));picker.add_theme_font_size_override("font_size",28)
	for index in c.events.size():
		picker.add_item(Model.event_title(c.events[index]))
		if Model.key(c.events[index])==c.selected: picker.select(index)
	picker.disabled=Game.busy or c.loading;picker.item_selected.connect(c.choose);ui.add_child(picker);picker.position=Vector2(76,246);picker.size=Vector2(1130,66);P.apply_text_direction(picker)
	if c.next_offset!=null: ui.button(P.localized("activity_more_history"),Rect2(1560,246,272,66),c.reload.bind(true),Game.busy or c.loading)
	var event := c.current()
	if event.is_empty(): return
	var state: String=str(event.get("state","Unavailable"))
	var state_key: String={"Active":"activity_active","Upcoming":"activity_upcoming","Ended":"activity_ended"}.get(state,"activity_unavailable")
	ui.text(P.localized(state_key)+" · "+Model.window_label(event),Rect2(76,328,1756,60),26,P.MUTED).name="ActivityWindow"
	ui.text(P.localized("activity_budget") % [event.available,event.earned,event.spent,event.tokenCap],Rect2(76,394,1756,60),30,P.GOLD).name="ActivityBudget"
	ui.text(P.localized("activity_exchange"),Rect2(76,464,800,48),30,P.GOLD)
	ui.text(P.localized("activity_rewards"),Rect2(1028,464,804,48),30,P.GOLD)
	var class_picker := OptionButton.new()
	class_picker.name="ActivityClass";class_picker.add_theme_font_override("font",P.font("ui"));class_picker.add_theme_font_size_override("font_size",24)
	for hero in ["Mage","Priest","Guardian"]: class_picker.add_item(P.localized("class_"+hero.to_lower()))
	class_picker.select(["Mage","Priest","Guardian"].find(c.hero));class_picker.disabled=Game.busy or c.loading
	class_picker.item_selected.connect(c.choose_hero);ui.add_child(class_picker);class_picker.position=Vector2(76,522);class_picker.size=Vector2(260,58);P.apply_text_direction(class_picker)
	ui.text(P.localized("activity_class_choice"),Rect2(354,522,610,58),23,P.MUTED)
	for index in mini(4,event.get("options",[]).size()):
		var option: Dictionary=event.options[index]
		var y := 600+index*76
		var label := Model.reward_title(option.merged({"heroClass":c.hero}))+" · "+P.localized("activity_cost") % [option.get("costTokens",0),option.get("used",0),option.get("eventLimit",0)]
		ui.text(label,Rect2(76,y,650,66),25,P.PAPER).name="ActivityOption"+str(index)
		ui.button(P.localized("activity_redeem"),Rect2(754,y,206,62),c.confirm_exchange.bind(option),Game.busy or c.loading or c.failed or Model.exchange_body(event,option,c.hero).is_empty(),BLUE).name="ActivityExchange"+str(index)
	var rewards: Array=event.get("rewards",[])
	if rewards.is_empty(): ui.text(P.localized("activity_no_rewards"),Rect2(1028,540,804,180),26,P.MUTED)
	for index in mini(4,rewards.size()):
		var reward: Dictionary=rewards[index]
		var y := 526+index*94
		ui.text(Model.reward_title(reward),Rect2(1028,y,540,62),25,P.PAPER).name="ActivityReward"+str(index)
		ui.button(P.localized("claim" if reward.get("state")=="Pending" else "activity_claimed"),Rect2(1600,y,232,62),c.confirm_claim.bind(reward),Game.busy or c.loading or c.failed or not reward.get("canClaim",false) or reward.get("state")!="Pending",BLUE).name="ActivityClaim"+str(index)
	ui.text(P.localized("activity_source_hint"),Rect2(1028,910,804,78),23,P.MUTED).name="ActivitySourceHint"
	ui.text(P.localized("loading") if c.loading else c.notice,Rect2(76,940,884,64),24,P.TEAL).name="ActivityNotice"
