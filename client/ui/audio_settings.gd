extends CanvasLayer

const P = preload("res://ui/palette.gd")
const Art = preload("res://ui/art.gd")
const ConfirmationModalScene = preload("res://ui/confirmation_modal.tscn")
const GOLD_BUTTON_KEY := "UI/CardCodex/card_codex_action_button_orange.png"
const COMMON_POPUP_PANEL_KEY := "UI/CardCodex/card_codex_dialog_panel_normal.png"
const POPUP_TARGET_SIZE := Vector2(948, 724)
const POPUP_VIEWPORT_MARGIN := Vector2(160, 120)
const SCROLLBAR_RIGHT_SHIFT := 4.0
const SCROLLBAR_CONTENT_GAP := 16
var _toggle: BaseButton
var _popup: PopupPanel
var _mute_button: CheckButton

func _ready() -> void:
	layer = 20
	var overlay := Control.new()
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	overlay.theme = P.theme()
	add_child(overlay)
	_toggle = TextureButton.new()
	_toggle.name = "AudioSettingsButton"
	_toggle.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	_toggle.position = Vector2(-112, 26)
	_toggle.size = Vector2(70, 70)
	_toggle.focus_mode = Control.FOCUS_NONE
	_toggle.ignore_texture_size = true
	_toggle.stretch_mode = TextureButton.STRETCH_KEEP_ASPECT_CENTERED
	_toggle.texture_normal = Art.texture("UI/Hall/settings_button.png")
	_toggle.texture_hover = Art.texture("UI/Hall/settings_button.png")
	_toggle.tooltip_text = P.localized("settings")
	_toggle.pressed.connect(show_settings)
	overlay.add_child(_toggle)
	Sound.settings_changed.connect(_refresh)
	_refresh()

func _refresh() -> void:
	_toggle.tooltip_text = "%s · %s %s%%" % [P.localized("settings"), P.localized("sound_volume"), roundi(Sound.volume * 100)]

