extends "res://tests/pr13_target_preview_input.gd"

const Proto = preload("res://network/protobuf.gd")
var case_verdicts := {}
var sounds: Array = []

class CodecGateway extends "res://network/gateway.gd":
	var sent: Array = []
	func new_id() -> String: return "b10-render-" + str(sent.size())
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		var codec := Proto.new()
		var message: String = COMMANDS.get(kind, "")
		var raw: PackedByteArray = codec.encode(message, payload) if not message.is_empty() else PackedByteArray()
		sent.append({"kind":kind,"payload":payload.duplicate(true),"request_id":request_id,"wire":raw,"codec_error":codec.error})
		return codec.error.is_empty()

func reset_cards(ids: Array, hero: String = "Mage", hp: int = 70, shield: int = 0) -> void:
	reset_battle()
	Game.selected_cards = []
	Game.room.room_revision = 10
	Game.room.player.hero_class = hero
	Game.room.player.combat = {"hp":hp,"maximum_hp":100 if hero=="Guardian" else 70,"shield":shield}
	Game.room.player.hand = []
	for id in ids: Game.room.player.hand.append({"instance_id":id,"card_id":id,"level":0})
	Game.gateway.sent = []
	sounds = []

func preview_texts() -> Array:
	var panel: Control = $UI._reference.get_node_or_null("CombatPreview")
	var values: Array = []
	if panel != null:
		for label in panel.find_children("*","Label",true,false):
			if label.is_visible_in_tree() and label.get_visible_line_count()>0: values.append(label.text)
	return values

func click_named(name: String) -> bool:
	var button: Button = $UI._reference.get_node_or_null(name)
	if button==null: return false
	var point: Vector2 = button.get_global_transform_with_canvas() * (button.size*.5)
	await click_viewport(point)
	return true

