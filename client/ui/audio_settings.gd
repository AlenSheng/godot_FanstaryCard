extends CanvasLayer

const P = preload("res://ui/palette.gd")
const I18n = preload("res://ui/i18n.gd")
const Art = preload("res://ui/art.gd")
var _toggle: Button
var _popup: PopupPanel
var _mute_button: CheckButton

func _ready() -> void:
	layer = 20
	var overlay := Control.new()
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	overlay.theme = P.theme()
	add_child(overlay)
	_toggle = Button.new()
	_toggle.name = "AudioSettingsButton"
	_toggle.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	_toggle.offset_left = 24
	_toggle.offset_right = 224
	_toggle.offset_top = -54
	_toggle.offset_bottom = -8
	_toggle.add_theme_font_size_override("font_size", 23)
	_toggle.tooltip_text = I18n.t("调整音效音量；F10 快捷静音")
	Art.button(_toggle, "UI/CardCodex/card_codex_action_button_blue.png")
	_toggle.pressed.connect(show_settings)
	overlay.add_child(_toggle)
	Sound.settings_changed.connect(_refresh)
	_refresh()

func _refresh() -> void:
	_toggle.text = I18n.t("音效 · 静音" if Sound.muted or Sound.volume <= 0 else "音效 · %s%%" % roundi(Sound.volume * 100))

func show_settings() -> void:
	if is_instance_valid(_popup):
		_popup.grab_focus()
		return
	_popup = PopupPanel.new()
	_popup.name = "AudioSettingsPopup"
	_popup.theme = P.theme()
	_popup.add_theme_stylebox_override("panel", P.box(P.INK, P.GOLD))
	_popup.window_input.connect(func(event):
		if _mute_shortcut(event): _popup.set_input_as_handled()
	)
	add_child(_popup)
	var column := VBoxContainer.new()
	column.custom_minimum_size = Vector2(590, 330)
	_popup.add_child(column)
	var title := Label.new()
	title.text = I18n.t("音效设置")
	title.add_theme_font_override("font", P.font("title"))
	title.add_theme_font_size_override("font_size", 34)
	title.add_theme_color_override("font_color", P.GOLD)
	column.add_child(title)
	var value := Label.new()
	value.text = I18n.t("音效音量 %s%%" % roundi(Sound.volume * 100))
	value.add_theme_font_override("font", P.font("number"))
	column.add_child(value)
	var slider := HSlider.new()
	slider.name = "SoundVolume"
	slider.min_value = 0
	slider.max_value = 100
	slider.step = 1
	slider.value = roundi(Sound.volume * 100)
	slider.custom_minimum_size.y = 44
	slider.value_changed.connect(func(level):
		Sound.set_volume(float(level) / 100.0, false)
		value.text = I18n.t("音效音量 %s%%" % roundi(level))
	)
	slider.drag_ended.connect(func(changed):
		if changed:
			Sound.save_settings()
			Sound.play_cue("ui_click")
	)
	column.add_child(slider)
	var mute := CheckButton.new()
	_mute_button = mute
	mute.name = "SoundMute"
	mute.text = I18n.t("静音")
	mute.button_pressed = Sound.muted
	mute.toggled.connect(Sound.set_muted)
	column.add_child(mute)
	var sample := Button.new()
	sample.text = I18n.t("试听 · 黄铜与纸牌")
	sample.set_meta("sound_cue", "card_play")
	Art.button(sample, "UI/CardCodex/card_codex_action_button_blue.png")
	column.add_child(sample)
	var back := Button.new()
	back.text = I18n.t("返回")
	Art.button(back, "UI/CardCodex/card_codex_action_button_blue.png")
	back.pressed.connect(_popup.hide)
	column.add_child(back)
	_popup.popup_hide.connect(func():
		Sound.save_settings()
		_popup.queue_free()
	)
	_popup.popup_centered()
	slider.grab_focus()

func _unhandled_key_input(event: InputEvent) -> void:
	if _mute_shortcut(event): get_viewport().set_input_as_handled()

func _mute_shortcut(event: InputEvent) -> bool:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_F10:
		Sound.set_muted(not Sound.muted)
		if is_instance_valid(_mute_button):
			_mute_button.set_pressed_no_signal(Sound.muted)
		return true
	return false
