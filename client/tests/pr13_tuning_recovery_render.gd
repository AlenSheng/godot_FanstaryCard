extends "res://tests/pr13_element_marginal_render.gd"

@export var tuning_case := "PR13-B08.3-T01"
const TUNING_VECTORS := "res://tests/data/tuning_recovery_native.json"
const NATIVE_SOURCE := "014a601c9a72a8bd2aec357e56a349914f6613f4"
var tuning_checks := 0

func chosen(row: Dictionary) -> bool:
	var high := row.recipe in ["water-first","same-core-with-counter","ordinary-plus-conflict"]
	var vitality := high or row.recipe in ["direct-before-tuning","non-core-tuning"]
	return int(row.weapon_level) == (5 if high else 0) and row.equipment_profile == ("VitalitySet" if vitality else "Empty")

func project_before(row: Dictionary) -> void:
	reset_cards([], row.hero, int(row.input_room.player.combat.hp))
	Game.hero_class = row.hero
	Game.room = row.input_room.duplicate(true)
	var native: Dictionary = JSON.parse_string(row.before_state)
	assert(row.before_state.sha256_text() == row.before_state_sha256)
	Game.room.match_id = native.RoomId
	Game.room.config_version = native.ConfigVersion
	Game.room.player.phase = "Exploring"
	Game.room.player.library_count = native.Players[0].Combat.Deck.Library.size()
	Game.room.player.discard_count = native.Players[0].Combat.Deck.Discard.size()
	Game.selected_cards = []
	Game.clear_combat_preview()
	$UI._codex_card = ""
	await present()

func inspect_preview(row: Dictionary) -> Dictionary:
	var actual: Dictionary = Game.combat_preview
	var exact := actual.get("authoritative", false) == true
	for key in row.expected:
		if key == "core_element": exact = exact and actual.get(key, "") == row.expected[key]
		else: exact = exact and absf(float(actual.get(key, 0)) - float(row.expected[key])) < .000001
	var texts := preview_texts()
	var headline := "%s · %s" % [P.localized("battle_preview_confirmed"), P.localized("exploration_preview_core") % [P.word(row.expected.core_element), int(row.expected.core_count)]]
	var panel: Control = $UI._reference.get_node_or_null("CombatPreview")
	var displayed := texts.has(headline)
	if int(row.expected.heal) > 0: displayed = displayed and texts.has("%s +%s" % [P.localized("battle_preview_heal"), int(row.expected.heal)])
	var formula_visible := panel != null
	if float(row.expected.resonance_multiplier) > 1: formula_visible = formula_visible and panel.tooltip_text.contains(P.localized("exploration_preview_multiplier") % float(row.expected.resonance_multiplier))
	if int(row.expected.conflict_pair_count) > 0: formula_visible = formula_visible and panel.tooltip_text.contains(P.localized("exploration_preview_conflict") % [int(row.expected.conflict_pair_count), Details.percent(float(row.expected.conflict_cancellation))])
	return {"authoritative_values_exact":exact,"headline_visible":texts.has(headline),"effective_recovery_visible":displayed,"formula_preserved_in_tooltip":formula_visible,"visible_texts":texts,"passed":exact and displayed and formula_visible}

func render_witness(row: Dictionary) -> Dictionary:
	await project_before(row)
	var order_checks: Array = []
	for index in range(row.selected_cards.size()):
		var clicked := await click_named("Card_" + row.selected_cards[index])
		order_checks.append(clicked and Game.selected_cards == row.ids.slice(0,index+1))
	var codec := Proto.new()
	var envelope: Dictionary = codec.decode("ServerEnvelope", Marshalls.base64_to_raw(row.response_wire))
	var payload: Dictionary = codec.decode("BattleComboResolvedEvent", envelope.payload)
	Game._preview_request = {"request_id":envelope.request_id,"context":Game._preview_context(Game.selected_cards),"revision":int(envelope.room_revision)}
	Game._preview_deadline = Time.get_ticks_msec()+1000
	payload["_request_id"] = envelope.request_id
	payload["_room_revision"] = int(envelope.room_revision)
	Game._accept_combat_preview(payload)
	await present()
	var preview := inspect_preview(row)
	var battle_saved := true
	if row == last_battle_witness and P.language() == "en" and get_window().size.x == 960 and Engine.max_fps == 60:
		battle_saved = get_viewport().get_texture().get_image().save_png(output + "/" + tuning_case + "-battle.png") == OK
	var projected := {"hero":row.hero,"states":{row.before_state_sha256:row.before_state,row.after_state_sha256:row.after_state}}
	var after: Dictionary = await observe_marginal(projected,row.after_state_sha256,"actual-committed-boundary")
	tuning_checks += 1
	return {"hero":row.hero,"weapon_level":row.weapon_level,"equipment_profile":row.equipment_profile,"recipe":row.recipe,"selected_instance_order":Game.selected_cards,"actual_mouse_selection_checks":order_checks,"native_before_sha256":row.before_state_sha256,"native_after_sha256":row.after_state_sha256,"original_protocol_decoded":codec.error.is_empty(),"preview":preview,"after_commit_display":after,"passed":order_checks.all(func(value):return value) and codec.error.is_empty() and preview.passed and after.passed and battle_saved}

var last_battle_witness: Dictionary = {}

