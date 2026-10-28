extends Node
func _ready() -> void:call_deferred("_run")
func _run() -> void:
 var P=load("res://ui/palette.gd");var Tips=load("res://ui/tips_overlay.gd");P.set_language("en");get_tree().root.size=Vector2i(1920,1080)
 Game.set_process(false);Game._client_info_socket.close();Game.gateway.set_process(false);Game.gateway.end_session("",false);Sound.set_process(false);Sound.set_music_context("");Sound.stop_all();Sound.stop_music()
 var host=load("res://ui/main.gd").new();var overlay=Tips.new();get_tree().root.add_child(overlay);host.tips_overlay=overlay;Game.settlement={};Game.room={"player":{"phase":"ActionBar"}};host._toast("Duel is not active in this room.")
 var checks={};var text=overlay.label.text;var serial=overlay._serial;var tween_id=overlay._tween.get_instance_id();var broad=overlay.panel.size.x
 await get_tree().create_timer(.35).timeout;Game.room.player.phase="Pvp";overlay.set_viewport_anchor(host._notice_anchor(),host._notice_width_ratio());await get_tree().process_frame
 checks["Combat narrows a running notice"]=overlay.panel.size.x<broad and overlay.panel.size.x<=1920*Tips.COMBAT_MAX_WIDTH_RATIO+.1
 checks["Wrapped notice fits its text instead of cached one-character lines"]=overlay.panel.size.y<120 and overlay.label.get_line_count()==2
 checks["Width change preserves text and serial"]=overlay.label.text==text and overlay._serial==serial
 checks["Width change preserves original tween"]=overlay._tween.get_instance_id()==tween_id
 checks["Running notice remains centered"]=abs((overlay.panel.get_global_transform_with_canvas().origin.x+overlay.panel.size.x*.5)-960)<1
 var offset=overlay.offset;overlay.set_viewport_anchor(host._notice_anchor(),host._notice_width_ratio());checks["Repeated reflow does not accumulate translation"]=overlay.offset==offset
 await get_tree().create_timer(.35).timeout;Game.room.player.phase="ActionBar";overlay.set_viewport_anchor(host._notice_anchor(),host._notice_width_ratio());await get_tree().process_frame
 checks["Leaving combat restores the natural notice width"]=is_equal_approx(overlay.panel.size.x,broad)
 checks["Leaving combat still preserves the same notice lifetime"]=overlay._serial==serial and overlay._tween.get_instance_id()==tween_id
 await get_tree().create_timer(1.45).timeout;checks["Original two-second lifetime is not restarted"]=not overlay.panel.visible and overlay.label.text.is_empty()
 Game.room.player.phase="Pvp";host._toast(text);await get_tree().process_frame;host._toast(text);await get_tree().create_timer(.2).timeout
 var panel_rect:Rect2=overlay.panel.get_global_transform_with_canvas()*Rect2(Vector2.ZERO,overlay.panel.size);var text_rect:Rect2=overlay.label.get_global_transform_with_canvas()*Rect2(Vector2.ZERO,overlay.label.size)
 checks["Consecutive wrapped notices keep text inside their backing"]=panel_rect.grow(.1).encloses(text_rect)
 checks["Consecutive wrapped notices keep compact two-line height"]=overlay.panel.size.y<120 and overlay.label.get_line_count()==2
 host.tips_overlay=null;overlay.free();host.free();Game.room={};Sound.stop_all();Sound.stop_music();await get_tree().create_timer(.35).timeout
 var result={"ok":not checks.values().has(false),"checks":checks,"scope":"Actual overlay, main placement helpers, native timers and layout; no renderer, login, world or human experience"};FileAccess.open(OS.get_environment("PR19_REFLOW_RESULT"),FileAccess.WRITE).store_string(JSON.stringify(result));print(JSON.stringify(result));get_tree().quit(0 if result.ok else 1)