func show_settings() -> void:
	if is_instance_valid(_popup):
		if _popup.visible:
			_popup.grab_focus()
			return
		_popup.queue_free()
		_popup = null
	_popup = PopupPanel.new()
	var popup := _popup
	_popup.name = "AudioSettingsPopup"
	_popup.theme = P.theme()
	var panel_style := Art.style(COMMON_POPUP_PANEL_KEY)
	panel_style.set_content_margin(SIDE_RIGHT, panel_style.get_content_margin(SIDE_RIGHT) - SCROLLBAR_RIGHT_SHIFT)
	_popup.add_theme_stylebox_override("panel", panel_style)
	popup.window_input.connect(func(event):
		if _mute_shortcut(event): popup.set_input_as_handled()
	)
	add_child(_popup)
	var popup_size := _settings_popup_size()
	var scroll := ScrollContainer.new()
	scroll.name = "AudioSettingsScroll"
	var padding := Art.COMMON_PANEL_PADDING
	scroll.custom_minimum_size = popup_size - Vector2(padding.x + padding.z - SCROLLBAR_RIGHT_SHIFT, padding.y + padding.w)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_popup.add_child(scroll)
	var content_margin := MarginContainer.new()
	content_margin.name = "SettingsContentMargin"
	content_margin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content_margin.add_theme_constant_override("margin_right", SCROLLBAR_CONTENT_GAP)
	scroll.add_child(content_margin)
	var column := VBoxContainer.new()
	column.name = "SettingsContent"
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content_margin.add_child(column)
	var title := Label.new()
	title.text = P.localized("settings")
	title.add_theme_font_override("font", P.font("title"))
	title.add_theme_font_size_override("font_size", 34)
	title.add_theme_color_override("font_color", P.GOLD)
	column.add_child(title)
	P.fit_control_font(title, P.font("title"), 34)
	var value := Label.new()
	value.text = "%s %s%%" % [P.localized("sound_volume"), roundi(Sound.volume * 100)]
	value.add_theme_font_override("font", P.font("number"))
	column.add_child(value)
	P.fit_control_font(value, P.font("number"), 24)
	var slider := HSlider.new()
	slider.name = "SoundVolume"
	slider.min_value = 0
	slider.max_value = 100
	slider.step = 1
	slider.value = roundi(Sound.volume * 100)
	slider.custom_minimum_size.y = 44
	slider.value_changed.connect(func(level):
		Sound.set_volume(float(level) / 100.0, false)
		value.text = "%s %s%%" % [P.localized("sound_volume"), roundi(level)]
	)
	slider.drag_ended.connect(func(changed):
		if changed:
			Sound.save_settings()
			Sound.play_cue("ui_click")
	)
	column.add_child(slider)
	var music_value := Label.new()
	music_value.text = "%s %s%%" % [P.localized("music_volume"), roundi(Sound.music_volume * 100)]
	music_value.add_theme_font_override("font", P.font("number"))
	column.add_child(music_value)
	P.fit_control_font(music_value, P.font("number"), 24)
	var music_slider := HSlider.new()
	music_slider.name = "MusicVolume"
	music_slider.min_value = 0
	music_slider.max_value = 100
	music_slider.step = 1
	music_slider.value = roundi(Sound.music_volume * 100)
	music_slider.custom_minimum_size.y = 44
	music_slider.value_changed.connect(func(level):
		Sound.set_music_volume(float(level) / 100.0, false)
		music_value.text = "%s %s%%" % [P.localized("music_volume"), roundi(level)]
	)
	music_slider.drag_ended.connect(func(changed):
		if changed:
			Sound.save_settings()
			Sound.play_cue("ui_click")
	)
	column.add_child(music_slider)
	var ambience_value := Label.new()
	ambience_value.text = "%s %s%%" % [P.localized("ambience_volume"), roundi(Sound.ambience_volume * 100)]
	ambience_value.add_theme_font_override("font", P.font("number"))
	column.add_child(ambience_value)
	P.fit_control_font(ambience_value, P.font("number"), 24)
	var ambience_slider := HSlider.new()
	ambience_slider.name = "AmbienceVolume"
	ambience_slider.min_value = 0
	ambience_slider.max_value = 100
	ambience_slider.step = 1
	ambience_slider.value = roundi(Sound.ambience_volume * 100)
	ambience_slider.custom_minimum_size.y = 44
	ambience_slider.value_changed.connect(func(level):
		Sound.set_ambience_volume(float(level) / 100.0, false)
		ambience_value.text = "%s %s%%" % [P.localized("ambience_volume"), roundi(level)]
	)
	ambience_slider.drag_ended.connect(func(changed):
		if changed:
			Sound.save_settings()
			Sound.play_cue("ui_click")
	)
	column.add_child(ambience_slider)
	var mute := CheckButton.new()
	_mute_button = mute
	mute.name = "SoundMute"
	mute.text = P.localized("mute")
	mute.button_pressed = Sound.muted
	mute.toggled.connect(Sound.set_muted)
	column.add_child(mute)
	P.fit_control_font(mute, P.font("body"), 24, 48.0)
	var language_title := Label.new()
	language_title.text = P.localized("language")
	language_title.add_theme_font_override("font", P.font("title"))
	language_title.add_theme_color_override("font_color", P.GOLD)
	column.add_child(language_title)
	P.fit_control_font(language_title, P.font("title"), 24)
	var language := OptionButton.new()
	for code in P.languages(): language.add_item(str(P.languages()[code].get("name", code)), language.item_count)
	language.select(P.languages().keys().find(P.language()))
	language.item_selected.connect(func(index):
		var code: String = P.languages().keys()[index]
		P.set_language(code)
		_refresh()
		_popup.hide()
		Game.changed.emit()
	)
	column.add_child(language)
	P.fit_control_font(language, P.font("body"), 24, 48.0)
	var account_title := Label.new()
	account_title.text = P.localized("account")
	account_title.add_theme_font_override("font", P.font("title"))
	account_title.add_theme_font_size_override("font_size", 26)
	account_title.add_theme_color_override("font_color", P.GOLD)
	column.add_child(account_title)
	P.fit_control_font(account_title, P.font("title"), 26)
	var account := Button.new()
	account.name = "SwitchAccountButton"
	account.text = P.localized("switch_account")
	Art.button(account, GOLD_BUTTON_KEY)
	account.pressed.connect(func():
		_popup.hide()
		Game.logout()
	)
	column.add_child(account)
	P.fit_control_font(account, P.font("title"), 24, 48.0)
	var sample := Button.new()
	sample.text = P.localized("sample_sound")
	sample.set_meta("sound_cue", "card_play")
	Art.button(sample, GOLD_BUTTON_KEY)
	column.add_child(sample)
	P.fit_control_font(sample, P.font("title"), 24, 48.0)
	if _in_battle():
		var exit_battle := Button.new()
		exit_battle.text = P.localized("battle_exit")
		Art.button(exit_battle, GOLD_BUTTON_KEY)
		exit_battle.pressed.connect(_show_battle_abandon_confirmation)
		column.add_child(exit_battle)
		P.fit_control_font(exit_battle, P.font("title"), 24, 48.0)
	var quit_game := Button.new()
	quit_game.name = "QuitGameButton"
	quit_game.text = P.localized("quit_game")
	Art.button(quit_game, GOLD_BUTTON_KEY)
	quit_game.pressed.connect(_show_quit_confirmation)
	column.add_child(quit_game)
	P.fit_control_font(quit_game, P.font("title"), 24, 48.0)
	var back := Button.new()
	back.text = P.localized("back")
	Art.button(back, GOLD_BUTTON_KEY)
	back.pressed.connect(_popup.hide)
	column.add_child(back)
	P.fit_control_font(back, P.font("title"), 24, 48.0)
	popup.popup_hide.connect(func():
		Sound.save_settings()
		if _popup == popup: _popup = null
		popup.queue_free()
	)
	_popup.popup_centered()
	slider.grab_focus()