func record(id: String, passed: bool, actual: Dictionary, language: String, resolution: Vector2i) -> void:
	await present()
	var image := get_viewport().get_texture().get_image()
	var sizes_ok: bool = get_window().size==resolution and image.get_size()==resolution
	var filename := ""
	var image_ok := true
	if language=="en" and resolution.x==960:
		filename = id + ".png"
		image_ok = image.save_png(output+"/"+filename)==OK
	passed = passed and sizes_ok and image_ok
	if not case_verdicts.has(id): case_verdicts[id]=true
	case_verdicts[id] = case_verdicts[id] and passed
	observations.append({"case_id":id,"language":language,"resolution":[resolution.x,resolution.y],"actual":actual,"screenshot":filename,"actual_pixel_size":[image.get_width(),image.get_height()],"passed":passed})

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	Game.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := CodecGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	Game.sound_requested.connect(func(cue): sounds.append(cue))
	var original_language: String = P.language()
	get_window().mode = Window.MODE_WINDOWED
	for language in ["zh-CN","en"]:
		P.set_language(language)
		for resolution in [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]:
			get_window().size = resolution
			reset_cards(["C09","C06"])
			await present()
			await click_named("Card_C09")
			await click_named("Card_C06")
			await present()
			var initial_core: String = Game.combat_preview.get("core_element","")
			await click_named("Card_C09")
			await click_named("Card_C09")
			await present()
			var order: Array = Game.selected_cards.duplicate()
			var order0: Label = $UI._reference.get_node_or_null("PlayOrder_0")
			var order1: Label = $UI._reference.get_node_or_null("PlayOrder_1")
			var numbering: bool = order0!=null and order1!=null and order0.text=="2" and order1.text=="1"
			var core: String = Game.combat_preview.get("core_element","")
			var visible_core: bool = preview_texts().any(func(text):return text.contains(P.word("Water")))
			await click_named("PlayCardsButton")
			var plays: Array = gateway.sent.filter(func(row):return row.kind=="battle.play_cards")
			var codec := Proto.new()
			var decoded: Dictionary = codec.decode("BattlePlayCardsCommand",plays[0].wire) if plays.size()==1 else {}
			await record("PR13-B10.1-T01",initial_core=="Earth" and core=="Water" and visible_core and numbering and order==["C06","C09"] and decoded.get("card_instance_ids",[])==order and codec.error.is_empty(),{"initial_core":initial_core,"reselected_order":order,"visible_core":core,"numbering_matches":numbering,"decoded_protocol_order":decoded.get("card_instance_ids",[]),"actual_play_commands":plays.size()},language,resolution)

			reset_cards(["C11"])
			await present(); await click_named("Card_C11"); await present()
			Game._preview_request.due = 0
			Game._flush_combat_preview()
			var previews: Array = gateway.sent.filter(func(row):return row.kind=="combat.preview")
			var request_id: String = previews[0].request_id if previews.size()==1 else "missing"
			Game._on_event("combat.previewed",{"_request_id":request_id,"_room_revision":9,"battle_id":"battle","target_id":"fire-bat","card_instance_ids":["C11"],"damage":99,"hp_damage":99})
			await present()
			var texts: Array = preview_texts()
			var estimate_visible: bool = texts.any(func(text):return text.contains(P.localized("battle_preview_estimate")))
			await record("PR13-B10.1-T02",previews.size()==1 and not Game.combat_preview.get("authoritative",false) and estimate_visible and not texts.any(func(text):return text.contains("99")),{"request_revision":10,"reply_revision":9,"authority_accepted":Game.combat_preview.get("authoritative",false),"estimate_visible":estimate_visible,"visible_preview_labels":texts},language,resolution)

			reset_cards(["C09","C06"])
			Game.toggle_card("C09"); Game.toggle_card("C06")
			Game._on_connection_changed("recovering")
			gateway.online = false; gateway.recovering = true
			await present()
			var recovery: Label = $UI._reference.get_node_or_null("CombatWaitReason")
			var recovery_visible: bool = recovery!=null and recovery.text==P.localized("battle_wait_recovering")
			var snapshot: Dictionary = Game.room.duplicate(true)
			snapshot.room_revision = 11
			snapshot.player.hand = [{"instance_id":"C06","card_id":"C06","level":0}]
			gateway.online = true; gateway.recovering = false
			Game._on_event("room.snapshot",snapshot)
			Game._on_connection_changed("已连接")
			await present()
			var current_selection: Array = Game.selected_cards.duplicate()
			var current_card: Button = $UI._reference.get_node_or_null("Card_C06")
			await record("PR13-B10.1-T03",recovery_visible and current_selection.all(func(id):return id=="C06") and current_card!=null and $UI._reference.get_node_or_null("Card_C09")==null,{"recovery_visible":recovery_visible,"selection_after_authority_snapshot":current_selection,"hand_after_snapshot":["C06"],"stale_card_absent":$UI._reference.get_node_or_null("Card_C09")==null},language,resolution)

			reset_cards(["C15"])
			Game.toggle_card("C15")
			await present()
			var heal: Dictionary = Game.combat_preview.duplicate(true)
			var panel: Control = $UI._reference.get_node_or_null("CombatPreview")
			var heal_text := "%s +0" % P.localized("battle_preview_heal")
			var heal_visible: bool = preview_texts().has(heal_text)
			var overflow_text: String = P.localized("battle_preview_overflow") % [int(heal.get("heal_overflow",0)),0]
			await record("PR13-B10.2-T01",int(heal.get("heal",-1))==0 and int(heal.get("heal_overflow",0))>0 and heal_visible and panel!=null and panel.tooltip_text.contains(overflow_text),{"effective_heal":heal.get("heal"),"heal_overflow":heal.get("heal_overflow"),"visible_zero_effect_label":heal_visible,"overflow_in_tooltip":panel!=null and panel.tooltip_text.contains(overflow_text)},language,resolution)

			reset_cards(["GUA-06"],"Guardian",100,49)
			Game.toggle_card("GUA-06")
			await present()
			var shield: Dictionary = Game.combat_preview.duplicate(true)
			panel = $UI._reference.get_node_or_null("CombatPreview")
			var effective_visible: bool = preview_texts().has("%s +1" % P.localized("battle_preview_shield"))
			var parts: String = P.localized("battle_preview_shield_parts") % [int(shield.get("shield_gain",0))+int(shield.get("shield_overflow",0)),int(shield.get("shield_gain",0)),int(shield.get("shield_overflow",0))]
			await record("PR13-B10.2-T02",int(shield.get("shield_gain",0))==1 and int(shield.get("shield_overflow",0))>0 and effective_visible and panel!=null and panel.tooltip_text.contains(parts) and Game.room.player.combat.shield==49,{"effective_shield":shield.get("shield_gain"),"shield_overflow":shield.get("shield_overflow"),"theory_effective_overflow_explained":panel!=null and panel.tooltip_text.contains(parts),"preview_did_not_mutate_shield":Game.room.player.combat.shield==49},language,resolution)

			var missing: Array = []
			for key in ["battle_preview_estimate","battle_preview_heal","battle_preview_shield","battle_preview_overflow","battle_preview_applied_estimate","battle_wait_confirming","battle_wait_recovering"]:
				if P.localized(key).is_empty() or P.localized(key)==key: missing.append(key)
			await record("PR13-B10.2-T03",missing.is_empty() and P.language()==language and P.languages().size()==2,{"requested_language":language,"actual_language":P.language(),"configured_locales":P.languages().keys(),"missing_keys":missing,"visible_preview_labels":preview_texts()},language,resolution)

			reset_cards(["C11"])
			await present(); await click_named("Card_C11"); await present()
			await click_named("PlayCardsButton")
			await click_named("PlayCardsButton")
			plays = gateway.sent.filter(func(row):return row.kind=="battle.play_cards")
			await record("PR13-B10.3-T01",plays.size()==1 and Game.has_pending_commands(),{"actual_gui_clicks_attempted":2,"actual_play_commands":plays.size(),"pending":Game.has_pending_commands()},language,resolution)
			var unchanged: bool = Game.room.player.combat.hp==70 and Game.room.pve.monsters[0].hp==20 and Game.room.player.hand.size()==1
			var wait_label: Label = $UI._reference.get_node_or_null("CombatWaitReason")
			await record("PR13-B10.3-T02",unchanged and not sounds.has("card_play") and wait_label!=null and wait_label.text==P.localized("battle_wait_confirming"),{"authority_hp_and_hand_unchanged":unchanged,"success_sound_before_ack":sounds.has("card_play"),"visible_submitted_state":wait_label!=null and wait_label.text==P.localized("battle_wait_confirming")},language,resolution)
			Game._on_connection_changed("recovering"); gateway.online=false; gateway.recovering=true
			await present()
			for i in range(20):Game.play_cards()
			await click_named("PlayCardsButton")
			plays = gateway.sent.filter(func(row):return row.kind=="battle.play_cards")
			wait_label = $UI._reference.get_node_or_null("CombatWaitReason")
			await record("PR13-B10.3-T03",plays.size()==1 and Game._queued_command.size()<=1 and wait_label!=null and wait_label.text==P.localized("battle_wait_recovering"),{"repeated_attempts":20,"actual_play_commands":plays.size(),"queued_contexts":0 if Game._queued_command.is_empty() else 1,"visible_recovering_state":wait_label!=null and wait_label.text==P.localized("battle_wait_recovering")},language,resolution)
	P.set_language(original_language)
	Game.gateway = old_gateway
	gateway.free()
	var cases: Array = []
	for id in case_verdicts:
		cases.append({"case_id":id,"executed":true,"status":"Passed" if case_verdicts[id] else "Failed","profiles_executed":["OFFLINE","RENDER"],"actual":{"matrix_rows":6,"all_rows_passed":case_verdicts[id]},"scope":"Current native rendered project scenes and real store/codec with controlled gateway, normal GUI input and declared authority events; no server LIVE/human claim"})
	var driver := DisplayServer.get_name()
	var result := {"ok":cases.size()==9 and observations.size()==54 and not case_verdicts.values().has(false) and driver!="headless","cases":cases,"observations":observations,"display_driver":driver,"adapter":RenderingServer.get_video_adapter_name()}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	print(JSON.stringify({"ok":result.ok,"cases":cases.size(),"rows":observations.size(),"passed_cases":case_verdicts.values().count(true)}))
	get_tree().quit(0 if result.ok else 1)
