extends RefCounted

func run_test() -> Dictionary:
	var ui = load("res://ui/main.gd").new()
	var tree := Engine.get_main_loop() as SceneTree
	tree.root.add_child(ui)
	await tree.process_frame
	Game.lobby = {"player": {"displayName": "Codex", "userId": "codex", "selectedClass": "Mage"}, "wallet": {"gold": 10}, "materials": {}, "decks": [], "equippedLoadouts": []}
	Game.room = {}
	Game.settlement = {}
	Game.ready_prompt = {}
	Game.busy = false
	Game.hero_class = "Mage"
	ui.screen = "cards"
	ui._codex_ready = true
	var rows: Array = []
	for id in ui.cards:
		var info: Dictionary = ui.cards[id]
		if info.get("is_codex", false):
			rows.append({"cardId": str(id), "unlocked": true, "copyCount": 1, "level": 0, "heroClass": info.get("hero_class")})
	ui.owned = rows
	ui._render()
	var grid := ui._reference.find_child("CardGrid", true, false) as GridContainer
	var first_page: Control = ui._reference
	for frame in range(4): await tree.process_frame
	var mounted := _mounted_count(grid)
	ui._render()
	var cached: bool = ui._reference == first_page
	var suffix := "点击查看详情"
	var tooltip := ""
	if grid != null and grid.get_child_count() > 0 and grid.get_child(0).get_child_count() > 0:
		tooltip = str(grid.get_child(0).get_child(0).tooltip_text)
	var ok: bool = grid != null and grid.get_child_count() == 220 and mounted > 0 and mounted < 220
	ok = ok and cached and tooltip.count(suffix) == 1
	var result := {"ok": ok, "slots": grid.get_child_count() if grid != null else 0, "mounted": mounted, "cached": cached}
	ui.free()
	return result

func _mounted_count(grid: GridContainer) -> int:
	if grid == null: return 0
	var count := 0
	for slot in grid.get_children(): count += slot.get_child_count()
	return count
