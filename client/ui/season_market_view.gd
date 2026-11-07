extends RefCounted

const P=preload("res://ui/palette.gd")
const Art=preload("res://ui/art.gd")
const Model=preload("res://ui/season_market_model.gd")
const Controller=preload("res://ui/season_market_controller.gd")
const Details=preload("res://ui/equipment_details.gd")
const Samples=preload("res://ui/season_crafting_model.gd")
const Visual=preload("res://ui/item_visual.gd")
const BLUE="UI/CardCodex/card_codex_action_button_blue.png"
const ORANGE="UI/CardCodex/card_codex_action_button_orange.png"

static func build(ui: Control,host: Control) -> void:
	var controller: Controller=host.market_controller
	controller.attach(host)
	ui.panel(Rect2(28,135,1862,884)).name="SeasonMarketPanel"
	var state: Dictionary=controller.state
	if state.is_empty() or state.get("error",false) or state.get("stale",false):
		var key: String="season_market_error" if state.get("error",false) else "season_market_stale" if state.get("stale",false) else "loading"
		ui.text(P.localized(key),Rect2(110,340,1700,150),32,P.PAPER)
		ui.button(P.localized("sync"),Rect2(660,580,600,76),controller.reload,controller.loading)
		return
	var policy: Dictionary=state.get("policy",{})
	var wallet: Dictionary=policy.get("wallet",{})
	ui.text(Model.money(int(wallet.get("gold",0)),"Gold"),Rect2(76,155,800,58),30,P.GOLD).name="MarketGoldBalance"
	ui.text(Model.money(int(wallet.get("diamond",0)),"Diamond"),Rect2(920,155,900,58),30,P.TEAL).name="MarketDiamondBalance"
	var info: String=P.localized("season_market_terms") % [state.get("ownListings",[]).size(),policy.get("sharedSlots",8),policy.get("listingHours",48),int(int(policy.get("taxBasisPoints",1000))/100.0)]
	ui.text(info,Rect2(76,218,1740,58),24,P.MUTED)
	var tabs: Array=[["browse","season_market_browse"],["own","season_market_own"],["sell","season_market_sell"],["returns","season_market_returns"]]
	for index in tabs.size():
		var label: String=P.localized(str(tabs[index][1]))
		if tabs[index][0]=="returns":label=label % state.get("returns",[]).size()
		ui.button(label,Rect2(72+index*373,290,355,62),controller.choose_tab.bind(str(tabs[index][0])),Game.busy,ORANGE if controller.tab==tabs[index][0] else BLUE).name="MarketTab_"+str(tabs[index][0])
	ui.button(P.localized("sync"),Rect2(1564,290,274,62),controller.reload,Game.busy or controller.loading).name="MarketRefresh"
	if controller.tab=="sell":_sell(ui,host,controller,policy)
	elif controller.tab=="returns":_returns(ui,host,controller,policy)
	else:
		if controller.tab=="browse":_filters(ui,controller,policy)
		else:ui.text(P.localized("season_market_relist_hint"),Rect2(76,370,1740,66),24,P.PAPER)
		_listings(ui,host,controller,policy)
	var notice: String=controller.notice
	if controller.loading:notice=P.localized("loading")
	elif not policy.get("canTrade",false) and notice.is_empty():notice=P.localized("season_market_closed")
	ui.text(notice,Rect2(76,964,1740,44),24,P.MUTED).name="MarketNotice"

static func _picker(ui: Control,rect: Rect2,values: Array,current: String,callback: Callable,labels: Array=[]) -> void:
	var picker := OptionButton.new()
	picker.clip_text=true;picker.text_overrun_behavior=TextServer.OVERRUN_TRIM_ELLIPSIS
	picker.add_theme_font_override("font",P.font("ui"));picker.add_theme_font_size_override("font_size",26)
	for index in values.size():picker.add_item(P.localized(str(labels[index])) if index<labels.size() else P.localized("all") if str(values[index]).is_empty() else P.word(str(values[index])))
	picker.select(maxi(0,values.find(current)));picker.disabled=Game.busy
	picker.item_selected.connect(func(index):callback.call(str(values[index])))
	ui.add_child(picker);picker.position=rect.position;picker.size=rect.size;P.apply_text_direction(picker)

