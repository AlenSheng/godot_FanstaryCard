extends "res://tests/pr13_b10_render_cases.gd"

var failures: Array = []

func _ready() -> void:
	output = OS.get_environment("FANTASYCARD_ART_EVIDENCE")
	Game.gateway.set_process(false)
	Game.gateway.persist_session = false
	Game.gateway.online = true
	Game.connection = "Controlled original room witness"
	Game.lobby = {"player":{"userId":"preview-player"},"wallet":{"gold":1200},"decks":[],"materials":{},"equippedLoadouts":[],"classWeapons":[]}
	$UI.inventory = {"equipments":[],"consumables":{}}
	$UI._shop_inventory_ready = true
	$UI.gear_draft = [null,null,null,null,null]
	Callable(self,"_run").call_deferred()

func native_payload(row: Dictionary, request_id: String) -> Dictionary:
	var n: Dictionary = row.native_preview
	var result: Dictionary = {"_request_id":request_id,"_room_revision":row.snapshot.room_revision,"battle_id":n.BattleId,"target_id":n.TargetId,"card_instance_ids":row.selected_instance_ids,"core_element":"Fire"}
	var fields := {"Damage":"damage","ShieldDamage":"shield_damage","HpDamage":"hp_damage","Heal":"heal","ShieldGain":"shield_gain","CoreCount":"core_count","HealthCost":"health_cost","ImmediateDraw":"immediate_draw","ConflictPairCount":"conflict_pair_count"}
	for key in fields: result[fields[key]] = int(n[key])
	for pair in [["ResonanceMultiplier","resonance_multiplier"],["ConflictCancellation","conflict_cancellation"],["DrawCharge","draw_charge"],["StunSeconds","stun_seconds"],["DrawBlockSeconds","draw_block_seconds"]]: result[pair[1]] = str(n[pair[0]])
	result["damage_segments"] = []
	for segment in n.DamageSegments: result.damage_segments.append({"kind":segment.Kind,"amount":segment.Amount})
	return result

