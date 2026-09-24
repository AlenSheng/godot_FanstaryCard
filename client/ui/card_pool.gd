extends Node

const CardView = preload("res://ui/card_view.gd")
const CardDetails = preload("res://ui/card_details.gd")
const BASELINE_CARDS := 50
const MAX_POOL_CARDS := 256
const CREATE_PER_FRAME := 10

var _idle: Array[Button] = []
var _idle_by_id: Dictionary = {}
var _all_cards: Array[Button] = []
var _catalog: Dictionary = {}
var _catalog_ids: Array = []
var _ownership: Dictionary = {}
var _describe: Callable
var _catalog_cursor := 0
var _creation_target := 0
var _trim_pending := false
var _cache_growth_enabled := true

func _exit_tree() -> void:
	# The idle controls are deliberately detached from the scene tree. Free them
	# explicitly when the owner exits so their labels, shaped text and GPU-backed
	# textures do not survive application shutdown.
	clear()

func begin_prewarm(catalog: Dictionary, owned: Array, describe: Callable) -> void:
	_catalog = catalog
	_catalog_ids = CardDetails.sorted_ids(catalog.keys(), catalog)
	_ownership.clear()
	for card in owned:
		if card is Dictionary: _ownership[str(card.get("cardId", ""))] = card
	_describe = describe
	_catalog_cursor = 0
	_trim_pending = false
	_cache_growth_enabled = true
	_creation_target = mini(BASELINE_CARDS, mini(MAX_POOL_CARDS, _catalog_ids.size()))
	set_process(_all_cards.size() < _creation_target)

func _process(_delta: float) -> void:
	var created := 0
	while _all_cards.size() < _creation_target and created < CREATE_PER_FRAME:
		if not _create_from_catalog():
			set_process(false)
			return
		created += 1
	set_process(_all_cards.size() < _creation_target)

func _create_from_catalog() -> bool:
	if _catalog_ids.is_empty(): return false
	var id: String = str(_catalog_ids[_catalog_cursor % _catalog_ids.size()])
	_catalog_cursor += 1
	var info: Dictionary = _catalog.get(id, {})
	var owned: Dictionary = _ownership.get(id, {})
	var is_codex: bool = bool(info.get("is_codex", false))
	var options := {
		"collection": is_codex,
		"copy_count": int(owned.get("copyCount", 0)) if owned.get("unlocked", false) else 0,
		"level": int(owned.get("level", 0)),
	}
	var description := str(_describe.call(id)) if _describe.is_valid() else ""
	var button := CardView.new()
	_configure(button, id, info, description, false, false, options)
	_all_cards.append(button)
	_add_idle(button)
	return true

func acquire(parent: Node, id: String, info: Dictionary, description: String, selected: bool, disabled: bool, options: Dictionary, callback: Callable) -> Button:
	var signature := _signature(id, info, description, selected, options)
	var button := _take_matching_idle(id, signature)
	if button == null and _cache_growth_enabled and _all_cards.size() < MAX_POOL_CARDS:
		button = CardView.new()
		_all_cards.append(button)
	elif button == null and not _idle.is_empty():
		button = _idle.front()
		_remove_idle(button)
	elif button == null:
		# More cards can be visible at once than the cache limit allows.
		button = CardView.new()
		_all_cards.append(button)
	var rebuilt := _configure(button, id, info, description, selected, disabled, options)
	button.set_meta("pool_rebuilt_on_acquire", rebuilt)
	button.name = "CardView"
	button.visible = true
	button.position = Vector2.ZERO
	button.scale = Vector2.ONE
	button.size = Vector2(218, 376)
	button.disabled = disabled
	button.set_meta("sound_cue", "" if options.get("preview", false) else "card_select")
	button.mouse_default_cursor_shape = Control.CURSOR_ARROW if disabled else Control.CURSOR_POINTING_HAND
	button.set_meta("pool_action", callback)
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func _configure(button: Button, id: String, info: Dictionary, description: String, selected: bool, disabled: bool, options: Dictionary) -> bool:
	var signature := _signature(id, info, description, selected, options)
	if button.get_meta("pool_signature", {}) != signature:
		button.disabled = disabled
		button.configure(id, info, description, selected, options)
		button.set_meta("pool_signature", signature)
		button.set_meta("pool_tooltip", button.tooltip_text)
		return true
	else:
		button.tooltip_text = str(button.get_meta("pool_tooltip", ""))
		return false