static func _filters(ui: Control,controller: Controller,policy: Dictionary) -> void:
	var headings: Array=[[72,250,"season_market_currency"],[340,235,"season_craft_quality"],[592,235,"season_craft_slot"],[844,235,"season_craft_element"],[1096,235,"season_market_effect"],[1348,490,"season_market_sort"]]
	for heading in headings:ui.text(P.localized(str(heading[2])),Rect2(float(heading[0]),369,float(heading[1]),44),24,P.MUTED)
	var currencies: Array=[]
	for row in policy.get("currencies",[]):currencies.append(str(row.get("currency","")))
	if currencies.is_empty():currencies=["Gold"]
	_picker(ui,Rect2(72,420,250,62),currencies,str(controller.filters.currency),func(value):controller.choose_filter("currency",value))
	_picker(ui,Rect2(340,420,235,62),["","White","Green","Blue","Purple","Orange","Red"],str(controller.filters.quality),func(value):controller.choose_filter("quality",value))
	_picker(ui,Rect2(592,420,235,62),["","Head","Chest","Hands","Legs","Feet"],str(controller.filters.slot),func(value):controller.choose_filter("slot",value))
	_picker(ui,Rect2(844,420,235,62),["","Wood","Fire","Earth","Metal","Water"],str(controller.filters.element),func(value):controller.choose_filter("element",value))
	_picker(ui,Rect2(1096,420,235,62),["","Piercing","Bulwark","Vitality"],str(controller.filters.effect),func(value):controller.choose_filter("effect",value))
	_picker(ui,Rect2(1348,420,490,62),["recent","price","material"],str(controller.filters.sort),func(value):controller.choose_filter("sort",value),["season_market_recent","season_market_price_order","season_market_material_order"])

static func _column(ui: Control,rect: Rect2,name: String) -> VBoxContainer:
	var scroll: ScrollContainer=ui._scroll(rect);scroll.name=name
	var column := VBoxContainer.new();column.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation",14);scroll.add_child(column)
	return column

static func _source(item: Dictionary,policy: Dictionary) -> String:
	if item.get("seasonId")==null:return P.localized("season_market_legacy")
	return P.localized("season_market_current" if item.get("seasonId")==policy.get("seasonId") else "season_market_archived")

static func _caption_button(parent: Control,item: Dictionary,host: Control,rect: Rect2) -> void:
	var button := Button.new();button.name="MarketEquipmentDetails"
	button.position=rect.position;button.size=rect.size
	Art.button(button,BLUE);parent.add_child(button)
	button.pressed.connect(host._show_equipment_details.bind(item))
	var label := Label.new();label.mouse_filter=Control.MOUSE_FILTER_IGNORE;label.clip_text=true
	label.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART;label.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER;label.vertical_alignment=VERTICAL_ALIGNMENT_CENTER
	label.text=Details.title(item)+"\n"+P.localized(Samples.sample_status(item))
	label.add_theme_font_override("font",P.font_for_text(label.text,24));label.add_theme_font_size_override("font_size",24)
	button.add_child(label);label.position=Vector2(18,8);label.size=rect.size-Vector2(36,16);P.apply_text_direction(label)

static func _row(parent: Control,item: Dictionary) -> Control:
	var row := Control.new();row.custom_minimum_size=Vector2(1700,190);parent.add_child(row)
	var visual := Visual.item(row,{"kind":"Equipment","equipment":item},Vector2(96,96),false)
	visual.position=Vector2(12,28);visual.size=Vector2(96,96)
	return row

static func _listings(ui: Control,host: Control,controller: Controller,policy: Dictionary) -> void:
	var list := _column(ui,Rect2(72,496 if controller.tab=="browse" else 450,1766,442 if controller.tab=="browse" else 488),"MarketListingsScroll")
	var entries: Array=controller.state.get("ownListings" if controller.tab=="own" else "listings",[])
	for listing in entries.slice(0,controller.displayed):
		var item: Dictionary=listing.get("equipment",{})
		var row := _row(list,item)
		_caption_button(row,item,host,Rect2(128,8,700,112))
		ui.text(_source(item,policy),Rect2(128,132,700,48),24,P.MUTED,row,false)
		ui.text(Model.money(Model.price(listing),Model.currency(listing)),Rect2(860,16,360,60),30,P.GOLD,row)
		var own: bool=listing.get("sellerId")==Game.lobby.get("player",{}).get("userId")
		if own:
			var net: int=int(listing.get("sellerNet",Model.price(listing)-Model.fee(policy,Model.price(listing))))
			ui.text(P.localized("season_market_net") % Model.money(net,Model.currency(listing)),Rect2(860,82,360,90),24,P.TEAL,row,false)
			ui.button(P.localized("season_market_cancel"),Rect2(1260,36,205,70),controller.confirm_cancel.bind(listing),Game.busy,BLUE,row)
			ui.button(P.localized("season_market_edit"),Rect2(1480,36,205,70),controller.edit_listing.bind(listing),Game.busy or not Model.live(listing,policy),BLUE,row)
		else:
			var balance: int=int(policy.get("wallet",{}).get("gold" if Model.currency(listing)=="Gold" else "diamond",0))
			ui.button(P.localized("buy"),Rect2(1290,42,390,70),controller.confirm_buy.bind(listing),Game.busy or controller.loading or balance<Model.price(listing) or not Model.live(listing,policy),ORANGE,row)
	if entries.is_empty():ui.text(P.localized("no_listings"),Rect2(460,610,1000,90),30,P.MUTED)
	elif controller.displayed<entries.size():_more(list,controller.show_more)

static func _more(parent: Control,callback: Callable) -> void:
	var button := Button.new();button.text=P.localized("season_market_more");button.custom_minimum_size.y=70
	Art.button(button,BLUE);parent.add_child(button);button.pressed.connect(callback)
	P.fit_control_font(button,P.font_for_text(button.text,26),26,48)

