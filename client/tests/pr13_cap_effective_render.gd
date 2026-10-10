extends "res://tests/pr13_tuning_recovery_render.gd"

@export var cap_case := "PR13-B08.4-T01"
@export var cap_diagnostic_one_row := false
const CapDetails = preload("res://ui/numerical_details.gd")
const CAP_SOURCE := "8ff06ef8fff0ed592fae52facca680ddf9a5b8a7"
var cap_checks := 0
var inactive_checks := 0

func cap_button_click(button: Button) -> bool:
	if button == null or not button.is_visible_in_tree() or button.disabled: return false
	var viewport: Viewport = button.get_viewport()
	var point: Vector2 = button.get_global_transform_with_canvas() * (button.size * .5)
	viewport.notify_mouse_entered()
	var motion := InputEventMouseMotion.new()
	motion.position = point
	motion.global_position = point
	viewport.push_input(motion, true)
	await get_tree().process_frame
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.button_mask = MOUSE_BUTTON_MASK_LEFT
	press.pressed = true
	press.position = point
	press.global_position = point
	viewport.push_input(press, true)
	await get_tree().process_frame
	var release: InputEventMouseButton = press.duplicate()
	release.pressed = false
	release.button_mask = 0
	viewport.push_input(release, true)
	await get_tree().process_frame
	return true

func cap_popup_text(dialog: AcceptDialog) -> String:
	var texts := PackedStringArray()
	for label in dialog.find_children("*", "Label", true, false):
		if label.is_visible_in_tree(): texts.append(label.text)
	return "\n".join(texts)

func cap_scroll(dialog: AcceptDialog, scroll: ScrollContainer, label: Label) -> Dictionary:
	var seen := {}
	var samples: Array = []
	var window_rect := dialog.get_visible_rect()
	var point: Vector2 = scroll.get_global_transform_with_canvas() * (scroll.size * .5)
	for step in range(24):
		dialog.notify_mouse_entered()
		var motion := InputEventMouseMotion.new()
		motion.position = point
		motion.global_position = point
		dialog.push_input(motion, true)
		await get_tree().process_frame
		var clip: Rect2 = scroll.get_global_rect().intersection(window_rect)
		var rect: Rect2 = label.get_global_rect()
		var line_y: float = rect.position.y
		var scale_y: float = label.get_global_transform_with_canvas().get_scale().y
		var visible: Array = []
		for index in range(label.get_line_count()):
			var height: float = float(label.get_line_height(index)) * scale_y
			var line := Rect2(rect.position.x, line_y, rect.size.x, height)
			if clip.encloses(line):
				seen[index] = true
				visible.append(index)
			line_y += height + float(label.get_theme_constant("line_spacing")) * scale_y
		samples.append({"scroll":scroll.scroll_vertical, "visible_lines":visible})
		var down := InputEventMouseButton.new()
		down.button_index = MOUSE_BUTTON_WHEEL_DOWN
		down.pressed = true
		down.position = point
		down.global_position = point
		dialog.push_input(down, true)
		await get_tree().process_frame
		var up: InputEventMouseButton = down.duplicate()
		up.pressed = false
		dialog.push_input(up, true)
		await get_tree().process_frame
	return {"wheel_notches":24, "wheel_press_release_events":48, "samples":samples, "line_count":label.get_line_count(), "all_lines_reachable":seen.size()==label.get_line_count(), "last_line_reachable":seen.has(label.get_line_count()-1), "horizontal_scroll_disabled":scroll.horizontal_scroll_mode==ScrollContainer.SCROLL_MODE_DISABLED, "font_size":label.get_theme_font_size("font_size"), "wrapped":label.autowrap_mode==TextServer.AUTOWRAP_WORD_SMART}

func cap_project_items(native: Array, selected: Dictionary) -> Dictionary:
	var before: Array = native.duplicate(true)
	for item in before: item["location"] = "Equipped"
	var candidate := selected.duplicate(true)
	var original_id: String = str(candidate.instanceId)
	candidate.instanceId = "cap-display-replacement-" + original_id
	candidate["location"] = "Inventory"
	return {"before":before, "candidate":candidate, "original_candidate_id":original_id, "display_candidate_id":candidate.instanceId, "identity_projection_only":true}

