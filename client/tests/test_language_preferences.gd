extends RefCounted

const P = preload("res://ui/palette.gd")

class QuietMain extends "res://ui/main.gd":
	func _ready() -> void: set_process(false)
	func _process(_delta: float) -> void: pass
	func _notification(_what: int) -> void: pass
	func _exit_tree() -> void: pass

func run_test() -> Dictionary:
	var supported := ["zh-CN", "en", "es", "fr", "pt", "id", "hi", "ar", "ru", "ja", "ko"]
	var checks := {}
	var cases := [["ja", "ko_KR", "ja"], ["", "ja_JP", "ja"], ["", "ko-KR", "ko"],
		["", "zh_Hant_TW", "zh-CN"], ["", "en_GB", "en"], ["", "pt_BR", "pt"],
		["", "in_ID", "id"], ["invalid", "ar_SA", "ar"], ["", "de_DE", "en"], ["", "C", "en"]]
	for row in cases:
		checks["preference/" + str(row)] = P.resolve_preferred_language(row[0], row[1], supported) == row[2]
	var saved := {"language": P.language(), "lobby": Game.lobby, "room": Game.room, "settlement": Game.settlement,
		"ready": Game.ready_prompt, "token": Game.gateway.token, "busy": Game.busy,
		"recovery": Game._settlement_recovery_match_id, "command_recovery": Game._command_recovery_context}
	var host := QuietMain.new()
	Game.lobby = {}; Game.room = {}; Game.settlement = {}; Game.ready_prompt = {}
	Game.gateway.token = ""; Game.busy = false; Game._settlement_recovery_match_id = ""; Game._command_recovery_context = {}
	checks["login/offline_selector_available"] = host._can_show_login_language()
	var other := "ja" if P.language() != "ja" else "ko"
	Game.busy = true
	host._select_login_language(other)
	checks["login/queued_selection_during_login_is_ignored"] = P.language() == saved.language
	Game.busy = false
	Game.gateway.token = "preference-test-authenticated"
	host._select_login_language(other)
	checks["session/authenticated_selection_is_ignored"] = not host._can_show_login_language() and P.language() == saved.language
	Game.gateway.token = ""
	Game.lobby = {"player": {}}
	host._select_login_language(other)
	checks["session/hall_selection_is_ignored"] = not host._can_show_login_language() and P.language() == saved.language
	Game.lobby = {}
	host._select_login_language(other)
	var file := ConfigFile.new()
	checks["login/selection_uses_production_handler_and_saves"] = P.language() == other and file.load(P.LANGUAGE_SETTINGS_PATH) == OK and str(file.get_value("ui", "language", "")) == other
	Game.lobby = saved.lobby; Game.room = saved.room; Game.settlement = saved.settlement; Game.ready_prompt = saved.ready
	Game.gateway.token = saved.token; Game.busy = saved.busy; Game._settlement_recovery_match_id = saved.recovery; Game._command_recovery_context = saved.command_recovery
	P.set_language(saved.language)
	host.free()
	return {"ok": not checks.values().has(false), "checks": checks,
		"scope": "System locale mapping, saved preference priority and actual Main login/authentication guards. Isolated test profile only; no network or real login."}
