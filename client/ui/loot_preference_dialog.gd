extends RefCounted

const P=preload("res://ui/palette.gd")
const Art=preload("res://ui/art.gd")

static func show_dialog(host: Control) -> void:
	if host.get_node_or_null("LootPreferenceInfo")!=null: return
	var modal := Control.new()
	modal.name="LootPreferenceInfo"
	modal.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	modal.mouse_filter=Control.MOUSE_FILTER_STOP
	modal.z_index=4096
	host.add_child(modal)
	var overlay := ColorRect.new()
	overlay.color=Color(0.02,0.05,0.06,0.78)
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter=Control.MOUSE_FILTER_STOP
	modal.add_child(overlay)
	var frame := Panel.new()
	frame.name="LootPreferencePanel"
	frame.add_theme_stylebox_override("panel",Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png"))
	frame.size=Vector2(1040,500)
	frame.position=(host.get_viewport_rect().size-frame.size)*0.5
	frame.mouse_filter=Control.MOUSE_FILTER_STOP
	modal.add_child(frame)
	_add_label(frame,P.localized("season_loot_preference_title"),Rect2(64,42,912,56),32,P.GOLD)
	_add_label(frame,P.localized("season_loot_preference_hint"),Rect2(64,120,912,228),26,P.PAPER)
	var close := Button.new()
	close.name="PreferenceClose"
	close.text=P.localized("close")
	close.position=Vector2(350,390);close.size=Vector2(340,64)
	close.add_theme_font_override("font",P.font_for_text(close.text,26))
	close.add_theme_font_size_override("font_size",26)
	Art.button(close,"UI/CardCodex/card_codex_action_button_blue.png")
	close.pressed.connect(modal.queue_free)
	close.set_meta("sound_cue","ui_cancel")
	var escape := InputEventKey.new();escape.keycode=KEY_ESCAPE
	close.shortcut=Shortcut.new();close.shortcut.events=[escape]
	frame.add_child(close);P.apply_text_direction(close)
	close.grab_focus()

static func _add_label(parent: Control,value: String,rect: Rect2,size: int,color: Color) -> void:
	var label := Label.new()
	label.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
	label.clip_text=true
	label.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment=VERTICAL_ALIGNMENT_CENTER
	label.mouse_filter=Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_override("font",P.font_for_text(value,size))
	label.add_theme_font_size_override("font_size",size)
	label.add_theme_color_override("font_color",color)
	label.text=value
	parent.add_child(label)
	label.position=rect.position;label.size=rect.size
	P.apply_text_direction(label)
