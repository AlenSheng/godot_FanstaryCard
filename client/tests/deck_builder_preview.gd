extends Node

const P = preload("res://ui/palette.gd")

var failures: Array[String] = []
var output := "res://evidence/deck_builder"

func _ready() -> void:
	var evidence_directory := OS.get_environment("FANTASYCARD_ART_EVIDENCE")
	if not evidence_directory.is_empty(): output = evidence_directory
	Sound.persist_settings = false
	Sound.stop_all()
	Sound.set_music_context("")
	Sound.stop_music()
	Sound._headless_runtime = true
	Sound.set_process(false)
	get_viewport().set_disable_input(true)
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.persist_session = false
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	Game.gateway.token = ""
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
	Game.lobby.cards = $UI.owned
	$UI._sync_account_session()
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
	_check(not $UI._reference.find_child("SaveDeck", true, false).disabled, "Incomplete drafts must keep Save enabled so clicking it can show the local tip")
	$UI._reference.find_child("SaveDeck", true, false).pressed.emit()
	await _settle()
	_check(not Game.busy, "Incomplete drafts must be rejected locally without starting a server save")
	_check($UI.toast_label.text == P.localized("deck_requires_twenty"), "Incomplete drafts need a localized local tip")
	await _show_owned_card(initial[0])
	var selected_card: Button = $UI._reference.find_child("DeckCard_" + initial[0], true, false)
	_check(selected_card != null and selected_card.get_node_or_null("SelectedIndicator") != null, "Cards already in the draft need a selected treatment")
	if selected_card != null:
		var draft_size_before_duplicate: int = $UI.deck_draft.size()
		selected_card.pressed.emit()
		await _settle()
		_check($UI.deck_draft.size() == draft_size_before_duplicate, "Clicking an already selected card must not duplicate it")
		_check($UI.toast_label.text == P.localized("card_already_in_deck"), "Clicking an already selected card needs a localized tip")
	await _show_owned_card(incompatible)
	var incompatible_card: Button = $UI._reference.find_child("DeckCard_" + incompatible, true, false)
	_check(incompatible_card != null and not incompatible_card.disabled, "Other-class cards stay clickable so they can explain why they cannot be added")
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
	var draft_before_locale: Array = $UI.deck_draft.duplicate()
	for locale in ["en", "zh-CN", "en"]:
		var settings := $UI.get_node("AudioSettings")
		settings.show_settings()
		await _settle()
		var language: OptionButton = settings._popup.find_children("*", "OptionButton", true, false)[0]
		language.item_selected.emit(P.languages().keys().find(locale))
		await _settle()
		_check(P.language() == locale, "The actual settings language callback must apply " + locale)
		_check($UI.deck_draft == draft_before_locale, "Language changes must preserve the unsaved deck")
		await _show_owned_card(str(draft_before_locale[0]))
		var localized_card: Button = $UI._reference.find_child("DeckCard_" + str(draft_before_locale[0]), true, false)
		var badge: Label = localized_card.get_node("SelectedIndicator") if localized_card != null else null
		_check(badge != null and badge.text == P.localized_text("已选"), "Pooled selected-card text must refresh for " + locale)
		await _capture("deck_locale_%s_%s" % [locale, str(Time.get_ticks_usec())])
	var report := {"ok": failures.is_empty(), "failures": failures}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	Sound.stop_all()
	Sound.set_music_context("")
	Sound.stop_music()
	await get_tree().create_timer(0.35).timeout
	get_tree().quit(0 if failures.is_empty() else 1)

func _owned(id: String, info: Dictionary) -> Dictionary:
	return {"cardId": id, "heroClass": info.get("hero_class"), "unlocked": true, "copyCount": 1, "level": 0, "version": 1}

func _show_owned_card(id: String) -> void:
	var grid: GridContainer = $UI._reference.find_child("DeckOwnedGrid", true, false)
	var scroll := $UI._reference.find_child("DeckOwnedScroll", true, false) as ScrollContainer
	if grid == null or scroll == null: return
	for index in range(grid.get_child_count()):
		if grid.get_child(index).name != "OwnedSlot_" + id: continue
		var target_slot: Control = grid.get_child(index)
		scroll.scroll_vertical = roundi(target_slot.position.y)
		for frame in range(4): await get_tree().process_frame
		return

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
