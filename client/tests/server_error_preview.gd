extends Node

const P = preload("res://ui/palette.gd")
const RemoteCopy = preload("res://ui/remote_copy.gd")
const Gateway = preload("res://network/gateway.gd")
const Proto = preload("res://network/protobuf.gd")
const TipsOverlay = preload("res://ui/tips_overlay.gd")
const RAW_MARKERS: String = "Fire / 装备 / {amount} / \"keep verbatim\""
const CASES: Array[Dictionary] = [
	{"id": "http_unknown_400", "transport": "http", "status": 400, "title": "Unrecognized fixture HTTP title", "key": "server_operation_failed"},
	{"id": "http_invalid_deck", "transport": "http", "status": 400, "title": "Invalid deck", "key": "deck_invalid"},
	{"id": "rt_stale_relic", "transport": "rt", "code": "STALE_RELIC", "key": "relic_changed"},
	{"id": "rt_unknown", "transport": "rt", "code": "UNRECOGNIZED_FIXTURE_CODE", "key": "server_operation_failed"}
]

## Only the autoload's deferred client-info read is stubbed. The separate
## Gateway under test below is an unmodified production Gateway instance.
class OfflineAutoloadGateway extends "res://network/gateway.gd":
	var blocked_requests: int = 0
	func _ready() -> void:
		persist_session = false
		set_process(false)
	func request(_path: String, _method: int = HTTPClient.METHOD_GET, _data: Variant = null, _quiet_statuses: Array = []) -> Dictionary:
		blocked_requests += 1
		return {"ok": false, "status": 0, "data": null, "error": ""}
	func send(_kind: String, _payload: Dictionary = {}, _request_id: String = "") -> bool:
		return false

var _gateway: Gateway
var _offline: OfflineAutoloadGateway
var _tips: TipsOverlay
var _output: String = ""
var _locale: String = ""
var _width: int = 0
var _sequence: int = 0
var _raw_failures: Array[String] = []
var _user_failures: Array[String] = []
var _events: Array[Dictionary] = []
var _checks: Dictionary = {}
var _errors: Array[Dictionary] = []
var _frames: Array[Dictionary] = []
var _screenshots: int = 0

func _ready() -> void:
	get_window().mode = Window.MODE_WINDOWED
	get_window().set_flag(Window.FLAG_NO_FOCUS, true)
	get_window().position = Vector2i.ZERO if OS.get_environment("FANTASYCARD_REVIEW_ISOLATED_DESKTOP") == "1" else Vector2i(-32000, -32000)
	_quiet_autoloads()
	_run.call_deferred()

func _quiet_autoloads() -> void:
	Game.set_process(false)
	Game._client_info_socket.close()
	var original: Node = Game.gateway
	original.set_process(false)
	original.persist_session = false
	original.reconnect_enabled = false
	original.socket.close()
	_offline = OfflineAutoloadGateway.new()
	Game.gateway = _offline
	Game.add_child(_offline)
	original.queue_free()
	Game.platform.set_process(false)
	Sound.persist_settings = false
	Sound._headless_runtime = true
	Sound.set_process(false)
	Sound.set_music_context("")
	Sound.stop_music()
	Sound.stop_all()

