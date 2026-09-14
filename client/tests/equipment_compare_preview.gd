extends Node

const OUTPUT := "res://evidence/equipment-comparison"
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
	$UI.gear_draft = ["head-current", "chest-current", "hands-current", "legs-current", null]
	$UI.screen = "gear"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT))
	await _capture(selected, Vector2i(1920, 1080))
	await _capture(selected, Vector2i(1280, 720))
	await _verify_empty_slot_bypass()
	var report := {"ok": errors.is_empty(), "errors": errors, "screenshots": 2, "direct_equip_calls": direct_equip_calls}
	FileAccess.open(OUTPUT + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	get_tree().quit(0 if report.ok else 1)

func _capture(selected: Dictionary, resolution: Vector2i) -> void:
	get_window().size = resolution
	$UI._render()
	await get_tree().process_frame
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
	var shell: Control = dialog.get_node_or_null("ComparisonShell")
	if shell == null or not Rect2(Vector2.ZERO, Vector2(1920, 1080)).encloses(shell.get_rect()):
		errors.append("Comparison shell outside logical canvas at %s" % resolution.x)
	RenderingServer.force_draw(false)
	get_viewport().get_texture().get_image().save_png(OUTPUT + "/equipment_compare_%s.png" % resolution.x)
	dialog.queue_free()
	await get_tree().process_frame
	await get_tree().process_frame

func _verify_empty_slot_bypass() -> void:
	var feet := _gear("feet-selected", "Feet", "Blue", "Water", "", "ForcedEscape")
	$UI._show_equipment_details(feet, _direct_equip, "确认穿戴")
	if direct_equip_calls != 1: errors.append("Empty slot did not equip directly")
	if $UI.get_node_or_null("EquipmentComparisonDialog") != null: errors.append("Empty slot opened a comparison dialog")

func _direct_equip() -> void:
	direct_equip_calls += 1

func _all_text(root: Node) -> String:
	var result := ""
	for node in root.find_children("*", "Control", true, false):
		if node is Label or node is Button: result += node.text + "\n"
	return result

func _gear(id: String, slot: String, quality: String, element: String, affix: String, secondary: String = "") -> Dictionary:
	return {"instanceId": id, "slot": slot, "quality": quality, "element": element, "effectAffix": affix, "secondaryTrait": secondary, "level": 0, "location": "Inventory", "isBound": false}
