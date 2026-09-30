extends "res://tests/ui_style_audit.gd"

var button_metrics: Array[Dictionary] = []
var pixel_checks: Array[Dictionary] = []

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	await get_tree().create_timer(0.5).timeout
	for locale in ["zh-CN", "en"]:
		Palette.set_language(locale)
		$UI.theme = Palette.theme()
		for resolution in [Vector2i(1920, 1080), Vector2i(1280, 720), Vector2i(960, 540)]:
			get_window().size = resolution
			await get_tree().process_frame
			await _mail_labels("%s_%s" % [locale, resolution.x])
	Palette.set_language(prior_language)
	var report := {"ok": audit_errors.is_empty(), "source_sha": OS.get_environment("FANTASYCARD_SOURCE_SHA"),
		"screenshots": captures.size(), "captures": captures, "checks": checks, "errors": audit_errors,
		"button_metrics": button_metrics, "pixel_checks": pixel_checks,
		"limitations": "Native Godot offline fixture. No mail claim/delete server commands. Pixel regression compares native button rendering with truncation disabled at identical size/font."}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify({"ok": report.ok, "screenshots": captures.size(), "checks": checks.size(), "errors": audit_errors}))
	get_tree().quit(0 if report.ok else 1)

func _mail_labels(suffix: String) -> void:
	_reset()
	$UI.screen = "hall"
	Game.mail = {"unreadCount": 0, "items": [
		{"id": "labels-unclaimed", "title": "Available reward · 可领取", "body": "Long runtime body / 运行时正文\n".repeat(35), "read": true, "claimed": false, "attachments": [{"kind": "Gold", "amount": 500}]},
		{"id": "labels-claimed", "title": "Claimed reward · 已领取", "body": "Already claimed / 已领取", "read": true, "claimed": true, "attachments": [{"kind": "Gold", "amount": 100}]}
	]}
	$UI._render()
	$UI._reference._mail()
	await _take("mail_labels_normal_" + suffix, false)
	await _assert_buttons(suffix)
	var scroll: ScrollContainer = $UI._reference.find_child("MailDetailScroll", true, false)
	scroll.scroll_vertical = 100000
	await _take("mail_labels_bottom_" + suffix, false)
	_check_audit(scroll.scroll_vertical > 0, "body scroll reaches bottom " + suffix)
	var claim: Button = $UI._reference.find_child("MailRow_labels-unclaimed", true, false).get_node("MailClaim")
	get_viewport().set_disable_input(false)
	var motion := InputEventMouseMotion.new()
	motion.position = claim.get_global_rect().get_center()
	get_viewport().push_input(motion, true)
	await _take("mail_labels_hover_" + suffix, false)
	_check_audit(claim.get_draw_mode() == BaseButton.DRAW_HOVER, "native hover " + suffix)
	var down := InputEventMouseButton.new()
	down.position = motion.position
	down.button_index = MOUSE_BUTTON_LEFT
	down.pressed = true
	get_viewport().push_input(down, true)
	await _take("mail_labels_pressed_" + suffix, false)
	_check_audit(claim.get_draw_mode() == BaseButton.DRAW_PRESSED, "native pressed " + suffix)
	# Release away from the economic action, then restore fixture-only input.
	var away := InputEventMouseMotion.new()
	away.position = Vector2(10, 10)
	get_viewport().push_input(away, true)
	down = InputEventMouseButton.new()
	down.position = away.position
	down.button_index = MOUSE_BUTTON_LEFT
	get_viewport().push_input(down, true)
	get_viewport().set_disable_input(true)
	$UI.set_meta("mail_selected_id", "labels-claimed")
	$UI._reference._refresh_mail_detail($UI._reference.get_node("MailModal"))
	await _take("mail_labels_claimed_" + suffix, false)
	claim = $UI._reference.find_child("MailRow_labels-claimed", true, false).get_node("MailClaim")
	_check_audit(claim.disabled and claim.text == Palette.localized_text("已领取"), "claimed disabled runtime label " + suffix)
	var old: Control = $UI._reference.get_node("MailModal")
	old.queue_free()
	await get_tree().process_frame
	$UI._reference._mail()
	await _take("mail_labels_reopen_" + suffix, false)
	_check_audit($UI._reference.find_children("MailModal", "Control", true, false).size() == 1, "one reopened modal " + suffix)
	await _assert_buttons("reopen_" + suffix)

func _assert_buttons(suffix: String) -> void:
	var modal: Control = $UI._reference.get_node("MailModal")
	var buttons: Array[Button] = []
	for candidate in modal.find_children("*", "Button", true, false):
		var node := candidate as Button
		if node.text.is_empty(): continue
		buttons.append(node)
		var typeface := node.get_theme_font("font")
		var font_size := node.get_theme_font_size("font_size")
		var style := node.get_theme_stylebox("disabled" if node.disabled else "normal")
		var available := node.size.x - style.get_minimum_size().x
		var measured := typeface.get_string_size(node.text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, font_size).x
		var fits := measured <= available + 0.5
		button_metrics.append({"capture": suffix, "node": str(node.get_path()), "text": node.text,
			"font_resource": typeface.resource_path, "font_size": font_size, "measured_width": measured,
			"available_width": available, "rect": str(node.get_global_rect()), "disabled": node.disabled, "fits": fits})
		_check_audit(fits, "full themed text fits %s %s %s" % [suffix, node.get_path(), node.text])
		_check_audit(font_size >= 14, "readable minimum font %s %s" % [suffix, node.get_path()])
	# Compare real pixels with ellipsis disabled; no font/geometry change.
	RenderingServer.force_draw(false)
	var trimmed := get_viewport().get_texture().get_image()
	var modes: Array[int] = []
	for node in buttons:
		modes.append(node.text_overrun_behavior)
		node.text_overrun_behavior = TextServer.OVERRUN_NO_TRIMMING
	await get_tree().process_frame
	RenderingServer.force_draw(false)
	var untrimmed := get_viewport().get_texture().get_image()
	var changed := 0
	var transform := get_viewport().get_stretch_transform()
	for node in buttons:
		var rect := Rect2i(transform * node.get_global_rect()).intersection(Rect2i(Vector2i.ZERO, trimmed.get_size()))
		if trimmed.get_region(rect).get_data() != untrimmed.get_region(rect).get_data(): changed += 1
	for index in range(buttons.size()): buttons[index].text_overrun_behavior = modes[index]
	pixel_checks.append({"capture": suffix, "buttons": buttons.size(), "buttons_with_pixel_difference": changed})
	_check_audit(changed == 0, "native pixels unchanged without ellipsis " + suffix)