func _run() -> void:
	_output = OS.get_environment("FANTASYCARD_ART_EVIDENCE")
	_locale = OS.get_environment("FANTASYCARD_REVIEW_LOCALES")
	_width = OS.get_environment("FANTASYCARD_REVIEW_WIDTHS").to_int()
	var isolated: bool = OS.get_environment("FANTASYCARD_REVIEW_ISOLATED_DESKTOP") == "1"
	if not isolated or _output.is_empty() or _locale not in ["zh-CN", "en", "es"] or _width not in [960, 1280, 1920]:
		print(JSON.stringify({"ok": false, "error": "Use the guarded error UI matrix with one supported locale and width."}))
		get_tree().quit(1)
		return
	if FileAccess.file_exists(_output.path_join("report.json")):
		print(JSON.stringify({"ok": false, "error": "The evidence report already exists; use a new immutable directory."}))
		get_tree().quit(1)
		return
	P.set_language(_locale)
	var expected_window: Vector2i = Vector2i(_width, roundi(float(_width) * 9.0 / 16.0))
	get_window().size = expected_window
	await get_tree().process_frame
	var profile: String = OS.get_environment("APPDATA").replace("\\", "/").to_lower()
	var user_directory: String = OS.get_user_data_dir().replace("\\", "/").to_lower()
	_check("guard/private_desktop_declared", isolated)
	_check("guard/isolated_user_profile", not profile.is_empty() and user_directory.begins_with(profile), user_directory)
	_check("setup/selected_locale", P.language() == _locale, P.language())
	_check("setup/selected_window", get_window().size == expected_window, [get_window().size.x, get_window().size.y])
	var backdrop: ColorRect = ColorRect.new()
	backdrop.name = "ErrorPreviewBackdrop"
	backdrop.color = Color("142d35")
	backdrop.size = get_viewport().get_visible_rect().size
	backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(backdrop)
	_tips = TipsOverlay.new()
	_tips.name = "ProductionTipsOverlay"
	add_child(_tips)
	_gateway = Gateway.new()
	_gateway.name = "ProductionGateway"
	_gateway.persist_session = false
	_gateway.set_process(false)
	add_child(_gateway)
	_gateway.set_process(false)
	_gateway.reconnect_enabled = false
	_gateway.online = true
	_gateway.recovering = false
	_gateway.room_id = ""
	_gateway.current_match_id = ""
	_gateway.last_sequence = 0
	_gateway.socket.close()
	_gateway.failed.connect(_on_raw_failure)
	_gateway.user_failed.connect(_on_user_failure)
	_gateway.event_received.connect(_on_event)
	for mode_value in [{"name": "wide", "ratio": TipsOverlay.MAX_WIDTH_RATIO}, {"name": "combat", "ratio": TipsOverlay.COMBAT_MAX_WIDTH_RATIO}]:
		var mode: Dictionary = mode_value
		var ratio: float = float(mode.ratio)
		var show_tip: Callable = _tips.show_tip.bind(TipsOverlay.VIEWPORT_Y_RATIO, ratio)
		_gateway.user_failed.connect(show_tip)
		for case_value in CASES:
			var case_data: Dictionary = case_value
			await _exercise_case(case_data, str(mode.name), ratio)
		_gateway.user_failed.disconnect(show_tip)
	_check("summary/eight_pngs", _screenshots == 8, _screenshots)
	_check("summary/eight_raw_failures", _raw_failures.size() == 8, _raw_failures.size())
	_check("summary/eight_user_failures", _user_failures.size() == 8, _user_failures.size())
	_check("summary/four_decoded_rt_events", _events.size() == 4, _events.size())
	_check("summary/no_gateway_reconnect_or_persistence", not _gateway.reconnect_enabled and not _gateway.persist_session and _gateway.room_id.is_empty())
	var report: Dictionary = {"ok": _errors.is_empty(), "locale": _locale, "width": _width,
		"expected_frames": 8, "screenshots": _screenshots, "checks": _checks, "errors": _errors, "frames": _frames,
		"raw_failures": _raw_failures, "user_failures": _user_failures, "decoded_rt_events": _events,
		"autoload_http_requests_blocked": _offline.blocked_requests, "actual_game_matches": 0,
		"isolated_user_directory": OS.get_user_data_dir(), "whole_visual_acceptance": false,
		"scope": "Production Gateway failure signals and decoded RT rejection frames shown by the production TipsOverlay at both production width ratios. Synthetic diagnostics, no network requests, no real game match, no animation lifecycle override or whole-language acceptance claim."}
	var file: FileAccess = FileAccess.open(_output.path_join("report.json"), FileAccess.WRITE)
	if file == null:
		print(JSON.stringify({"ok": false, "error": "Unable to save the error preview report."}))
		get_tree().quit(1)
		return
	file.store_string(JSON.stringify(report, "  "))
	file.close()
	print(JSON.stringify(report))
	Sound.stop_all()
	get_tree().quit(0 if bool(report.ok) else 1)

