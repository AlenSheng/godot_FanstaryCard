extends RefCounted

const ModalScene = preload("res://ui/confirmation_modal.tscn")
const P = preload("res://ui/palette.gd")

func run_test() -> Dictionary:
	var errors: Array[String] = []
	var previous_language := P.language()
	P.set_language("en")
	var host := Control.new()
	host.size = Vector2(1920, 1080)
	var tree := Engine.get_main_loop() as SceneTree
	if tree != null: tree.root.add_child(host)
	var invoked := [false]
	var modal := ModalScene.instantiate()
	host.add_child(modal)
	modal.configure("This deliberately long localized operation description must wrap cleanly without colliding with either action button.", func(): invoked[0] = true)
	var panel := modal.get_node("DialogPanel") as Panel
	var title := panel.get_node("Title") as Label
	var description := panel.get_node("Description") as Label
	var cancel := panel.get_node("CancelButton") as Button
	var confirm := panel.get_node("ConfirmButton") as Button
	if title.text != "Confirm Action" or cancel.text != "Cancel" or confirm.text != "Confirm": errors.append("Default labels must use the active language")
	if cancel.focus_mode != Control.FOCUS_NONE or confirm.focus_mode != Control.FOCUS_NONE: errors.append("Confirmation actions must not draw a keyboard selection frame")
	if description.autowrap_mode == TextServer.AUTOWRAP_OFF or description.max_lines_visible < 4: errors.append("Description must reserve a wrapped multi-line text region")
	if not panel.get_global_rect().encloses(description.get_global_rect()) or not panel.get_global_rect().encloses(cancel.get_global_rect()) or not panel.get_global_rect().encloses(confirm.get_global_rect()): errors.append("All text and actions must remain inside the common panel")
	var panel_style := panel.get_theme_stylebox("panel") as StyleBoxTexture
	var confirm_style := confirm.get_theme_stylebox("normal") as StyleBoxTexture
	var cancel_style := cancel.get_theme_stylebox("normal") as StyleBoxTexture
	if panel_style == null or panel_style.texture == null: errors.append("Confirmation must use the existing common dialog artwork")
	if confirm_style == null or confirm_style.texture == null or cancel_style == null or cancel_style.texture == null: errors.append("Confirmation actions must use existing button artwork")
	confirm.pressed.emit()
	if not invoked[0]: errors.append("Confirm button must invoke its supplied action")
	var info_modal := ModalScene.instantiate()
	host.add_child(info_modal)
	info_modal.configure("Battle details", Callable(), {"info_only": true, "tall": true, "title": "battle_stats_set", "confirm_text": "confirm"})
	var info_panel := info_modal.get_node("DialogPanel") as Panel
	var info_cancel := info_panel.get_node("CancelButton") as Button
	var info_confirm := info_panel.get_node("ConfirmButton") as Button
	var info_backdrop := info_modal.get_node("Backdrop") as Control
	if info_panel.get_node("Title").text != "Battle Stats / Sets" or info_confirm.text != "Confirm": errors.append("Information modal must resolve stable localization keys")
	if info_modal.mouse_filter != Control.MOUSE_FILTER_STOP or info_backdrop.mouse_filter != Control.MOUSE_FILTER_STOP or info_panel.mouse_filter != Control.MOUSE_FILTER_STOP: errors.append("Information modal must block pointer events behind it")
	if info_cancel.visible: errors.append("Information modal must hide the cancel action")
	if info_confirm.position.x != 345.0 or info_confirm.position.y != 426.0: errors.append("Information modal must center its close action")
	if info_panel.size.y != 600.0: errors.append("Tall information modal must reserve the detail layout")
	info_confirm.pressed.emit()
	if info_modal.visible: errors.append("Information modal confirm must close the modal")
	var second_modal := ModalScene.instantiate()
	host.add_child(second_modal)
	second_modal.configure("Battle details", Callable(), {"info_only": true, "tall": true, "title": "battle_stats_set", "confirm_text": "confirm"})
	(second_modal.get_node("DialogPanel/ConfirmButton") as Button).pressed.emit()
	if second_modal.visible: errors.append("Information modal must close on its second opening")
	host.free()
	P.set_language(previous_language)
	return {"ok": errors.is_empty(), "message": "Shared layered confirmation panel, localized wrapping and two sprite-backed actions" if errors.is_empty() else "; ".join(errors)}