func _take_matching_idle(id: String, signature: Dictionary) -> Button:
	var candidates: Array = _idle_by_id.get(id, [])
	for button in candidates:
		if button.get_meta("pool_signature", {}) == signature:
			_remove_idle(button)
			return button
	return null

func _add_idle(button: Button) -> void:
	_idle.append(button)
	var id := str(button.get_meta("pool_signature", {}).get("id", ""))
	var candidates: Array = _idle_by_id.get(id, [])
	candidates.append(button)
	_idle_by_id[id] = candidates

func _remove_idle(button: Button) -> void:
	_idle.erase(button)
	var id := str(button.get_meta("pool_signature", {}).get("id", ""))
	var candidates: Array = _idle_by_id.get(id, [])
	candidates.erase(button)
	if candidates.is_empty(): _idle_by_id.erase(id)

func ensure_available(required: int) -> bool:
	var needed := maxi(0, required)
	if _idle.size() >= needed: return true
	if _catalog_ids.is_empty(): return false
	var shortage := needed - _idle.size()
	var pending := maxi(0, _creation_target - _all_cards.size())
	var additional := maxi(0, shortage - pending)
	if additional > 0:
		var batches := int(ceil(float(additional) / float(CREATE_PER_FRAME)))
		_creation_target = mini(MAX_POOL_CARDS, maxi(_creation_target, _all_cards.size() + pending + batches * CREATE_PER_FRAME))
	set_process(true)
	return false

func release(button: Button) -> void:
	if not is_instance_valid(button): return
	if button in _idle: return
	var action: Callable = button.get_meta("pool_action", Callable())
	if action.is_valid() and button.pressed.is_connected(action): button.pressed.disconnect(action)
	if button.has_meta("pool_action"): button.remove_meta("pool_action")
	if button.is_inside_tree(): button.release_focus()
	if button.get_parent() != null: button.get_parent().remove_child(button)
	button.tooltip_text = str(button.get_meta("pool_tooltip", ""))
	button.visible = false
	if _trim_pending and _all_cards.size() > BASELINE_CARDS:
		_free_card(button)
		if _all_cards.size() <= BASELINE_CARDS: _trim_pending = false
	else:
		_add_idle(button)

func release_descendants(root: Node) -> void:
	for child in root.get_children():
		if child is CardView:
			release(child)
		else:
			release_descendants(child)

func trim_to_baseline() -> void:
	_creation_target = mini(_all_cards.size(), BASELINE_CARDS)
	set_process(false)
	_cache_growth_enabled = false
	_trim_pending = _all_cards.size() > BASELINE_CARDS
	while _all_cards.size() > BASELINE_CARDS and not _idle.is_empty():
		_free_card(_idle.front())
	if _all_cards.size() <= BASELINE_CARDS: _trim_pending = false

func _free_card(button: Button) -> void:
	_remove_idle(button)
	_all_cards.erase(button)
	if button.get_parent() != null: button.get_parent().remove_child(button)
	button.free()

func clear() -> void:
	set_process(false)
	_catalog = {}
	_catalog_ids.clear()
	_ownership.clear()
	_describe = Callable()
	_catalog_cursor = 0
	_creation_target = 0
	_trim_pending = false
	_cache_growth_enabled = true
	for button in _all_cards.duplicate(): _free_card(button)
	_idle.clear()
	_idle_by_id.clear()

func _signature(id: String, info: Dictionary, description: String, selected: bool, options: Dictionary) -> Dictionary:
	return {"id": id, "info": info, "description": description, "selected": selected, "options": options}