func _exercise_case(case_data: Dictionary, mode: String, ratio: float) -> void:
	var frame_name: String = "%s_%s_%s_%s" % [_locale, _width, mode, str(case_data.id)]
	var raw: String = str(case_data.id) + ": " + RAW_MARKERS
	var raw_before: int = _raw_failures.size()
	var user_before: int = _user_failures.size()
	var events_before: int = _events.size()
	var expected: String = P.localized(str(case_data.key))
	if str(case_data.transport) == "http":
		var problem: Dictionary = {"title": str(case_data.title), "detail": raw, "code": "http_400"}
		_gateway._report_failure(raw, RemoteCopy.http_error(problem, int(case_data.status)))
		_check(frame_name + "/http_problem_preserved", str(problem.detail) == raw and str(problem.title) == str(case_data.title), problem)
	else:
		_sequence += 1
		var proto: Proto = Proto.new()
		var payload_bytes: PackedByteArray = proto.encode("CommandRejectedEvent", {"code": str(case_data.code), "detail": raw})
		_check(frame_name + "/payload_encoded", str(proto.error).is_empty(), str(proto.error))
		var packet: PackedByteArray = proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "error.command_rejected", "sequence": _sequence,
			"request_id": "error-preview-" + str(_sequence), "payload": payload_bytes})
		_check(frame_name + "/envelope_encoded", str(proto.error).is_empty(), str(proto.error))
		_gateway._receive(packet)
		_check(frame_name + "/one_decoded_event", _events.size() == events_before + 1, _events.size() - events_before)
		var event_entry: Dictionary = _events[events_before] if _events.size() > events_before else {}
		var event_payload: Dictionary = event_entry.get("payload", {})
		_check(frame_name + "/rt_payload_detail_verbatim", str(event_entry.get("kind", "")) == "error.command_rejected" and str(event_payload.get("detail", "")) == raw, event_entry)
		_check(frame_name + "/rt_payload_code_preserved", str(event_payload.get("code", "")) == str(case_data.code), event_payload)
		_check(frame_name + "/rt_sequence_advanced", _gateway.last_sequence == _sequence, _gateway.last_sequence)
	await get_tree().create_timer(0.22).timeout
	await get_tree().process_frame
	_check(frame_name + "/one_raw_failure", _raw_failures.size() == raw_before + 1, _raw_failures.size() - raw_before)
	_check(frame_name + "/raw_failure_verbatim", _raw_failures.size() > raw_before and _raw_failures[raw_before] == raw, _raw_failures)
	_check(frame_name + "/one_user_failure", _user_failures.size() == user_before + 1, _user_failures.size() - user_before)
	_check(frame_name + "/localized_user_failure", _user_failures.size() > user_before and _user_failures[user_before] == expected, _user_failures)
	var label: Label = _tips.label
	var panel: PanelContainer = _tips.panel
	var viewport_rect: Rect2 = get_viewport().get_visible_rect()
	var panel_rect: Rect2 = panel.get_global_rect()
	var label_rect: Rect2 = label.get_global_rect()
	var font: Font = label.get_theme_font("font")
	var font_size: int = label.get_theme_font_size("font_size")
	var control_scale: Vector2 = label.get_global_transform().get_scale()
	var pixel_scale: float = float(get_window().size.y) / maxf(1.0, viewport_rect.size.y)
	var effective_font_size: float = float(font_size) * absf(control_scale.y) * pixel_scale
	var missing_glyphs: Array[int] = []
	for index in range(label.text.length()):
		var codepoint: int = label.text.unicode_at(index)
		if codepoint > 32 and not font.has_char(codepoint) and not missing_glyphs.has(codepoint): missing_glyphs.append(codepoint)
	_check(frame_name + "/localized_visible_text", label.text == expected, {"expected": expected, "actual": label.text})
	_check(frame_name + "/glyphs_complete", missing_glyphs.is_empty(), missing_glyphs)
	_check(frame_name + "/complete_label_lines", label.get_line_count() > 0 and label.get_visible_line_count() >= label.get_line_count(), {"lines": label.get_line_count(), "visible_lines": label.get_visible_line_count()})
	_check(frame_name + "/natural_animation_at_full_scale", panel.scale.is_equal_approx(Vector2.ONE), [panel.scale.x, panel.scale.y])
	_check(frame_name + "/panel_visible", panel.is_visible_in_tree() and panel.modulate.a > 0.99)
	_check(frame_name + "/panel_inside_viewport", viewport_rect.grow(0.5).encloses(panel_rect), _rect(panel_rect))
	_check(frame_name + "/label_inside_viewport", viewport_rect.grow(0.5).encloses(label_rect), _rect(label_rect))
	_check(frame_name + "/label_inside_panel", panel_rect.grow(0.5).encloses(label_rect), {"panel": _rect(panel_rect), "label": _rect(label_rect)})
	_check(frame_name + "/effective_font_at_least_12", effective_font_size >= 12.0 - 0.001, effective_font_size)
	_check(frame_name + "/production_width_cap", panel_rect.size.x <= viewport_rect.size.x * ratio + 0.5, {"width": panel_rect.size.x, "maximum": viewport_rect.size.x * ratio})
	var image_path: String = _output.path_join(frame_name + ".png")
	var saved: bool = false
	if not FileAccess.file_exists(image_path):
		RenderingServer.force_draw(false)
		var image: Image = get_viewport().get_texture().get_image()
		_check(frame_name + "/native_png_dimensions", image.get_width() == get_window().size.x and image.get_height() == get_window().size.y, [image.get_width(), image.get_height()])
		var save_result: int = image.save_png(image_path)
		saved = save_result == OK
		if saved: _screenshots += 1
	_check(frame_name + "/png_saved_once", saved, image_path)
	_frames.append({"name": frame_name, "path": image_path, "case": str(case_data.id), "transport": str(case_data.transport),
		"width_ratio": ratio, "raw": raw, "expected_key": str(case_data.key), "text": label.text,
		"font_size": font_size, "effective_font_size": effective_font_size, "pixel_scale": pixel_scale,
		"control_scale": [control_scale.x, control_scale.y], "panel_scale": [panel.scale.x, panel.scale.y],
		"lines": label.get_line_count(), "visible_lines": label.get_visible_line_count(), "missing_glyphs": missing_glyphs,
		"panel_rect": _rect(panel_rect), "label_rect": _rect(label_rect), "viewport_rect": _rect(viewport_rect),
		"checks": _frame_checks(frame_name)})

func _on_raw_failure(message: String) -> void:
	_raw_failures.append(message)

func _on_user_failure(message: String) -> void:
	_user_failures.append(message)

func _on_event(kind: String, payload: Dictionary) -> void:
	_events.append({"kind": kind, "payload": payload.duplicate(true)})

func _check(check_name: String, passed: bool, observed: Variant = null) -> void:
	_checks[check_name] = passed
	if not passed: _errors.append({"check": check_name, "observed": observed})

func _frame_checks(frame_name: String) -> Dictionary:
	var result: Dictionary = {}
	for key in _checks:
		if str(key).begins_with(frame_name + "/"): result[key] = _checks[key]
	return result

func _rect(value: Rect2) -> Array[float]:
	return [value.position.x, value.position.y, value.size.x, value.size.y]
