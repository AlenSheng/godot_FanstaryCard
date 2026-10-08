extends "res://tests/art_preview.gd"

const P = preload("res://ui/palette.gd")
var observations: Array = []
var verdicts := {}

func battle() -> Dictionary:
	return {"room_id":"wait-room", "match_id":"wait-match", "room_revision":10,
		"allowed_actions":["battle.play_cards", "battle.select_target"],
		"player":{"player_id":"preview-player", "hero_class":"Guardian", "phase":"Pve",
			"combat":{"hp":60, "maximum_hp":100, "shield":49},
			"hand":[{"instance_id":"shield-card", "card_id":"C05", "level":0}]},
		"pve":{"battle_id":"wait-battle", "current_target_id":"fire-bat", "monsters":[{"monster_id":"fire-bat", "hp":40, "maximum_hp":44, "shield":0, "intent_kind":"Attack", "intent_element":"Fire", "intent_value":2}]}}

func reset() -> void:
	Game.room = {}
	Game.ready_prompt = {}
	Game.settlement = {}
	Game.selected_cards = []
	Game.combat_preview = {}
	Game._pending_commands = {}
	Game._latest_commands = {}
	Game._pending_play = {}
	Game._queued_command = {}
	Game.busy = false
	Game.gateway.online = true
	Game.gateway.recovering = false
	Game.hero_class = "Guardian"
	$UI.screen = "hall"

func present() -> void:
	$UI._render()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw

func text_visible(value: String) -> bool:
	for node in $UI._reference.find_children("*", "Label", true, false):
		if node.is_visible_in_tree() and node.text.contains(value) and node.get_visible_line_count()>0:
			return true
	return false

func button_visible(value: String) -> bool:
	for node in $UI._reference.find_children("*", "Button", true, false):
		if node.is_visible_in_tree() and node.text == value and not node.disabled:
			return Rect2(Vector2.ZERO, Vector2(1920,1080)).encloses(node.get_global_rect())
	return false

