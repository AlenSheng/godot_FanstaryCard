extends CanvasLayer

const P = preload("res://ui/palette.gd")
const Art = preload("res://ui/art.gd")
var _popup: PopupPanel
var _language: OptionButton
var _settings_button: Button
var _column: VBoxContainer

func _ready() -> void:
	layer = 30
	var overlay := Control.new()
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	overlay.theme = P.theme()
	add_child(overlay)
	var toggle := Button.new()
	_settings_button = toggle
	toggle.name = "SettingsButton"
	toggle.text = P.localized("settings")
	toggle.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	toggle.offset_left = -250
	toggle.offset_right = -48
	toggle.offset_top = 22
	toggle.offset_bottom = 78
	toggle.mouse_filter = Control.MOUSE_FILTER_STOP
	Art.button(toggle, "UI/CardCodex/card_codex_action_button_blue.png")
	toggle.pressed.connect(show_settings)
	overlay.add_child(toggle)
	I18n.language_changed.connect(_on_language_changed)

func _on_language_changed(_locale: String) -> void:
	_settings_button.text = P.localized("settings")
	if is_instance_valid(_popup):
		_select_current_language()
		_popup.theme = P.theme()
		P.apply_text_direction(_column)
		_refresh_text(_column)

func _popup_size() -> Vector2i:
	var available := Vector2i(get_viewport().get_visible_rect().size) - Vector2i(48, 48)
	return Vector2i(mini(640, available.x), mini(720, available.y))

func _on_popup_hidden(popup: PopupPanel) -> void:
	Sound.save_settings()
	if _popup == popup:
		_popup = null
		_column = null
		_language = null
	popup.queue_free()

func show_settings() -> void:
	if is_instance_valid(_popup):
		_popup.popup_centered(_popup_size())
		return
	_popup = PopupPanel.new()
	_popup.name = "SettingsPopup"
	_popup.theme = P.theme()
	_popup.add_theme_stylebox_override("panel", P.box(P.INK, P.GOLD))
	add_child(_popup)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.custom_minimum_size = Vector2(_popup_size() - Vector2i(24, 24))
	_popup.add_child(scroll)
	var column := VBoxContainer.new()
	_column = column
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(column)
	var title := Label.new()
	title.name = "SettingsTitle"
	title.text = P.localized("settings")
	title.add_theme_font_override("font", P.font("title"))
	title.add_theme_font_size_override("font_size", 36)
	title.add_theme_color_override("font_color", P.GOLD)
	column.add_child(title)
	var language_label := Label.new()
	language_label.text = P.localized("language")
	column.add_child(language_label)
	_language = OptionButton.new()
	_language.name = "LanguageSelector"
	for key in P.languages():
		_language.add_item(I18n.locale_name(key), _language.item_count)
		_language.set_item_metadata(_language.item_count - 1, key)
	_select_current_language()
	_language.item_selected.connect(func(index):
		I18n.set_language(str(_language.get_item_metadata(index)))
		_refresh_text(column)
	)
	column.add_child(_language)
	var audio_title := Label.new()
	audio_title.name = "AudioTitle"
	audio_title.text = P.localized("sound_volume")
	column.add_child(audio_title)
	var slider := HSlider.new()
	slider.name = "Volume"
	slider.min_value = 0
	slider.max_value = 100
	slider.step = 1
	slider.value = roundi(Sound.volume * 100)
	slider.value_changed.connect(func(level): Sound.set_volume(float(level) / 100.0, false))
	column.add_child(slider)
	var mute := CheckButton.new()
	mute.name = "Mute"
	mute.text = P.localized("mute")
	mute.button_pressed = Sound.muted
	mute.toggled.connect(Sound.set_muted)
	column.add_child(mute)
	var logout := Button.new()
	logout.name = "Logout"
	logout.text = P.localized("switch_account")
	Art.button(logout, "UI/CardCodex/card_codex_action_button_orange.png")
	logout.pressed.connect(_logout)
	column.add_child(logout)
	var close := Button.new()
	close.name = "Close"
	close.text = P.localized("back")
	Art.button(close, "UI/CardCodex/card_codex_action_button_blue.png")
	close.pressed.connect(_popup.hide)
	column.add_child(close)
	_popup.popup_hide.connect(_on_popup_hidden.bind(_popup))
	_popup.popup_centered(_popup_size())
	P.apply_text_direction(column)

func _select_current_language() -> void:
	for index in _language.item_count:
		if str(_language.get_item_metadata(index)) == P.language():
			_language.selected = index
			return

func _refresh_text(column: VBoxContainer) -> void:
	for child in column.get_children():
		if child.name == "AudioTitle": child.text = P.localized("sound_volume")
		elif child.name == "Mute": child.text = P.localized("mute")
		elif child.name == "Logout": child.text = P.localized("switch_account")
		elif child.name == "Close": child.text = P.localized("back")
		elif child.name == "SettingsTitle": child.text = P.localized("settings")

func _logout() -> void:
	var confirm := ConfirmationDialog.new()
	confirm.dialog_text = P.localized("switch_account")
	confirm.ok_button_text = P.localized("confirm")
	confirm.cancel_button_text = P.localized("cancel")
	confirm.confirmed.connect(func():
		if is_instance_valid(_popup): _popup.hide()
		Game.logout()
	)
	add_child(confirm)
	confirm.popup_centered()
