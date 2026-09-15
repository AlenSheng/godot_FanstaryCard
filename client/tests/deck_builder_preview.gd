extends Node

var failures: Array[String] = []
var output := "res://evidence/deck_builder"

func _ready() -> void:
	get_viewport().set_disable_input(true)
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.persist_session = false
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	_run.call_deferred()

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	Game.hero_class = "Mage"
	Game.lobby = {"player": {"userId": "deck-preview", "selectedClass": "Mage"}, "materials": {}, "wallet": {"gold": 9999}, "decks": []}
	Game.room = {}
	Game.settlement = {}
	Game.ready_prompt = {}
	Game.busy = false
	var eligible: Array[String] = []
	var incompatible := ""
	$UI.owned = []
	var by_quality := {"White": [], "Green": [], "Blue": [], "Purple": [], "Orange": []}
	for id in $UI.cards:
		var info: Dictionary = $UI.cards[id]
		if not info.get("is_codex", false): continue
		var hero: Variant = info.get("hero_class")
		if hero == null or hero == "Mage":
			by_quality[str(info.get("quality", "White"))].append(id)
		elif hero != null and hero != "Mage" and incompatible.is_empty():
			incompatible = id
	for quality in ["White", "Green", "Blue", "Purple", "Orange"]:
		for id in by_quality[quality].slice(0, 6):
			eligible.append(id)
			$UI.owned.append(_owned(id, $UI.cards[id]))
	$UI.owned.append(_owned(incompatible, $UI.cards[incompatible]))
	var initial: Array = eligible.slice(0, 3)
	Game.lobby.decks = [{"heroClass": "Mage", "cardIds": initial, "version": 1}]
	$UI.screen = "deck"
	$UI._codex_ready = true
	await $UI._navigate("deck")
	await _settle()
	_check($UI._reference.find_child("DeckBuilderSearch", true, false) != null, "Deck builder must reuse search")
	_check($UI._reference.find_child("DeckFilter_All", true, false) != null, "Deck builder must reuse quality filters")
	_check($UI._reference.find_child("DeckOwnedScroll", true, false) is ScrollContainer, "Owned cards need a vertical scroll area")
	var grid: Control = $UI._reference.find_child("DeckOwnedGrid", true, false)
	_check(grid != null and grid.get_child_count() == $UI.owned.size(), "Only owned cards should appear on the left")
	_check($UI._reference.find_children("DeckSlot_*", "Button", true, false).size() == 20, "Deck must always render exactly 20 fixed slots")
	_check($UI._reference.find_children("DeckEmpty_*", "Label", true, false).size() == 17, "Unfilled deck slots need gray placeholders")
	_check($UI._reference.find_child("DeckCardEffect_01", true, false) != null, "Filled rows need a short effect layer")
	_check($UI._reference.find_child("DeckRowBackground_01", true, false) != null, "Deck row background must be a separate layer")
	_check($UI._reference.find_child("DeckCard_" + incompatible, true, false).disabled, "Other-class owned cards stay visible but cannot be added")
	get_window().size = Vector2i(1920, 1080)
	await _capture("deck_builder_1920")
	$UI._reference.find_child("AutoBuildDeck", true, false).pressed.emit()
	await _settle()
	_check($UI.deck_draft.size() == 20, "Auto build should fill all 20 slots when enough cards are available")
	var unique := {}
	for id in $UI.deck_draft: unique[id] = true
	_check(unique.size() == 20, "Auto build must not duplicate cards")
	var general_orange := 0
	var class_orange := 0
	for id in $UI.deck_draft:
		var info: Dictionary = $UI.cards[id]
		if info.get("quality") == "Orange":
			if info.get("hero_class") == null: general_orange += 1
			else: class_orange += 1
	_check(general_orange <= 1 and class_orange <= 1, "Auto build must preserve both Orange-card limits")
	_check($UI._reference.find_children("DeckEmpty_*", "Label", true, false).is_empty(), "A full deck must have no empty placeholders")
	_check(not $UI._reference.find_child("SaveDeck", true, false).disabled, "A valid 20-card deck can be saved")
	await _capture("deck_builder_full_1920")
	get_window().size = Vector2i(960, 540)
	await _capture("deck_builder_960")
	var report := {"ok": failures.is_empty(), "failures": failures}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	get_tree().quit(0 if failures.is_empty() else 1)

func _owned(id: String, info: Dictionary) -> Dictionary:
	return {"cardId": id, "heroClass": info.get("hero_class"), "unlocked": true, "copyCount": 1, "level": 0, "version": 1}

func _settle() -> void:
	await get_tree().process_frame
	await get_tree().process_frame

func _capture(label: String) -> void:
	await _settle()
	if DisplayServer.get_name() == "headless": return
	var error := get_viewport().get_texture().get_image().save_png(output + "/" + label + ".png")
	_check(error == OK, "Screenshot failed: " + label)

func _check(value: bool, message: String) -> void:
	if not value: failures.append(message)