func cap_witness(row: Dictionary, final_witness: bool, inactive_projection: bool = false) -> Dictionary:
	var actual: Dictionary = row.actual
	var before: Array = actual.before if cap_case.ends_with("T01") else actual.items
	if inactive_projection: before = actual.inactive_items
	var selected: Dictionary = actual.after[0] if cap_case.ends_with("T01") else before[0]
	var projection := cap_project_items(before, selected)
	Game.hero_class = actual.hero
	Game.room = {}
	Game.busy = false
	Game.selected_cards = []
	Game.clear_combat_preview()
	$UI.screen = "gear"
	$UI.inventory = {"equipments":[projection.candidate] + projection.before, "consumables":{}}
	$UI.gear_draft = projection.before.map(func(item):return str(item.instanceId))
	$UI._equipment_scroll = 0
	await present()
	var entry: Button = $UI._reference.find_child("EquipmentEntry_" + str(projection.candidate.instanceId), true, false) as Button
	var comparison_clicked: bool = await cap_button_click(entry)
	var comparison: Control = $UI.get_node_or_null("EquipmentComparisonDialog")
	var open_comparison: bool = comparison_clicked and comparison != null
	var effective: Button = null
	if comparison != null:
		for button in comparison.find_children("*", "Button", true, false):
			if button.text == CapDetails.text("title"): effective = button
	var gains_clicked: bool = await cap_button_click(effective)
	var dialog: AcceptDialog = null
	if comparison != null:
		for child in comparison.find_children("*", "AcceptDialog", true, false):
			if child.visible: dialog = child
	var content: String = cap_popup_text(dialog) if dialog != null else ""
	var gains_opened: bool = gains_clicked and dialog != null
	var stage_words: Array = ["resistance_stage", "draw_stage", "shield_stage"]
	var semantics: bool = stage_words.all(func(key):return content.contains(CapDetails.text(key)))
	var numbers := true
	if cap_case.ends_with("T01"):
		var wanted := "%.2f / %.2f / %.2f → %.2f / %.2f / %.2f  (%+.2f)" % [float(actual.raw_before)*100, float(actual.effective_before)*100, float(actual.capped_before)*100, float(actual.raw_after)*100, float(actual.effective_after)*100, float(actual.capped_after)*100, float(actual.marginal_effective)*100]
		numbers = content.contains(wanted) and is_zero_approx(float(actual.marginal_effective))
	elif cap_case.ends_with("T02"):
		var raw: float = float(actual.equipment_raw)
		var interval: float = float(actual.equipment_interval)
		var wanted := "%.2f / %.2f / %.2f → %.2f / %.2f / %.2f  (%+.2f)" % [raw, interval, maxf(0, interval-raw), raw, interval, maxf(0, interval-raw), 0.0]
		numbers = content.contains(wanted) and bool(actual.post_clamp_conversion)
	else:
		var reduction: Dictionary = CapDetails.inspect(before, actual.hero).bulwark_reduction_percent
		numbers = int(actual.requested_shield)==int(actual.effective_shield)+int(actual.shield_overflow) and not bool(actual.candidate_activation)
		if actual.hero != "Guardian": semantics = semantics and content.contains(CapDetails.text("not_applicable")) and is_zero_approx(float(reduction.excess))
		elif inactive_projection: semantics = semantics and content.contains(CapDetails.text("inactive_affix")) and is_zero_approx(float(reduction.excess))
	var scrolling := {"all_lines_reachable":false, "last_line_reachable":false, "horizontal_scroll_disabled":false, "font_size":0, "wrapped":false}
	if dialog != null:
		var scroll: ScrollContainer = dialog.find_children("*", "ScrollContainer", true, false)[0]
		var label: Label = scroll.find_children("*", "Label", true, false)[0]
		scrolling = await cap_scroll(dialog, scroll, label)
	var image_saved := true
	if final_witness and P.language()=="en" and get_window().size.x==960 and Engine.max_fps==60:
		await RenderingServer.frame_post_draw
		image_saved = get_viewport().get_texture().get_image().save_png(output+"/"+cap_case+"-gains.png")==OK
	var closed := false
	if dialog != null:
		var weak := weakref(dialog)
		var close_clicked: bool = await cap_button_click(dialog.get_ok_button())
		await get_tree().process_frame
		await get_tree().process_frame
		closed = close_clicked and weak.get_ref()==null
	var comparison_closed := false
	if comparison != null:
		var cancel: Button = comparison.find_child("CancelEquip", true, false) as Button
		var close_clicked: bool = await cap_button_click(cancel)
		await get_tree().process_frame
		comparison_closed = close_clicked and $UI.get_node_or_null("EquipmentComparisonDialog")==null
	if inactive_projection: inactive_checks += 1
	else: cap_checks += 1
	var inactive := {}
	if cap_case.ends_with("T03") and not inactive_projection: inactive = await cap_witness(row,false,true)
	return {"hero":actual.hero, "original_native_line_sha256":row.original_line_sha256, "element":actual.get("element", "Fire"), "level":actual.get("level", 5), "original_and_display_identity":projection, "inactive_projection":inactive_projection, "comparison_opened_by_mouse":open_comparison, "gains_opened_by_mouse":gains_opened, "complete_stage_explanations":semantics, "original_values_and_marginal_delta_visible":numbers, "full_text":content, "scroll":scrolling, "popup_closed_by_mouse":closed, "comparison_closed_by_mouse":comparison_closed, "inactive_context":inactive, "passed":open_comparison and gains_opened and semantics and numbers and scrolling.all_lines_reachable and scrolling.last_line_reachable and scrolling.horizontal_scroll_disabled and int(scrolling.font_size)>=18 and bool(scrolling.wrapped) and closed and comparison_closed and image_saved and (inactive.is_empty() or bool(inactive.get("passed",false)))}

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	tuning_case = cap_case
	var raw := FileAccess.get_file_as_string("res://tests/data/cap_effective_native.json")
	var data: Dictionary = JSON.parse_string(raw)
	assert(data.source_sha==CAP_SOURCE and data.rows.size()==30 and not data.render_executed)
	var vectors: Array = data.rows.filter(func(row):return row.case_id==cap_case)
	vectors.sort_custom(func(a,b):return (1 if a.actual.hero=="Mage" else 0)<(1 if b.actual.hero=="Mage" else 0))
	Game.set_process(false)
	$UI.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := CodecGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	var original_language: String = P.language()
	var original_hero: String = Game.hero_class
	get_window().mode = Window.MODE_WINDOWED
	get_viewport().gui_embed_subwindows = true
	var languages: Array = ["en"] if cap_diagnostic_one_row else ["zh-CN","en"]
	var sizes: Array = [Vector2i(960,540)] if cap_diagnostic_one_row else [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]
	var caps: Array = [60] if cap_diagnostic_one_row else [30,60,144]
	for language in languages:
		P.set_language(language)
		for size in sizes:
			get_window().size = size
			for fps in caps:
				Engine.max_fps = fps
				var results: Array = []
				for row in vectors: results.append(await cap_witness(row,row==vectors.back()))
				await record_tuning_row(results.all(func(row):return row.passed), {"native_source_sha":CAP_SOURCE,"native_vectors_sha256":raw.sha256_text(),"original_native_witnesses":results,"no_wire_or_live_claim":true},language,size,fps)
	P.set_language(original_language)
	Game.hero_class = original_hero
	Game.gateway = old_gateway
	gateway.free()
	var result := {"ok":case_verdicts.get(tuning_case,false) and observations.size()==(1 if cap_diagnostic_one_row else 18) and DisplayServer.get_name()!="headless","case_id":cap_case,"observations":observations,"native_witness_renders":cap_checks,"additional_inactive_contexts":inactive_checks,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name(),"diagnostic_only":cap_diagnostic_one_row,"whole_task_accepted":false}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().create_timer(.25).timeout
	get_tree().quit(0 if result.ok else 1)
