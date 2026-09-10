extends Node

var failures: Array = []
var output := "res://evidence/codex"
var screenshot_count := 0

func _ready() -> void:
	var evidence_directory := OS.get_environment("FANTASYCARD_CODEX_EVIDENCE")
	if not evidence_directory.is_empty(): output = evidence_directory
	# Fixture setup uses signal activation; desktop input must not change the selected card.
	get_viewport().set_disable_input(true)
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.persist_session = false
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	_run.call_deferred()

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	Game.lobby = {"player": {"userId": "codex-preview"}, "materials": {"warriorSoul": 300, "priestSoul": 80, "mageSoul": 120, "guardianSoul": 60}, "wallet": {"gold": 9999}, "decks": []}
	Game.room = {}
	Game.settlement = {}
	Game.ready_prompt = {}
	Game.busy = false
	$UI.screen = "cards"
	$UI._codex_ready = true
	$UI.owned = []
	for id in $UI.cards:
		var info: Dictionary = $UI.cards[id]
		if not info.is_codex: continue
		var owned: bool = info.source == "Initial" or (info.source == "Class" and info.quality == "White")
		var kind: String = "WarriorSoul" if info.hero_class == null else str(info.hero_class) + "Soul"
		$UI.owned.append({"cardId": id, "heroClass": info.hero_class, "unlocked": owned, "copyCount": 1 if owned else 0, "level": 0, "version": 1, "craftCost": 10 if info.hero_class == null else 12, "dismantleRefund": 2 if info.hero_class == null else 3, "currencyKind": kind, "upgradeSoulSpent": 0, "canDismantle": owned})
	await _capture("collection")
	_check($UI._reference.find_child("CardGrid", true, false).get_child_count() == 200, "Collection must include all 200 cards")
	for kind in ["PriestSoul", "MageSoul", "GuardianSoul", "WarriorSoul"]:
		_check($UI._reference.find_child("Material_" + kind, true, false) != null, "Missing material " + kind)
	var missing_id := "GW08"
	var card: Button = $UI._reference.find_child("Card_" + missing_id, true, false)
	_check(card != null and not card.disabled and card.material != null, "Unowned card must be gray and clickable")
	if card == null:
		_finish()
		return
	card.pressed.emit()
	_check($UI._codex_card == missing_id, "Card activation must select the requested card")
	await _capture("craft", false)
	var craft_button: Button = $UI._reference.find_child("CraftCard", true, false)
	_check(craft_button != null, "Unowned click must open craft dialog")
	if craft_button == null:
		_finish()
		return
	var return_button: Button = $UI._reference.find_child("CloseCardDetails", true, false)
	var details_panel: Control = $UI._reference.find_child("DetailsPanel", true, false)
	_check(return_button.text == "返回", "Dialog return label must be consistent")
	_check(details_panel.get_global_rect().encloses(return_button.get_global_rect()), "Dialog return button must stay inside its panel")
	_check(not craft_button.disabled, "Sufficient material must enable craft")
	_check($UI._reference.find_child("DetailCard", true, false).material == null, "Unowned preview must be in color")
	Game.lobby.materials[$UI._owned_card(missing_id).currencyKind.left(1).to_lower() + $UI._owned_card(missing_id).currencyKind.substr(1)] = 0
	$UI._render()
	_check($UI._reference.find_child("CraftCard", true, false).disabled, "Insufficient material must disable craft")
	$UI._codex_card = "MAG-07"
	await _capture("dismantle")
	_check($UI._reference.find_child("DismantleCard", true, false) != null, "Owned click must open dismantle dialog")
	_check($UI._reference.find_child("DetailCard", true, false).get_node_or_null("ClassBadge") != null, "Class card requires its own badge")
	$UI._owned_card("MAG-07")["canDismantle"] = false
	$UI._render()
	_check($UI._reference.find_child("DismantleCard", true, false).disabled, "Saved deck copy must not be dismantled")
	$UI._owned_card("MAG-07")["canDismantle"] = true
	$UI.deck_draft = ["MAG-07"]
	$UI._render()
	_check($UI._reference.find_child("DismantleCard", true, false).disabled, "Unsaved draft must protect its required copy")
	_check($UI._reference.find_child("CodexSearch", true, false).focus_mode == Control.FOCUS_NONE, "Modal must prevent keyboard focus in background")
	$UI.deck_draft = []
	$UI._codex_card = ""
	$UI._render()
	await get_tree().process_frame
	await get_tree().process_frame
	get_viewport().set_disable_input(false)
	await _drag_check()
	get_viewport().set_disable_input(true)
	$UI._quality = "Green"
	$UI._codex_scroll = 0
	$UI._render()
	_check($UI._reference.find_child("CardGrid", true, false).get_child_count() == 49, "Green filter must contain 49 cards")
	$UI._quality = ""
	$UI._search = "抽牌"
	$UI._render()
	var results: int = $UI._reference.find_child("CardGrid", true, false).get_child_count()
	_check(results > 0 and results < 200, "Search must match effect descriptions")
	$UI._search = ""
	$UI.edit_mode = true
	$UI.deck_draft = ["C01", "C02", "MAG-01"]
	await _capture("deck")
	$UI._codex_card = "PRI-01"
	$UI._render()
	_check($UI._reference.find_child("AddCardToDeck", true, false).disabled, "Other class card cannot enter current deck")
	$UI._codex_card = ""
	$UI.edit_mode = false
	get_window().size = Vector2i(960, 540)
	await _capture("collection_960")
	$UI._codex_card = missing_id
	await _capture("craft_960")
	_finish()