func scroll_details(scroll: ScrollContainer, label: Label) -> Dictionary:
	var samples: Array = []
	for step in range(12):
		var point := scroll.get_global_transform_with_canvas() * (scroll.size*.5)
		var motion := InputEventMouseMotion.new()
		motion.position = point
		motion.global_position = point
		get_viewport().push_input(motion, true)
		await get_tree().process_frame
		var clip := scroll.get_global_rect().intersection(get_viewport().get_visible_rect())
		var first: float = label.get_global_rect().position.y
		var height := float(label.get_line_height(0))*label.get_global_scale().y
		var visible_lines: Array = []
		for index in range(label.get_line_count()):
			var rect := Rect2(label.get_global_rect().position.x,first+height*index,label.get_global_rect().size.x,height)
			if clip.encloses(rect): visible_lines.append(index)
		samples.append({"scroll":scroll.scroll_vertical,"fully_visible_lines":visible_lines})
		var wheel := InputEventMouseButton.new()
		wheel.button_index = MOUSE_BUTTON_WHEEL_DOWN
		wheel.pressed = true
		wheel.position = point
		wheel.global_position = point
		get_viewport().push_input(wheel,true)
		await get_tree().process_frame
	var seen := {}
	for sample in samples:
		for index in sample.fully_visible_lines: seen[index] = true
	return {"actual_wheel_inputs":12,"samples":samples,"line_count":label.get_line_count(),"all_lines_reachable":seen.size()==label.get_line_count(),"last_line_reachable":seen.has(label.get_line_count()-1)}

func card_details_check(id: String) -> Dictionary:
	Game.room = {}
	Game.selected_cards = []
	Game.clear_combat_preview()
	Game.busy = false
	$UI.screen = "cards"
	$UI._codex_card = ""
	$UI._codex_ready = true
	$UI._search = id
	$UI._quality = ""
	$UI.owned = [{"cardId":id,"level":0,"copyCount":1,"unlocked":true,"version":1,"craftCost":1,"currencyKind":"WarriorSoul","canDismantle":false}]
	await present()
	var opened := await click_named("Card_"+id)
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var label: Label = $UI._reference.find_child("CardFullEffect",true,false) as Label
	var scroll: ScrollContainer = $UI._reference.find_child("CardEffectScroll",true,false) as ScrollContainer
	var tokens: Array = ["首张元素牌定核","计入同核共振","不增加向反牌数","不进入向反回复基数","相克牌仍可降低","不叠加牧师临渊或武器"] if P.language()=="zh-CN" else ["first elemental card sets the core","same-core resonance","adds no conflict count","conflict-heal base","counter cards can still lower","no Priest low-HP or weapon"]
	var full_text := label.text if label!=null else ""
	var semantics: bool = tokens.all(func(value):return full_text.contains(value))
	var accessibility := {"all_lines_reachable":false,"last_line_reachable":false}
	var readable := false
	if label != null and scroll != null:
		accessibility = await scroll_details(scroll,label)
		readable = label.get_theme_font_size("font_size") >= 18 and label.autowrap_mode==TextServer.AUTOWRAP_WORD_SMART and scroll.horizontal_scroll_mode==ScrollContainer.SCROLL_MODE_DISABLED and get_viewport().get_visible_rect().encloses(scroll.get_global_rect())
	var image_saved := true
	if P.language()=="en" and get_window().size.x==960 and Engine.max_fps==60:
		image_saved = get_viewport().get_texture().get_image().save_png(output+"/"+tuning_case+"-"+id+"-details.png")==OK
	var close: Button = $UI._reference.get_node_or_null("CardDetails/CloseCardDetails")
	var closed := false
	if close != null:
		await click_viewport(close.get_global_transform_with_canvas()*(close.size*.5))
		await get_tree().process_frame
		closed = $UI._codex_card.is_empty()
	return {"card_id":id,"opened_by_mouse":opened,"complete_semantics":semantics,"actual_full_text":full_text,"readable_wrapped_scroll_area":readable,"scrolling":accessibility,"closed_by_mouse":closed,"passed":opened and semantics and readable and accessibility.all_lines_reachable and accessibility.last_line_reachable and closed and image_saved}

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	var raw := FileAccess.get_file_as_string(TUNING_VECTORS)
	var data: Dictionary = JSON.parse_string(raw)
	assert(data.schema=="actual_tuning_recovery_render_v1" and data.source_sha==NATIVE_SOURCE and data.fixture_only and data.vectors.size()==96)
	var rows: Array = data.vectors.filter(func(row):return row.case_id==tuning_case and chosen(row))
	assert(rows.size()==(6 if tuning_case.ends_with("T03") else 9))
	last_battle_witness = rows.back()
	Game.set_process(false)
	$UI.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := CodecGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	var old_language := P.language()
	get_window().mode = Window.MODE_WINDOWED
	for language in ["zh-CN","en"]:
		P.set_language(language)
		for size in [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]:
			get_window().size = size
			for fps in [30,60,144]:
				Engine.max_fps = fps
				var witnesses: Array = []
				for row in rows: witnesses.append(await render_witness(row))
				var details: Array = []
				for id in ["ET-FIRE-G","ET-WATER-G"]: details.append(await card_details_check(id))
				await capture_case(tuning_case,witnesses.all(func(row):return row.passed) and details.all(func(row):return row.passed),{"actual_native_witnesses":witnesses,"actual_card_details":details,"original_native_source":NATIVE_SOURCE,"original_native_vectors_sha256":raw.sha256_text(),"controlled_boundary_only":true},language,size,fps)
	P.set_language(old_language)
	Game.gateway = old_gateway
	gateway.free()
	var result := {"ok":case_verdicts.get(tuning_case,false) and observations.size()==18 and DisplayServer.get_name()!="headless","observations":observations,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name(),"native_witness_renders":tuning_checks,"case_id":tuning_case,"scope":"Original native room/router witnesses and real mouse input; software GPU, no LIVE/hardware FPS/human claim."}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().create_timer(.25).timeout
	get_tree().quit(0 if result.ok else 1)
