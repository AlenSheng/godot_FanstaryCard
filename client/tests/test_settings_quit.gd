extends SceneTree

const P = preload("res://ui/palette.gd")
var checks := {}

func _initialize() -> void: _run.call_deferred()

func _run() -> void:
	var game := root.get_node("Game")
	game.set_process(false)
	game.gateway.persist_session = false
	game.gateway.end_session("", false)
	game.gateway.set_process(false)
	game.gateway.accept_session("quit-fixture", "2099-01-01T00:00:00Z", "quit-user")
	game.gateway.reconnect_enabled = true
	game.platform._ticket_pending = true
	game.platform._ticket_handle = 1
	root.get_node("Sound").persist_settings = false
	var settings: Node = load("res://ui/audio_settings.gd").new()
	root.add_child(settings)
	for locale in ["zh-CN", "en"]:
		P.set_language(locale)
		for phase in ["", "Pve"]:
			game.room = {} if phase.is_empty() else {"player": {"phase": phase}, "allowed_actions": ["battle.abandon"]}
			settings.show_settings()
			var button: Button = settings._popup.find_child("QuitGameButton", true, false)
			checks[locale + "/" + phase + ": quit button is enabled and localized"] = button != null and not button.disabled and button.text == P.localized("quit_game") and button.text != "quit_game"
			button.pressed.emit()
			var dialog: Control = settings.get_node("QuitGameConfirmation")
			checks[locale + "/" + phase + ": quit first opens a localized confirmation"] = dialog.visible and dialog.get_node("DialogPanel/Title").text == P.localized("quit_game") and dialog.get_node("DialogPanel/Description").text == P.localized("quit_game_confirmation") and dialog.get_node("DialogPanel/ConfirmButton").text == P.localized("confirm") and dialog.get_node("DialogPanel/CancelButton").text == P.localized("cancel")
			checks[locale + "/" + phase + ": opening confirmation keeps the session alive"] = game.gateway.token == "quit-fixture" and game.gateway.reconnect_enabled and game.platform._ticket_pending
			button.pressed.emit()
			checks[locale + "/" + phase + ": repeated click reuses the same confirmation"] = settings.get_node("QuitGameConfirmation") == dialog
			dialog.get_node("DialogPanel/CancelButton").pressed.emit()
			await process_frame
			checks[locale + "/" + phase + ": cancel closes confirmation and keeps playing"] = settings.get_node_or_null("QuitGameConfirmation") == null and game.gateway.token == "quit-fixture" and game.gateway.reconnect_enabled and game.platform._ticket_pending
	settings.show_settings()
	settings._popup.find_child("QuitGameButton", true, false).pressed.emit()
	var cancel_key := InputEventKey.new()
	cancel_key.keycode = KEY_ESCAPE
	cancel_key.pressed = true
	settings.get_node("QuitGameConfirmation")._unhandled_key_input(cancel_key)
	await process_frame
	checks["Escape cancels quitting without ending the session"] = settings.get_node_or_null("QuitGameConfirmation") == null and game.gateway.token == "quit-fixture" and game.platform._ticket_pending
	settings.show_settings()
	var quit_button: Button = settings._popup.find_child("QuitGameButton", true, false)
	quit_button.pressed.emit()
	settings.get_node("QuitGameConfirmation/DialogPanel/ConfirmButton").pressed.emit()
	checks["confirm quit releases the session and Steam ticket"] = game.gateway.token.is_empty() and not game.gateway.reconnect_enabled and not game.platform._ticket_pending and game.platform._ticket_handle == 0
	var report := {"ok": not checks.values().has(false), "checks": checks, "scope": "actual settings confirmation cancel and accept; accept exits this isolated Godot process"}
	print(JSON.stringify(report))
	P.clear_runtime_fonts()
	if not report.ok: quit(1)