func record(id: String, passed: bool, actual: Dictionary) -> void:
	if not verdicts.has(id): verdicts[id] = true
	verdicts[id] = verdicts[id] and passed
	observations.append({"case_id":id, "language":P.language(), "resolution":[get_window().size.x,get_window().size.y], "passed":passed, "actual":actual})

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	Game.gateway.set_process(false)
	Game.gateway.socket.close()
	Game.gateway.persist_session = false
	Game.configuration_error = ""
	var original_language := P.language()
	var polling: Dictionary = preload("res://tests/test_settlement_polling.gd").new().run_test()
	var acknowledgement: Dictionary = preload("res://tests/test_settlement_return.gd").new().run_test()
	for language in ["zh-CN", "en"]:
		P.set_language(language)
		for resolution in [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]:
			get_window().size = resolution
			reset()
			var deadline := Time.get_unix_time_from_system()*1000.0+12000.0
			Game.ready_prompt = {"ready_players":1,"required_players":2,"deadline_unix_ms":deadline}
			await present()
			var remaining := false
			for label in $UI._reference.find_children("*", "Label", true, false):
				if label.text.contains("11") or label.text.contains("12"): remaining = true
			record("PR13-B11.1-T01",remaining and button_visible(P.localized_text("准备就绪")),{"deadline_source":"injected authoritative deadline_unix_ms", "remaining_from_deadline":remaining, "estimated_server_finish_present":false})
			reset()
			Game.room = {"match_id":"wait-match","player":{"phase":"Extracted"}}
			Game.settlement_query_failed = false
			await present()
			record("PR13-B11.1-T02",text_visible(P.localized("settlement_pending_message")) and button_visible(P.localized("settlement_retry")) and Game.settlement.is_empty(),{"visible_processing":text_visible(P.localized("settlement_pending_message")),"receipt_not_received":Game.settlement.is_empty(),"retry_available":button_visible(P.localized("settlement_retry"))})
			reset()
			Game.room = battle()
			Game._pending_commands = {"submitted-command":{"action":"battle.play_cards","payload":{},"deadline":Time.get_ticks_msec()+3000}}
			await present()
			var wait_label: Label = $UI._reference.get_node_or_null("CombatWaitReason")
			record("PR13-B11.1-T03",wait_label!=null and wait_label.text==P.localized("battle_wait_confirming") and not Game.combat_wait_state().legal_opportunity,{"waiting":Game.combat_wait_state(),"visible_submitted":wait_label!=null and wait_label.text==P.localized("battle_wait_confirming")})
			reset()
			Game.room = battle()
			Game.room.player.numerical_state = {"guardian_policy":"CurrentSteps", "guardian_remainder_tenths":8}
			await present()
			record("PR13-B07.4-T01",$UI._reference.get_node_or_null("GuardianRemainder")==null,{"old_room_candidate_remainder_hidden":$UI._reference.get_node_or_null("GuardianRemainder")==null})
			Game.room.player.numerical_state = {"guardian_policy":"FractionalRemainder", "guardian_remainder_tenths":8}
			Game.selected_cards = ["shield-card"]
			Game.combat_preview = {"authoritative":true,"core_element":"Earth","core_count":1,"damage_segments":[],"shield_gain":1,"shield_overflow":6}
			await present()
			var remainder: Button = $UI._reference.get_node_or_null("GuardianRemainder")
			var preview: Control = $UI._reference.get_node_or_null("CombatPreview")
			var parts := P.localized("battle_preview_shield_parts") % [7,1,6]
			record("PR13-B07.4-T02",remainder!=null and remainder.text=="8 / 10" and preview!=null and preview.tooltip_text.contains(parts) and int(Game.room.player.combat.shield)==49,{"integer_shield":7,"effective_shield":1,"overflow":6,"authoritative_remainder":8,"preview_no_state_mutation":int(Game.room.player.combat.shield)==49,"parts_exposed":preview!=null and preview.tooltip_text.contains(parts)})
			record("PR13-B07.4-T03",remainder!=null and remainder.text=="8 / 10" and remainder.get_theme_font("font").get_string_size(remainder.text,HORIZONTAL_ALIGNMENT_LEFT,-1,remainder.get_theme_font_size("font_size")).x < remainder.size.x,{"label":remainder.text if remainder!=null else "missing","key_value_fits":remainder!=null and remainder.text=="8 / 10"})
			Game._on_event("combat.hit",{"battle_id":"wait-battle","target_id":"fire-bat","source_id":"preview-player","shield_gain":1,"damage_segments":[]})
			await get_tree().process_frame
			await RenderingServer.frame_post_draw
			var integer_feedback := false
			for number in $UI.find_children("CombatNumber*","Label",true,false):
				if number.is_visible_in_tree() and number.text=="+1": integer_feedback = true
			verdicts["PR13-B07.4-T02"] = verdicts["PR13-B07.4-T02"] and integer_feedback
			observations.back().actual["effective_shield_feedback"] = integer_feedback
			reset()
			Game.settlement = {"settlementId":"retry-receipt","matchId":"wait-match","result":"Extracted","details":{}}
			await present()
			var retry_receipt_visible := button_visible(P.localized_text("返回")) and not Game.settlement.is_empty() and not Game.busy
			record("PR13-B11.2-T01",bool(polling.checks.get("duplicate real rejection preserves M",false)) and retry_receipt_visible,{"duplicate_rejection_preserves_original_match":polling.checks.get("duplicate real rejection preserves M"),"receipt_action_visible":retry_receipt_visible})
			record("PR13-B11.2-T03",acknowledgement.ok and retry_receipt_visible,{"actual_production_ack_checks":acknowledgement.checks,"restored_receipt_action_visible":retry_receipt_visible,"transport":"declared controlled synchronous gateway, no PG claim"})
			record("PR13-B11.4-T02",retry_receipt_visible and text_visible(P.localized("settlement_no_items")),{"long_english_and_receipt_button_fit":retry_receipt_visible,"empty_reward_explanation_visible":text_visible(P.localized("settlement_no_items"))})
			reset()
			Game.room = battle()
			await present()
			record("PR13-B11.2-T02",bool(polling.checks.get("old rejection cannot clear new match",false)) and $UI._reference.get_node_or_null("Card_C05")!=null,{"actual_old_callback_guard":polling.checks.get("old rejection cannot clear new match"),"new_room_card_visible":$UI._reference.get_node_or_null("Card_C05")!=null})
			Game.gateway._schedule_reconnect()
			Game.gateway.reconnect_enabled = false
			await present()
			wait_label = $UI._reference.get_node_or_null("CombatWaitReason")
			record("PR13-B11.4-T03",wait_label!=null and wait_label.text==P.localized("battle_wait_recovering") and not Game.allowed("battle.play_cards") and retry_receipt_visible,{"reconnect_explanation_visible":wait_label!=null and wait_label.text==P.localized("battle_wait_recovering"),"gameplay_disabled_until_authority":not Game.allowed("battle.play_cards"),"ack_retry_action_previously_visible":retry_receipt_visible,"scope":"actual rendered component callbacks; full natural three-cycle route and human evidence separate"})
			if language=="en" and resolution.x==960:
				get_viewport().get_texture().get_image().save_png(output+"/reconnect_narrow.png")
	P.set_language(original_language)
	var cases: Array = []
	for id in verdicts:
		cases.append({"case_id":id,"executed":true,"status":"Passed" if verdicts[id] else "Failed","profiles_executed":["OFFLINE","RENDER"],"actual":{"matrix_rows":6,"all_rows_passed":verdicts[id]},"scope":"Actual GPU UI with controlled authority/gateway fixtures. PG, LIVE, sampled experiment and human layers remain separate."})
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify({"cases":cases,"observations":observations,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name()}))
	print(JSON.stringify({"cases":cases.size(),"passed":verdicts.values().count(true),"observations":observations.size()}))
	get_tree().quit(0 if not verdicts.values().has(false) else 1)