func _show_quit_confirmation() -> void:
	if get_node_or_null("QuitGameConfirmation") != null: return
	if is_instance_valid(_popup): _popup.hide()
	var dialog := ConfirmationModalScene.instantiate()
	dialog.name = "QuitGameConfirmation"
	add_child(dialog)
	dialog.configure("quit_game_confirmation", _quit_game, {"title": "quit_game"})

func _quit_game() -> void:
	Sound.save_settings()
	Game.gateway.end_session("", false)
	Game.platform.release_ticket()
	get_tree().quit()

func _in_battle() -> bool:
	var phase := str(Game.room.get("player", {}).get("phase", ""))
	return phase in ["Pve", "Pvp"]

func _settings_popup_size() -> Vector2:
	var viewport_size := get_viewport().get_visible_rect().size
	var available_size := viewport_size - POPUP_VIEWPORT_MARGIN
	return Vector2(
		minf(POPUP_TARGET_SIZE.x, maxf(480.0, available_size.x)),
		minf(POPUP_TARGET_SIZE.y, maxf(360.0, available_size.y))
	)

func _show_battle_abandon_confirmation() -> void:
	if not Game.allowed("battle.abandon") or get_node_or_null("BattleAbandonConfirmation") != null: return
	if is_instance_valid(_popup): _popup.hide()
	var dialog := ConfirmationModalScene.instantiate()
	dialog.name = "BattleAbandonConfirmation"
	add_child(dialog)
	dialog.configure(
		P.localized("battle_abandon_warning"),
		func(): Game.command("battle.abandon"),
		{"title": P.localized("battle_abandon_title"), "confirm_text": P.localized("battle_abandon_confirm"), "cancel_text": P.localized("cancel"), "tall": true})

func _unhandled_key_input(event: InputEvent) -> void:
	if _mute_shortcut(event): get_viewport().set_input_as_handled()

func _mute_shortcut(event: InputEvent) -> bool:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_F10:
		Sound.set_muted(not Sound.muted)
		if is_instance_valid(_mute_button):
			_mute_button.set_pressed_no_signal(Sound.muted)
		return true
	return false
