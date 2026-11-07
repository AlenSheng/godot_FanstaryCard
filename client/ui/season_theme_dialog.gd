extends RefCounted

const P=preload("res://ui/palette.gd")
const Art=preload("res://ui/art.gd")
const Model=preload("res://ui/season_theme_model.gd")

static func show_dialog(host: Control,theme: Dictionary) -> void:
	if theme.is_empty() or host.get_node_or_null("SeasonThemeInfo")!=null: return
	var modal := Control.new();modal.name="SeasonThemeInfo";modal.z_index=4096
	modal.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT);modal.mouse_filter=Control.MOUSE_FILTER_STOP;host.add_child(modal)
	var overlay := ColorRect.new();overlay.color=Color(0.02,0.05,0.06,0.78);overlay.mouse_filter=Control.MOUSE_FILTER_STOP
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT);modal.add_child(overlay)
	var frame := Panel.new();frame.name="ThemeInfoPanel";frame.mouse_filter=Control.MOUSE_FILTER_STOP
	frame.add_theme_stylebox_override("panel",Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png"))
	frame.size=Vector2(1160,720);frame.position=(host.get_viewport_rect().size-frame.size)*0.5;modal.add_child(frame)
	_label(frame,Model.title(theme),Rect2(64,44,1032,68),34,P.GOLD).name="ThemeInfoTitle"
	_label(frame,P.localized("season_theme_strategy_"+str(theme.element).to_lower()),Rect2(64,124,1032,176),26,P.PAPER).name="ThemeStrategy"
	_label(frame,Model.phases(theme,1),Rect2(64,318,1032,60),26,P.TEAL)
	_label(frame,Model.phases(theme,2),Rect2(64,384,1032,60),26,P.TEAL)
	_label(frame,P.localized("season_theme_terms"),Rect2(64,460,1032,126),24,P.MUTED).name="ThemeBounds"
	var close := Button.new();close.name="ThemeInfoClose";close.text=P.localized("close")
	close.position=Vector2(410,612);close.size=Vector2(340,64);close.add_theme_font_override("font",P.font_for_text(close.text,26));close.add_theme_font_size_override("font_size",26)
	Art.button(close,"UI/CardCodex/card_codex_action_button_blue.png");frame.add_child(close);P.fit_control_font(close,P.font_for_text(close.text,26),26,48)
	close.pressed.connect(modal.queue_free);close.set_meta("sound_cue","ui_cancel")
	var escape := InputEventKey.new();escape.keycode=KEY_ESCAPE;close.shortcut=Shortcut.new();close.shortcut.events=[escape];close.grab_focus()
	var room_id: String=str(Game.room.get("room_id",""));var version: String=str(Game.room.get("config_version",""));var generation: int=Game.gateway.session_generation
	var guard := func():
		if Game.gateway.session_generation!=generation or str(Game.room.get("room_id",""))!=room_id or str(Game.room.get("config_version",""))!=version: modal.queue_free()
	Game.changed.connect(guard)
	modal.tree_exiting.connect(func():
		if Game.changed.is_connected(guard): Game.changed.disconnect(guard))

static func _label(parent: Control,value: String,rect: Rect2,size: int,color: Color) -> Label:
	var label := Label.new();label.text=P.system_display_text(value);label.mouse_filter=Control.MOUSE_FILTER_IGNORE
	label.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART;label.clip_text=true;label.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER;label.vertical_alignment=VERTICAL_ALIGNMENT_CENTER
	label.add_theme_font_override("font",P.font_for_text(label.text,size));label.add_theme_font_size_override("font_size",size);label.add_theme_color_override("font_color",color)
	parent.add_child(label);label.position=rect.position;label.size=rect.size;P.apply_text_direction(label)
	return label
