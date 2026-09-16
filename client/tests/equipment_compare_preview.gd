extends Node

const OUTPUT := "res://evidence/equipment-comparison"
const EquipmentCompareDialog = preload("res://ui/equipment_compare_dialog.gd")
var errors: Array[String] = []
var direct_equip_calls := 0

func _ready() -> void:
	Game.gateway.set_process(false)
	Game.gateway.persist_session = false
	Game.gateway.online = true
	Game.room = {}
	Game.connection = "装备对比 · 测试数据"
	Game.lobby = {"player": {"userId": "equipment-preview"}, "wallet": {"gold": 100000}, "classWeapons": [], "equippedLoadouts": []}
	var current := _gear("head-current", "Head", "Purple", "Fire", "Bulwark")
	var selected := _gear("head-selected", "Head", "Orange", "Water", "Piercing", "DrawInterval")
	$UI.inventory = {"equipments": [
		current,
		_gear("chest-current", "Chest", "Purple", "Earth", "Bulwark"),
		_gear("hands-current", "Hands", "Purple", "Metal", "Bulwark"),
		_gear("legs-current", "Legs", "Purple", "Wood", "Piercing"),
		selected,
	], "consumables": {}}
	for index in range(14):
		var slots := ["Head", "Chest", "Hands", "Legs", "Feet"]
		var elements := ["Fire", "Water", "Wood", "Metal", "Earth"]
		$UI.inventory.equipments.append(_gear("scroll-item-%02d" % index, slots[index % slots.size()], "Blue", elements[index % elements.size()], "Piercing"))
	$UI.gear_draft = ["head-current", "chest-current", "hands-current", "legs-current", null]
	$UI.screen = "gear"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT))
	await _capture(selected, Vector2i(1920, 1080))
	await _capture(selected, Vector2i(1280, 720))
	await _verify_null_affix_hidden()
	await _verify_empty_slot_bypass()
	await _verify_inventory_drag_and_draft()
	var report := {"ok": errors.is_empty(), "errors": errors, "screenshots": 4, "direct_equip_calls": direct_equip_calls}
	FileAccess.open(OUTPUT + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	get_tree().quit(0 if report.ok else 1)

func _capture(selected: Dictionary, resolution: Vector2i) -> void:
	get_window().size = resolution
	$UI._render()
	await get_tree().process_frame
	await get_tree().process_frame
	var summary_text := ""
	for node_name in ["EquipmentSummaryTitle", "EquipmentAttributeSummary", "EquipmentSetSummary"]:
		var summary_label: Label = $UI._reference.find_child(node_name, true, false)
		if summary_label != null: summary_text += summary_label.text + "\n"
	for expected in ["装备属性汇总", "火 · 增伤 +15% · 抗性 +9%", "载壁 3/3 · 已生效", "破击 1/3 · 未激活", "上盾 +24% / 减伤 +12%（仅盾卫）", "提升直伤（未生效）"]:
		if not summary_text.contains(expected): errors.append("Missing loadout summary %s at %s" % [expected, resolution.x])
	var summary_panel: Control = $UI._reference.find_child("EquipmentSummaryPanel", true, false)
	if summary_panel == null: errors.append("Missing equipment summary panel at %s" % resolution.x)
	var save_button: Control = $UI._reference.find_child("SaveLoadoutButton", true, false)
	var attribute_scroll: ScrollContainer = $UI._reference.find_child("EquipmentAttributeScroll", true, false)
	var set_scroll: ScrollContainer = $UI._reference.find_child("EquipmentSetScroll", true, false)
	if save_button == null or attribute_scroll == null or set_scroll == null:
		errors.append("Missing summary alignment controls at %s" % resolution.x)
	else:
		var center_x := save_button.position.x + save_button.size.x * 0.5
		if not is_equal_approx(summary_panel.position.x + summary_panel.size.x * 0.5, center_x): errors.append("Summary panel is not centered on save button at %s" % resolution.x)
		if not is_equal_approx(center_x - (attribute_scroll.position.x + attribute_scroll.size.x * 0.5), set_scroll.position.x + set_scroll.size.x * 0.5 - center_x): errors.append("Summary columns are not mirrored at %s" % resolution.x)
		if not is_equal_approx(attribute_scroll.size.x, set_scroll.size.x): errors.append("Summary columns differ in size at %s" % resolution.x)
		if not is_equal_approx(attribute_scroll.size.y, 81.0) or not is_equal_approx(set_scroll.size.y, 81.0): errors.append("Summary viewports do not show three standard rows at %s" % resolution.x)
		if attribute_scroll.vertical_scroll_mode != ScrollContainer.SCROLL_MODE_SHOW_NEVER or set_scroll.vertical_scroll_mode != ScrollContainer.SCROLL_MODE_SHOW_NEVER: errors.append("Summary scroll bars are not hidden at %s" % resolution.x)
		attribute_scroll.scroll_vertical = 10000
		set_scroll.scroll_vertical = 10000
		await get_tree().process_frame
		if attribute_scroll.scroll_vertical <= 0: errors.append("Scattered equipment attributes cannot scroll at %s" % resolution.x)
		if set_scroll.scroll_vertical <= 0: errors.append("Affix sets cannot scroll at %s" % resolution.x)
		attribute_scroll.scroll_vertical = 0
		set_scroll.scroll_vertical = 0
		await get_tree().process_frame
	RenderingServer.force_draw(false)
	get_viewport().get_texture().get_image().save_png(OUTPUT + "/equipment_summary_%s.png" % resolution.x)
	$UI._show_equipment_details(selected, _direct_equip, "确认穿戴")
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().create_timer(0.4).timeout
	var dialog: Control = $UI.get_node_or_null("EquipmentComparisonDialog")
	if dialog == null:
		errors.append("Missing comparison dialog at %s" % resolution.x)
		return
	var text := _all_text(dialog)
	for expected in ["紫火头部 +0", "橙水头部 +0", "火元素增伤", "水元素增伤", "载壁", "破击", "3/3 已激活", "2/2 已激活", "+27%"]:
		if not text.contains(expected): errors.append("Missing %s at %s" % [expected, resolution.x])
	if text.contains("+7%") or text.contains("+4%"):
		errors.append("Cross-element stats were incorrectly subtracted at %s" % resolution.x)
	if dialog.find_children("QualityBackground", "ColorRect", true, false).size() != 2:
		errors.append("Quality backgrounds are not layered at %s" % resolution.x)
	if dialog.find_children("QualityFrame", "TextureRect", true, false).size() != 2:
		errors.append("Quality frames are not layered at %s" % resolution.x)
	if dialog.find_children("EquipmentIcon", "TextureRect", true, false).size() != 2:
		errors.append("Equipment icons are not layered at %s" % resolution.x)
	if dialog.find_child("CloseComparison", true, false) != null:
		errors.append("Comparison title close button is still visible at %s" % resolution.x)
	var shell: Control = dialog.get_node_or_null("ComparisonShell")
	if shell == null or not Rect2(Vector2.ZERO, Vector2(1920, 1080)).encloses(shell.get_rect()):
		errors.append("Comparison shell outside logical canvas at %s" % resolution.x)
	RenderingServer.force_draw(false)
	get_viewport().get_texture().get_image().save_png(OUTPUT + "/equipment_compare_%s.png" % resolution.x)
	dialog.queue_free()
	await get_tree().process_frame
	await get_tree().process_frame

func _verify_null_affix_hidden() -> void:
	var current := _gear("null-current", "Chest", "Blue", "Earth", "<null>")
	var selected := _gear("null-selected", "Chest", "Purple", "Fire", "<null>")
	var dialog := EquipmentCompareDialog.new()
	add_child(dialog)
	dialog.open(selected, current, [current])
	await get_tree().process_frame
	if _all_text(dialog).contains("<null>"):
		errors.append("Null affix placeholder is still visible")
	dialog.queue_free()
	await get_tree().process_frame

func _verify_empty_slot_bypass() -> void:
	var feet := _gear("feet-selected", "Feet", "Blue", "Water", "", "ForcedEscape")
	$UI._show_equipment_details(feet, _direct_equip, "确认穿戴")
	if direct_equip_calls != 1: errors.append("Empty slot did not equip directly")
	if $UI.get_node_or_null("EquipmentComparisonDialog") != null: errors.append("Empty slot opened a comparison dialog")

func _verify_inventory_drag_and_draft() -> void:
	$UI.screen = "gear"
	$UI._render()
	await get_tree().process_frame
	await get_tree().process_frame
	var scroll = $UI._reference.find_child("EquipmentInventoryScroll", true, false)
	if scroll == null:
		errors.append("Equipment inventory is missing its drag scroll")
		return
	var maximum := maxi(0, int(scroll.get_v_scroll_bar().max_value - scroll.get_v_scroll_bar().page))
	if maximum <= 0:
		errors.append("Equipment inventory fixture cannot scroll vertically")
		return
	scroll._begin(Vector2(1500, 650))
	scroll._drag(Vector2(1500, 350))
	var dragged_position: int = scroll.scroll_vertical
	if dragged_position <= 0: errors.append("Dragging an equipment entry does not scroll the inventory")
	if scroll.can_activate(): errors.append("Equipment entry can activate during a drag")
	scroll._finish()
	await get_tree().process_frame
	var expected_position: int = $UI._equipment_scroll
	var selected: Dictionary = $UI.inventory.equipments.back()
	var draft_before: Array = $UI.gear_draft.duplicate()
	$UI._equip(selected)
	if Game.busy: errors.append("Local equipment draft selection entered network busy state")
	await get_tree().process_frame
	await get_tree().process_frame
	var restored = $UI._reference.find_child("EquipmentInventoryScroll", true, false)
	if restored == null or abs(restored.scroll_vertical - expected_position) > 1:
		errors.append("Equipment inventory scroll position reset after local draft selection")
	if selected.instanceId not in $UI.gear_draft:
		errors.append("Selected equipment was not stored in the local draft")
	var selected_entry: Button = $UI._reference.find_child("EquipmentEntry_" + selected.instanceId, true, false)
	if selected_entry == null or not selected_entry.text.begins_with("已选"):
		errors.append("Draft equipment is missing its selected treatment")
	if _all_text($UI._reference).contains("当前没有词缀套装"):
		errors.append("Draft equipment did not update the reserved set summary")
	$UI.gear_draft = draft_before

func _direct_equip() -> void:
	direct_equip_calls += 1

func _all_text(root: Node) -> String:
	var result := ""
	for node in root.find_children("*", "Control", true, false):
		if node is Label or node is Button: result += node.text + "\n"
	return result

func _gear(id: String, slot: String, quality: String, element: String, affix: String, secondary: String = "") -> Dictionary:
	return {"instanceId": id, "slot": slot, "quality": quality, "element": element, "effectAffix": affix, "secondaryTrait": secondary, "level": 0, "location": "Inventory", "isBound": false}
