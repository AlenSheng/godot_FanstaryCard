extends GridContainer

const P = preload("res://ui/palette.gd")
const MAX_REBUILDS_PER_FRAME := 12

var _host: Control
var _scroll: ScrollContainer
var _entries: Array = []
var _slots: Array[Control] = []
var _side := 218.0
var _rebuilding := false
var _sync_scheduled := false
var _waiting_for_pool := false
var _mounted_first := -1
var _mounted_last := -1

static func display_layout(host: Control, maximum_columns: int, authored_side: float, logical_width: float, horizontal_gap: float, minimum_card_pixels: float = 160.0) -> Dictionary:
	var pixel_scale: float = float(host.get_window().size.x) / host.get_viewport().get_visible_rect().size.x
	var columns_for_display: int = clampi(floori((logical_width + horizontal_gap) * pixel_scale / (minimum_card_pixels + horizontal_gap * pixel_scale)), 1, maximum_columns)
	var side_for_display: float = authored_side
	if columns_for_display != maximum_columns or pixel_scale < 1.0:
		side_for_display = maxf(authored_side, floorf((logical_width - horizontal_gap * (columns_for_display - 1)) / columns_for_display))
	return {"columns": columns_for_display, "side": side_for_display}

func _exit_tree() -> void:
	set_process(false)
	if _host == null or not is_instance_valid(_host): return
	for slot in _slots:
		if not is_instance_valid(slot): continue
		for child in slot.get_children():
			if child is Button: _host.release_card(child)

func configure(host: Control, scroll: ScrollContainer, entries: Array, side: float) -> void:
	_rebuilding = true
	clear_cards()
	_host = host
	_scroll = scroll
	_entries = entries
	_side = side
	for entry in _entries:
		var slot := Control.new()
		slot.name = str(entry.get("slot_name", "CardSlot"))
		slot.custom_minimum_size = Vector2(side, side * 376.0 / 218.0)
		slot.mouse_filter = Control.MOUSE_FILTER_PASS
		add_child(slot)
		_slots.append(slot)
	if _entries.is_empty():
		var empty := Label.new()
		empty.text = P.localized_text("没有符合条件的卡牌")
		empty.custom_minimum_size = Vector2(1000, 180)
		empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		add_child(empty)
	var bar := scroll.get_v_scroll_bar()
	if not bar.value_changed.is_connected(_on_scroll_changed): bar.value_changed.connect(_on_scroll_changed)
	_rebuilding = false
	_schedule_sync_visible()

func clear_cards() -> void:
	if _host != null and is_instance_valid(_host):
		for slot in _slots:
			if not is_instance_valid(slot): continue
			for child in slot.get_children():
				if child is Button: _host.release_card(child)
	for child in get_children():
		remove_child(child)
		child.queue_free()
	_slots.clear()
	_entries.clear()
	_mounted_first = -1
	_mounted_last = -1
	_waiting_for_pool = false
	set_process(false)

func _on_scroll_changed(_value: float) -> void:
	if _rebuilding: return
	_schedule_sync_visible()

func _schedule_sync_visible() -> void:
	if _sync_scheduled: return
	_sync_scheduled = true
	call_deferred("_sync_visible")

func _process(_delta: float) -> void:
	if _waiting_for_pool:
		_sync_visible()

func _sync_visible() -> void:
	_sync_scheduled = false
	if _rebuilding: return
	if not is_inside_tree() or is_queued_for_deletion():
		set_process(false)
		return
	if _scroll == null or not is_instance_valid(_scroll) or _host == null or not is_instance_valid(_host):
		set_process(false)
		return
	if _slots.is_empty():
		set_process(false)
		return
	var row_height := _side * 376.0 / 218.0 + get_theme_constant("v_separation")
	var first_row := maxi(0, int(floor(float(_scroll.scroll_vertical) / row_height)) - 1)
	var last_row := int(ceil(float(_scroll.scroll_vertical + _scroll.size.y) / row_height)) + 1
	var first := mini(_slots.size(), first_row * columns)
	var last := mini(_slots.size(), last_row * columns)
	if first == _mounted_first and last == _mounted_last and not _waiting_for_pool:
		return
	# Scroll changes used to scan every slot and touch every mounted card. The
	# grid already knows its old mounted interval, so only recycle the cards that
	# actually left the viewport (including the small row overscan).
	if _mounted_first >= 0:
		for i in range(_mounted_first, _mounted_last):
			if i >= first and i < last: continue
			for child in _slots[i].get_children():
				if child is Button: _host.release_card(child)
	_mounted_first = first
	_mounted_last = last
	var missing := 0
	for i in range(first, last):
		if _slots[i].get_child_count() == 0: missing += 1
	_host.ensure_card_pool(missing)
	var mounted := 0
	var rebuilt := 0
	for i in range(first, last):
		if _slots[i].get_child_count() > 0: continue
		if rebuilt >= MAX_REBUILDS_PER_FRAME or not _host.ensure_card_pool(1): break
		var entry: Dictionary = _entries[i]
		var card: Button = _host._card_button(_slots[i], str(entry.id), entry.callback, bool(entry.get("selected", false)), bool(entry.get("disabled", false)), entry.get("options", {}))
		card.name = str(entry.get("card_name", "Card_" + str(entry.id)))
		card.size = Vector2(218, 376)
		card.scale = Vector2.ONE * _side / 218.0
		if entry.has("tooltip"): card.tooltip_text = P.localized_text(str(entry.tooltip))
		elif entry.has("tooltip_suffix"): card.tooltip_text += P.localized_text(str(entry.tooltip_suffix))
		mounted += 1
		if card.get_meta("pool_rebuilt_on_acquire", false): rebuilt += 1
	_waiting_for_pool = mounted < missing
	set_process(_waiting_for_pool)