static func _sell(ui: Control,host: Control,controller: Controller,policy: Dictionary) -> void:
	var item := controller.selected()
	var editing: bool=not controller.relist_target.is_empty()
	ui.text(P.localized("season_market_edit" if editing else "select_stored_equipment"),Rect2(76,373,800,60),26,P.GOLD)
	if editing:ui.text(Details.title(item),Rect2(76,445,800,70),28,P.PAPER)
	else:
		var ids: Array=[""];var labels: Array=[P.localized("select_stored_equipment")]
		for candidate in controller.state.get("inventory",{}).get("equipments",[]):
			if Model.eligible(candidate,policy,controller.listing_currency):ids.append(str(candidate.get("instanceId","")));labels.append(Details.title(candidate))
		var picker := OptionButton.new();picker.name="MarketStoredEquipment"
		for label in labels:picker.add_item(str(label))
		picker.select(maxi(0,ids.find(controller.selected_item)));picker.disabled=Game.busy
		picker.add_theme_font_override("font",P.font("ui"));picker.add_theme_font_size_override("font_size",26);picker.clip_text=true
		picker.item_selected.connect(func(index):controller.select_item(str(ids[index])))
		ui.add_child(picker);picker.position=Vector2(76,445);picker.size=Vector2(800,70)
	for index in 2:
		var currency: String=["Gold","Diamond"][index]
		ui.button(P.word(currency),Rect2(76+index*410,535,390,64),controller.choose_currency.bind(currency),Game.busy or Model.offer(policy,currency).is_empty(),ORANGE if currency==controller.listing_currency else BLUE)
	var preview := _column(ui,Rect2(76,625,800,300),"MarketListingPreview")
	var description := Label.new();description.text=Details.description(item) if not item.is_empty() else P.localized("select_stored_equipment")
	description.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART;description.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	description.add_theme_font_override("font",P.font_for_text(description.text,24));description.add_theme_font_size_override("font_size",24)
	preview.add_child(description);P.apply_text_direction(description)
	ui.text(P.localized("listing_price"),Rect2(995,373,800,60),30,P.GOLD)
	var price := SpinBox.new();price.name="MarketPrice";price.min_value=1;price.max_value=maxi(1,controller.selected_cap());price.step=1;price.value=controller.listing_price
	price.get_line_edit().editable=not Game.busy;price.add_theme_font_size_override("font_size",32)
	price.value_changed.connect(func(value):controller.listing_price=int(value))
	ui.add_child(price);price.position=Vector2(995,455);price.size=Vector2(800,76)
	ui.text(P.localized("season_market_cap") % Model.money(controller.selected_cap(),controller.listing_currency),Rect2(995,550,800,70),26,P.PAPER)
	var fee: int=Model.fee(policy,controller.listing_price)
	ui.text(P.localized("season_market_fee") % Model.money(fee,controller.listing_currency),Rect2(995,635,800,70),28,P.MUTED)
	ui.text(P.localized("season_market_net") % Model.money(controller.listing_price-fee,controller.listing_currency),Rect2(995,710,800,70),28,P.TEAL)
	ui.text(_source(item,policy),Rect2(995,795,800,60),24,P.MUTED)
	var invalid: bool=item.is_empty() or not policy.get("canTrade",false) or controller.listing_price<1 or controller.listing_price>controller.selected_cap() or (not editing and controller.state.get("ownListings",[]).size()>=int(policy.get("sharedSlots",8)))
	ui.button(P.localized("list_item"),Rect2(1110,875,570,64),controller.confirm_list,Game.busy or controller.loading or invalid,ORANGE).name="MarketSubmitListing"

static func _returns(ui: Control,host: Control,controller: Controller,policy: Dictionary) -> void:
	ui.text(P.localized("season_market_holds_hint"),Rect2(76,373,1740,78),24,P.PAPER)
	var column := _column(ui,Rect2(72,470,1766,468),"MarketReturnsScroll")
	var rows: Array=controller.state.get("returns",[])
	for hold in rows.slice(0,controller.displayed):
		var item: Dictionary=hold.get("equipment",{})
		var row := _row(column,item);_caption_button(row,item,host,Rect2(128,8,700,112))
		ui.text(_source(item,policy),Rect2(128,132,700,48),24,P.MUTED,row,false)
		if not hold.get("canClaim",false):ui.text(P.localized("season_market_return_full"),Rect2(860,30,390,105),24,P.MUTED,row,false)
		ui.button(P.localized("claim"),Rect2(1290,42,390,70),controller.confirm_return.bind(hold),Game.busy or not hold.get("canClaim",false),ORANGE,row)
	if rows.is_empty():ui.text(P.localized("season_market_no_returns"),Rect2(460,610,1000,90),30,P.MUTED)
	elif controller.displayed<rows.size():_more(column,controller.show_more)
	elif controller.state.get("returnsNextOffset")!=null:_more(column,controller.more_returns)