func same_contract(preview: Dictionary, native: Dictionary) -> bool:
	if preview.get("core_element","") != "Fire": return false
	for pair in [["damage","Damage"],["heal","Heal"],["shield_gain","ShieldGain"],["core_count","CoreCount"],["conflict_pair_count","ConflictPairCount"],["shield_damage","ShieldDamage"],["hp_damage","HpDamage"]]:
		if int(preview.get(pair[0],-1)) != int(native[pair[1]]): return false
	for pair in [["resonance_multiplier","ResonanceMultiplier"],["conflict_cancellation","ConflictCancellation"]]:
		if absf(float(preview.get(pair[0],-1))-float(native[pair[1]])) > 0.000000001: return false
	return true

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	Game.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := CodecGateway.new()
	gateway.persist_session = false
	gateway.online = true
	Game.gateway = gateway
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/b08_core_actual_witness_projection.json"))
	var level := int(OS.get_environment("PR13_B08_WEAPON_LEVEL"))
	var witnesses: Array = data.rows.filter(func(row):return int(row.weapon_level)==level)
	var original_language: String = P.language()
	get_window().mode = Window.MODE_WINDOWED
	for language in ["zh-CN","en"]:
		P.set_language(language)
		for resolution in [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]:
			get_window().size = resolution
			for cap in [30,60,144]:
				Engine.max_fps = cap
				for delay in [0,100,300]:
					for row in witnesses:
						Game.room = row.snapshot.duplicate(true)
						Game.hero_class = row.hero
						Game.selected_cards = []
						Game.clear_combat_preview()
						Game._pending_commands = {}
						Game._latest_commands = {}
						Game._pending_play = {}
						Game._queued_command = {}
						Game.busy = false
						gateway.sent = []
						await present()
						var clicks := true
						for id in row.selected_card_ids:
							clicks = await click_named("Card_"+str(id)) and clicks
						await present()
						var estimated: Dictionary = Game.combat_preview.duplicate(true)
						var estimate_ok := same_contract(estimated,row.native_preview)
						var order_ok: bool = Game.selected_cards == row.selected_instance_ids
						Game._preview_request.due = 0
						Game._flush_combat_preview()
						var requests: Array = gateway.sent.filter(func(r):return r.kind=="combat.preview")
						var request_id: String = requests[-1].request_id if not requests.is_empty() else "MISSING"
						if delay > 0: await get_tree().create_timer(float(delay)/1000.0).timeout
						Game._on_event("combat.previewed",native_payload(row,request_id))
						await present()
						var authority: Dictionary = Game.combat_preview.duplicate(true)
						var texts: Array = preview_texts()
						var core_visible: bool = texts.any(func(t):return t.contains(P.word("Fire")))
						var confirmation_visible: bool = texts.any(func(t):return t.contains(P.localized("battle_preview_confirmed")))
						var heal_visible: bool = int(row.native_preview.Heal)==0 or texts.has("%s +%d" % [P.localized("battle_preview_heal"),int(row.native_preview.Heal)])
						var preview_panel: Control = $UI._reference.get_node_or_null("CombatPreview")
						var bounds: Rect2 = get_viewport().get_visible_rect()
						var image: Image = get_viewport().get_texture().get_image()
						var ok: bool = clicks and order_ok and estimate_ok and requests.size()==1 and authority.get("authoritative",false) and same_contract(authority,row.native_actual) and core_visible and confirmation_visible and heal_visible and preview_panel!=null and preview_panel.is_visible_in_tree() and bounds.encloses(preview_panel.get_global_rect()) and image.get_size()==resolution
						var screenshot := ""
						var pixel_sha := ""
						if resolution.x==960 and cap==60 and delay==300 and row.equipment_arm=="PublishedFivePurpleVitality":
							screenshot = "%s-L%d-%s-%s.png" % [row.hero,level,row.case_id,language]
							var pixels: PackedByteArray = image.save_png_to_buffer()
							var root: String = OS.get_environment("PR13_ORIGINAL_PIXELS")
							var original := FileAccess.open(root+"/"+screenshot,FileAccess.WRITE)
							ok = ok and original!=null and pixels.size()>8
							if original != null: original.store_buffer(pixels); original.close()
							original = null
							var hash := HashingContext.new()
							hash.start(HashingContext.HASH_SHA256)
							hash.update(pixels)
							pixel_sha = hash.finish().hex_encode()
							hash = null
						image = null
						var clicked_play: bool = await click_named("PlayCardsButton")
						var plays: Array = gateway.sent.filter(func(r):return r.kind=="battle.play_cards")
						var codec := Proto.new()
						var decoded: Dictionary = codec.decode("BattlePlayCardsCommand",plays[0].wire) if plays.size()==1 else {}
						ok = ok and clicked_play and plays.size()==1 and codec.error.is_empty() and decoded.get("card_instance_ids",[])==row.selected_instance_ids
						var actual: Dictionary = {"original_native_line_SHA256":row.source_original_line_sha256,"native_before_SHA256":row.native_before_sha256,"native_after_SHA256":row.native_after_sha256,"selection_order":row.selected_instance_ids,"client_estimate":estimated,"accepted_authoritative_preview":authority,"native_actual":row.native_actual,"ordinary_card_heal":row.normal_card_heal,"conflict_recovery":row.conflict_recovery,"visible_preview_texts":texts,"decoded_protocol_order":decoded.get("card_instance_ids",[]),"original_pixel_SHA256":pixel_sha}
						observations.append({"case_id":row.case_id,"hero":row.hero,"weapon_level":level,"equipment_arm":row.equipment_arm,"language":language,"resolution":[resolution.x,resolution.y],"fps_cap":cap,"controlled_response_delay_ms":delay,"passed":ok,"actual":actual,"screenshot":screenshot})
						if not ok: failures.append({"case_id":row.case_id,"hero":row.hero,"weapon_level":level,"equipment_arm":row.equipment_arm,"language":language,"resolution":[resolution.x,resolution.y],"fps_cap":cap,"delay":delay,"actual":actual})
	P.set_language(original_language)
	Game.room = {}
	Game.selected_cards = []
	Game.clear_combat_preview()
	Game.gateway = old_gateway
	gateway.free()
	var result: Dictionary = {"ok":failures.is_empty() and witnesses.size()==18 and observations.size()==972,"source_sha":data.source_sha,"native_witnesses":18,"weapon_level":level,"observations":observations,"failures":failures,"expected_rows":972,"expected_screenshots":18,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name(),"scope":"Actual native original-room witness projection, GUI selection, current estimator, guarded controlled preview reply and real Protobuf order; RENDER only"}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().create_timer(0.25).timeout
	get_tree().quit(0 if result.ok else 1)
