extends Node

const CATALOG = preload("res://data/catalog.json")

func _ready() -> void:
	_run.call_deferred()

func _run() -> void:
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	# Navigation sounds are irrelevant here and can outlive a headless test quit.
	Sound.muted = true
	var owned: Array = []
	for row in CATALOG.data.tables.Cards:
		if not row.get("is_codex", false): continue
		owned.append({"cardId": row.id, "heroClass": row.get("hero_class"), "unlocked": true,
			"copyCount": 1, "level": 0, "version": 1})
	var snapshot := {"player": {"userId": "pool-smoke", "displayName": "Pool", "selectedClass": "Mage"},
		"wallet": {"gold": 1000}, "materials": {}, "cards": owned, "decks": [], "equippedLoadouts": [],
		"inventory": {"equipments": [], "summary": {"capacity": 50, "equipmentCount": 0, "freeSlots": 50}},
		"shop": {"products": []}, "market": []}
	Game.lobby = {}
	var ui: Control = load("res://main.tscn").instantiate()
	get_tree().root.add_child(ui)
	Game.lobby = snapshot
	ui._sync_account_session()
	var errors: Array[String] = []
	if not ui._card_prewarm_started: errors.append("Cards must prewarm when login data arrives after the UI")
	ui._navigate("cards")
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	var codex: GridContainer = ui._reference.find_child("CardGrid", true, false)
	var cached_codex: Control = ui._reference
	if codex == null or codex.get_child_count() != 220: errors.append("Codex must keep all 220 scroll positions")
	elif _mounted(codex) == 0 or _mounted(codex) > 40: errors.append("Codex must mount only visible cards")
	var first_card := ui._reference.find_child("Card_C01", true, false) as Button
	if first_card == null: errors.append("First visible card must be interactive")
	else:
		first_card.pressed.emit()
		if ui._reference.find_child("CardDetails", true, false) == null: errors.append("Pooled cards must still open details")
		var close := ui._reference.find_child("CloseCardDetails", true, false) as Button
		if close != null: close.pressed.emit()
		await get_tree().process_frame
	var codex_scroll := ui._reference.find_child("CodexScroll", true, false) as ScrollContainer
	if codex_scroll != null:
		codex_scroll.scroll_vertical = 2000
		await get_tree().process_frame
		await get_tree().process_frame
		if codex._slots[0].get_child_count() != 0 or _mounted(codex) > 40:
			errors.append("Codex scroll must release offscreen cards")
		codex_scroll.scroll_vertical = 0
		await get_tree().process_frame
		await get_tree().process_frame
		if ui._reference.find_child("Card_C01", true, false) != first_card:
			errors.append("Returning to a loaded card must reuse its configured control")
		var scroll_end := maxi(0, int(codex_scroll.get_v_scroll_bar().max_value - codex_scroll.get_v_scroll_bar().page))
		for offset in range(0, scroll_end + 1, 500):
			codex_scroll.scroll_vertical = offset
			for frame in range(4): await get_tree().process_frame
		codex_scroll.scroll_vertical = scroll_end
		for frame in range(4): await get_tree().process_frame
		codex_scroll.scroll_vertical = 0
		for frame in range(4): await get_tree().process_frame
		if ui._reference.find_child("Card_C01", true, false) != first_card or first_card.get_meta("pool_rebuilt_on_acquire", true):
			errors.append("A fully visited collection must reuse the original card without rebuilding it")
		if ui._card_pool._all_cards.size() > ui._card_pool.MAX_POOL_CARDS:
			errors.append("Scrolling the full catalog exceeded the card cache limit")
	var search := ui._reference.find_child("CodexSearch", true, false) as LineEdit
	if search != null:
		search.text_changed.emit("抽牌")
		await get_tree().process_frame
		if codex.get_child_count() >= 220: errors.append("Filtering must rebuild only matching scroll slots")
		search.text_changed.emit("")
		await get_tree().process_frame
	ui._navigate("deck")
	await get_tree().process_frame
	await get_tree().process_frame
	var deck: GridContainer = ui._reference.find_child("DeckOwnedGrid", true, false)
	if deck == null or deck.get_child_count() != 220: errors.append("Deck builder must keep all owned card positions")
	elif _mounted(deck) == 0 or _mounted(deck) > 24: errors.append("Deck builder must mount only visible cards")
	ui._navigate("hall")
	await get_tree().process_frame
	if ui._card_pool._idle.is_empty(): errors.append("Leaving a card page must return cards to the pool")
	ui._navigate("cards")
	await get_tree().process_frame
	await get_tree().process_frame
	if ui._reference != cached_codex: errors.append("Reopening the codex must reuse its page tree")
	if ui._reference.find_child("Card_C01", true, false) == null: errors.append("Re-entering codex must display cached cards")
	ui.owned[0]["copyCount"] = int(ui.owned[0].get("copyCount", 0)) + 1
	ui._render()
	if ui._reference == cached_codex: errors.append("Changed ownership must invalidate the cached card page")
	Game.lobby = {}
	ui._reset_account_ui()
	await get_tree().process_frame
	if not ui._card_pool._all_cards.is_empty() or not ui._card_page_cache.is_empty() or ui._reference != null:
		errors.append("Account switch must remove the old card page and clear its pool")
	print({"ok": errors.is_empty(), "errors": errors, "idle": ui._card_pool._idle.size()})
	ui.queue_free()
	await get_tree().process_frame
	await get_tree().process_frame
	get_tree().quit(0 if errors.is_empty() else 1)

func _mounted(grid: GridContainer) -> int:
	var count := 0
	for slot in grid.get_children(): count += slot.get_child_count()
	return count
