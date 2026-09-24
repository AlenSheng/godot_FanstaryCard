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
		if not info.get("is_codex", false): continue
		rows.append({"cardId": str(id), "unlocked": true, "copyCount": 1, "level": 0, "heroClass": info.get("hero_class")})
	ui.owned = rows
	var cold := _sample(ui)
	await tree.process_frame
	var warm := _sample(ui)
	await tree.process_frame
	var again := _sample(ui)
	var fresh_ui = load("res://ui/main.gd").new()
	tree.root.add_child(fresh_ui)
	await tree.process_frame
	_arm(fresh_ui, rows)
	var fresh := _sample(fresh_ui)
	await tree.process_frame
	var grid := ui._reference.find_child("CardGrid", true, false) as GridContainer
	var tooltip := ""
	if grid != null and grid.get_child_count() > 0 and grid.get_child(0).get_child_count() > 0:
		tooltip = str(grid.get_child(0).get_child(0).tooltip_text)
	var suffix := "点击查看详情"
	var parked := 0
	for key in ui._card_pool:
		parked += ui._card_pool[key].size()
	var message := "cold render %s us configure %s us acquire %s us creates %s; warm render %s us configure %s us acquire %s us reuses %s; again render %s us configure %s us reuses %s; fresh render %s us configure %s us acquire %s us creates %s; cards %s/%s/%s/%s; parked %s; tooltip hits %s" % [cold.render_us, cold.configure_us, cold.acquire_us, cold.creates, warm.render_us, warm.configure_us, warm.acquire_us, warm.reuses, again.render_us, again.configure_us, again.reuses, fresh.render_us, fresh.configure_us, fresh.acquire_us, fresh.creates, cold.cards, warm.cards, again.cards, fresh.cards, parked, tooltip.count(suffix)]
	print("CODEX ", message)
	var ok: bool = cold.cards == 220 and warm.cards == 220 and again.cards == 220
	ok = ok and cold.creates == 220 and cold.reuses == 0 and cold.configure_us > 0
	ok = ok and warm.creates == 0 and warm.reuses == 220 and warm.configure_us == 0
	ok = ok and again.creates == 0 and again.reuses == 220 and again.configure_us == 0
	ok = ok and parked == 0 and tooltip.count(suffix) == 1
	ok = ok and fresh.cards == 220 and fresh.creates == 220 and fresh.reuses == 0 and fresh.configure_us > 0
	ui.free()
	fresh_ui.free()
	return {"ok": ok, "cold_us": cold.render_us, "warm_us": warm.render_us, "again_us": again.render_us, "fresh_us": fresh.render_us, "cold_configure_us": cold.configure_us, "fresh_configure_us": fresh.configure_us, "warm_configure_us": warm.configure_us, "warm_acquire_us": warm.acquire_us, "message": message}

func _arm(ui: Control, rows: Array) -> void:
	ui.screen = "cards"
	ui._codex_ready = true
	ui.owned = rows

func _sample(ui: Control) -> Dictionary:
	var creates_before: int = ui.card_pool_creates
	var reuses_before: int = ui.card_pool_reuses
	var configure_before: int = ui.card_configure_usec
	var acquire_before: int = ui.card_acquire_usec
	var started := Time.get_ticks_usec()
	ui._render()
	return {
		"render_us": Time.get_ticks_usec() - started,
		"creates": ui.card_pool_creates - creates_before,
		"reuses": ui.card_pool_reuses - reuses_before,
		"configure_us": ui.card_configure_usec - configure_before,
		"acquire_us": ui.card_acquire_usec - acquire_before,
		"cards": _grid_count(ui),
	}

func _grid_count(ui: Control) -> int:
	var grid := ui._reference.find_child("CardGrid", true, false) as GridContainer
	return grid.get_child_count() if grid != null else -1
