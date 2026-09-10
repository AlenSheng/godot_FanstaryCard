extends ScrollContainer

var interaction_enabled := true
var _held := false
var _dragged := false
var _origin := Vector2.ZERO
var _initial_scroll := Vector2.ZERO
var _pressed_button: BaseButton
var _touch_index := -1
var _suppress_until := -1

func can_activate() -> bool:
	return interaction_enabled and not _dragged and Engine.get_process_frames() > _suppress_until

func _input(event: InputEvent) -> void:
	if not interaction_enabled or not is_visible_in_tree():
		_held = false
		return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			var hovered := get_viewport().gui_get_hovered_control()
			if hovered != self and (hovered == null or not is_ancestor_of(hovered)): return
			# Leave the scroll bar's own thumb dragging to Godot.
			if hovered is ScrollBar: return
			_begin(event.position)
			while hovered != null and hovered != self:
				if hovered is BaseButton:
					_pressed_button = hovered
					break
				hovered = hovered.get_parent() as Control
		elif _held and _touch_index == -1:
			_finish()
	elif event is InputEventMouseMotion and _held and _touch_index == -1:
		_drag(event.position)
	elif event is InputEventScreenTouch:
		if event.pressed and get_global_rect().has_point(event.position):
			_begin(event.position)
			_touch_index = event.index
		elif not event.pressed and _held and event.index == _touch_index:
			_finish()
	elif event is InputEventScreenDrag and _held and event.index == _touch_index:
		_drag(event.position)

func _begin(point: Vector2) -> void:
	_held = true
	_dragged = false
	_touch_index = -1
	_origin = point
	_initial_scroll = Vector2(scroll_horizontal, scroll_vertical)
	_pressed_button = null

func _drag(point: Vector2) -> void:
	var displacement := point - _origin
	if not _dragged and displacement.length() < 12.0: return
	_dragged = true
	if vertical_scroll_mode != SCROLL_MODE_DISABLED: scroll_vertical = int(_initial_scroll.y - displacement.y)
	if horizontal_scroll_mode != SCROLL_MODE_DISABLED: scroll_horizontal = int(_initial_scroll.x - displacement.x)
	get_viewport().set_input_as_handled()

func _finish() -> void:
	if _dragged:
		# A drag must not also activate the card under the release position.
		_suppress_until = Engine.get_process_frames() + 1
		if is_instance_valid(_pressed_button): _pressed_button.set_pressed_no_signal(false)
		get_viewport().set_input_as_handled()
	_held = false
	_dragged = false
	_touch_index = -1
	_pressed_button = null