func _finish() -> void:
	var report := {"ok": failures.is_empty(), "fixture_only": true, "screenshots": screenshot_count, "failures": failures}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	get_tree().quit(0 if failures.is_empty() else 1)

func _drag_check() -> void:
	var scroll: ScrollContainer = $UI._reference.find_child("CodexScroll", true, false)
	var origin := Vector2(130, 510)
	var motion := InputEventMouseMotion.new()
	motion.position = origin
	Input.parse_input_event(motion)
	await get_tree().process_frame
	var down := InputEventMouseButton.new()
	down.button_index = MOUSE_BUTTON_LEFT
	down.pressed = true
	down.position = origin
	Input.parse_input_event(down)
	await get_tree().process_frame
	motion = InputEventMouseMotion.new()
	motion.position = origin - Vector2(0, 220)
	motion.relative = Vector2(0, -220)
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(motion)
	await get_tree().process_frame
	var up := InputEventMouseButton.new()
	up.button_index = MOUSE_BUTTON_LEFT
	up.position = motion.position
	Input.parse_input_event(up)
	await get_tree().process_frame
	_check(scroll.scroll_vertical >= 180, "Dragging must scroll the card grid")
	_check($UI._codex_card.is_empty(), "Dragging must not accidentally open card details")
	await _capture("scrolled", false)
	await get_tree().process_frame
	motion = InputEventMouseMotion.new()
	motion.position = Vector2(130, 510)
	Input.parse_input_event(motion)
	await get_tree().process_frame
	down.position = motion.position
	Input.parse_input_event(down)
	await get_tree().process_frame
	up.position = motion.position
	Input.parse_input_event(up)
	await get_tree().process_frame
	_check(not $UI._codex_card.is_empty(), "Short click after dragging must still open details")
	var escape := InputEventKey.new()
	escape.keycode = KEY_ESCAPE
	escape.pressed = true
	Input.parse_input_event(escape)
	await get_tree().process_frame
	_check($UI._codex_card.is_empty(), "Escape must close details")
	scroll = $UI._reference.find_child("CodexScroll", true, false)
	var before_scroll := scroll.scroll_vertical
	var touch := InputEventScreenTouch.new()
	touch.index = 0
	touch.position = Vector2(300, 710)
	touch.pressed = true
	Input.parse_input_event(touch)
	await get_tree().process_frame
	var touch_drag := InputEventScreenDrag.new()
	touch_drag.index = 0
	touch_drag.position = Vector2(300, 490)
	touch_drag.relative = Vector2(0, -220)
	Input.parse_input_event(touch_drag)
	await get_tree().process_frame
	touch.pressed = false
	touch.position = touch_drag.position
	Input.parse_input_event(touch)
	await get_tree().process_frame
	_check(scroll.scroll_vertical > before_scroll, "Touch drag must scroll the card grid")
	_check($UI._codex_card.is_empty(), "Touch drag must not open card details")

func _capture(label: String, rebuild: bool = true) -> void:
	if rebuild: $UI._render()
	await get_tree().process_frame
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	for node in $UI._reference.find_children("*", "Label", true, false):
		if node.is_visible_in_tree() and not node.text.is_empty():
			_check(node.get_visible_line_count() > 0, label + ": no visible text line: " + node.text.left(40))
	var save_error := get_viewport().get_texture().get_image().save_png(output + "/" + label + ".png")
	_check(save_error == OK, "Screenshot save failed: " + label)
	if save_error == OK: screenshot_count += 1

func _check(value: bool, message: String) -> void:
	if not value: failures.append(message)
