extends "res://tests/pr13_wait_frames.gd"

var failures: Array = []

func _ready() -> void:
	var evidence_directory := OS.get_environment("FANTASYCARD_ART_EVIDENCE")
	if not evidence_directory.is_empty(): output = evidence_directory
	Game.gateway.set_process(false)
	Game.gateway.persist_session = false
	Game.gateway.online = true
	Game.connection = "Controlled cloud render fixture"
	Game.lobby = {"player":{"userId":"preview-player"},"wallet":{"gold":1200},"decks":[{"heroClass":"Mage","cardIds":["MAG-01","MAG-04","GP01","MAG-10","C01"]}],"materials":{"equipmentFragments":32},"equippedLoadouts":[],"classWeapons":[{"heroClass":"Mage","level":2,"version":1}]}
	$UI.inventory = {"equipments":[],"consumables":{"healthPotionCount":2,"advancedBagCount":1,"topBagCount":1}}
	$UI._shop_inventory_ready = true
	$UI.gear_draft = [null,null,null,null,null]
	Callable(self,"_run").call_deferred()

func label_fits(label: Label, viewport: Rect2) -> bool:
	if label == null or not label.is_visible_in_tree() or label.get_visible_line_count() <= 0:
		return false
	if not viewport.encloses(label.get_global_rect()):
		return false
	var font: Font = label.get_theme_font("font")
	var size: int = label.get_theme_font_size("font_size")
	for line in label.text.split("\n"):
		if font.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x > label.size.x + 1.0:
			return false
	return true

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.socket.close()
	Game.gateway.persist_session = false
	Game.configuration_error = ""
	var old_language: String = P.language()
	get_window().mode = Window.MODE_WINDOWED
	var index := 0
	for hero in ["Mage", "Priest", "Guardian"]:
		for language in ["zh-CN", "en"]:
			P.set_language(language)
			for resolution in [Vector2i(1920,1080), Vector2i(1280,720), Vector2i(960,540)]:
				get_window().size = resolution
				for cap in [30,60,144]:
					Engine.max_fps = cap
					for delay in [0,100,300]:
						for number in [1,2,3]:
							index += 1
							reset()
							var authority: Dictionary = battle()
							authority.room_id = "b04-wait-room-%d" % index
							authority.room_revision = index + 1000
							authority.player.hero_class = hero
							authority.player.combat = {"hp":100,"maximum_hp":100,"shield":0}
							authority.player["draw_charge"] = "0.25"
							authority.player["draw_interval_seconds"] = "20"
							authority.player["base_draw_interval_seconds"] = "20"
							authority.player["draw_speed_remaining_ms"] = 0
							authority.player["draw_block_speed_remaining_ms"] = 0
							authority.player["draw_block_remaining_ms"] = 0
							authority.player["stun_remaining_ms"] = 0
							var expected_reason := "full_hand" if number == 1 else ("stunned" if number == 2 else "drawing")
							if number == 1:
								authority.player.hand = []
								for card in ["C01","C02","C03","C04","C05"]:
									authority.player.hand.append({"instance_id":"b04-"+card,"card_id":card,"level":0})
							elif number == 2:
								authority.player.stun_remaining_ms = 7500
								authority.allowed_actions.erase("battle.play_cards")
							else:
								authority.player.hand = []
							if delay > 0:
								await get_tree().create_timer(float(delay)/1000.0).timeout
							Game.room = authority.duplicate(true)
							Game.hero_class = hero
							if not Game.room.player.hand.is_empty():
								Game.selected_cards = [Game.room.player.hand[0].instance_id]
							await present()
							var waiting: Dictionary = Game.combat_wait_state()
							var label: Label = $UI._reference.get_node_or_null("CombatWaitReason")
							var status: Label = $UI._reference.get_node_or_null("PlayerStatus")
							var percent: Label = $UI._reference.get_node_or_null("DrawChargePercent")
							var bar: Range = $UI._reference.get_node_or_null("DrawChargeBar")
							var play: Button = $UI._reference.get_node_or_null("PlayCardsButton")
							var bounds: Rect2 = get_viewport().get_visible_rect()
							var expected_text: String = P.localized("battle_wait_"+expected_reason)
							var ok: bool = label_fits(label,bounds) and label.text == expected_text and waiting.reason == expected_reason
							ok = ok and play != null and play.is_visible_in_tree() and bounds.encloses(play.get_global_rect())
							ok = ok and bar != null and bar.value >= 0.0 and bar.value <= 1.0 and label_fits(percent,bounds)
							var actual: Dictionary = {"reason":waiting,"wait_text":label.text if label != null else "MISSING","status_text":status.text if status != null else "MISSING","progress_text":percent.text if percent != null else "MISSING","progress":bar.value if bar != null else -1.0,"authority_draw_charge":"0.25","authority_interval_seconds":"20","authority_stun_ms":authority.player.stun_remaining_ms,"draw_speed_ms":authority.player.draw_speed_remaining_ms,"double_charge_ms":authority.player.draw_block_speed_remaining_ms,"controlled_authority_snapshot":true}
							if number == 1:
								ok = ok and waiting.hand_count == 5 and waiting.legal_opportunity and not play.disabled
								actual["full_hand_keeps_legal_play"] = not play.disabled
							elif number == 2:
								var digits := RegEx.new()
								digits.compile("[0-9]+\\.[0-9]")
								var matched: RegExMatch = digits.search(status.text if status != null else "")
								var shown := float(matched.get_string()) if matched != null else -1.0
								var elapsed := maxi(0, Time.get_ticks_msec()-int($UI._draw_charge_anchor_msec))
								var expected_seconds := maxf(0.0, float(7500-elapsed)/1000.0)
								ok = ok and waiting.remaining_ms == 7500 and not waiting.legal_opportunity and play.disabled and label_fits(status,bounds)
								ok = ok and shown > 0.0 and shown <= 7.5 and absf(shown-expected_seconds) <= 0.2
								actual.merge({"shown_remaining_seconds":shown,"expected_remaining_seconds_at_observation":expected_seconds,"elapsed_since_authority_anchor_ms":elapsed,"display_precision_bound_seconds":0.2})
							else:
								var elapsed := maxi(0, Time.get_ticks_msec()-int($UI._draw_charge_anchor_msec))
								var projected := fposmod(0.25+float(elapsed)/20000.0,1.0)
								ok = ok and waiting.hand_count == 0 and not waiting.legal_opportunity and play.disabled and (status == null or not status.is_visible_in_tree())
								ok = ok and absf(bar.value-projected) <= 0.02 and not label.text.contains("20")
								actual.merge({"progress_from_authority_and_bounded_frame_interpolation":true,"expected_progress_at_observation":projected,"elapsed_since_authority_anchor_ms":elapsed,"progress_frame_precision_bound":0.02,"twenty_second_interval_not_reported_as_measured_wait":true})
							var image: Image = get_viewport().get_texture().get_image()
							ok = ok and image.get_size() == resolution and get_window().size == resolution
							var screenshot := ""
							if resolution.x == 960 and cap == 60 and delay == 300:
								screenshot = "%s-T0%d-%s.png" % [hero,number,language]
								ok = ok and image.save_png(output+"/"+screenshot) == OK
								var bytes: PackedByteArray = FileAccess.get_file_as_bytes(output+"/"+screenshot)
								var protected_root: String = OS.get_environment("PR13_ORIGINAL_PIXELS")
								DirAccess.make_dir_recursive_absolute(protected_root)
								var original := FileAccess.open(protected_root+"/"+screenshot,FileAccess.WRITE)
								ok = ok and original != null and bytes.size() > 8
								if original != null:
									original.store_buffer(bytes)
									original.close()
								original = null
								var hash := HashingContext.new()
								hash.start(HashingContext.HASH_SHA256)
								hash.update(bytes)
								actual["original_pixel_SHA256"] = hash.finish().hex_encode()
								hash = null
								actual["original_pixel_bytes"] = bytes.size()
								actual["original_pixel_copied_immediately_after_successful_capture"] = true

							image = null
							var cid := "PR13-B04.3-T0%d" % number
							observations.append({"case_id":cid,"hero":hero,"language":language,"resolution":[resolution.x,resolution.y],"fps_cap":cap,"controlled_response_delay_ms":delay,"passed":ok,"actual":actual,"screenshot":screenshot})
							if not ok:
								failures.append({"index":index,"case_id":cid,"hero":hero,"language":language,"resolution":[resolution.x,resolution.y],"fps_cap":cap,"delay":delay,"actual":actual})
	P.set_language(old_language)
	Game.room = {}
	Game.selected_cards = []
	Game.combat_preview = {}
	await present()
	var result: Dictionary = {"ok":failures.is_empty() and observations.size()==486,"source_sha":OS.get_environment("PR13_SOURCE_SHA"),"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name(),"observations":observations,"failures":failures,"expected_rows":486,"expected_screenshots":18,"scope":"Actual cloud pixels with declared controlled current authority snapshots; no natural LIVE, PG, elapsed combat duration or hardware FPS claim"}
	var file := FileAccess.open(output+"/native-result.json",FileAccess.WRITE)
	file.store_string(JSON.stringify(result))
	file.close()
	file = null
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().create_timer(0.25).timeout
	get_tree().quit(0 if result.ok else 1)
