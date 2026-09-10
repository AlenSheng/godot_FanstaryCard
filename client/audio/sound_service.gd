extends Node

signal cue_started(cue: String)
signal settings_changed

const CUES := ["ui_click", "card_select", "card_draw", "card_play", "hit_direct", "hit_fire", "hit_water", "hit_wood", "hit_metal", "hit_earth", "heal", "shield", "reward", "purchase", "upgrade", "equip", "potion", "move", "extract_start", "extract_success", "death", "error"]
const MAX_VOICES := 8
const DEFAULT_VOLUME := 0.65
const COOLDOWN_MS := {"ui_click": 55, "card_select": 65, "card_draw": 120, "card_play": 90, "heal": 150, "shield": 150, "error": 600}

var volume := DEFAULT_VOLUME
var muted := false
var settings_path := "user://audio_settings.cfg"
var persist_settings := true
var bind_game_events := true
var bus_name := &"FantasyCard SFX"
var streams: Dictionary = {}
var _voices: Array[AudioStreamPlayer] = []
var _last_played: Dictionary = {}
var _voice_order: Dictionary = {}
var _serial := 0
var _owns_bus := false

func _ready() -> void:
	_load_settings()
	_create_bus()
	for cue in CUES:
		var stream := load("res://assets/audio/%s.wav" % cue) as AudioStream
		if stream != null: streams[cue] = stream
	for index in range(MAX_VOICES):
		var player := AudioStreamPlayer.new()
		player.bus = bus_name
		player.name = "Voice%s" % index
		add_child(player)
		_voices.append(player)
	_apply_mix()
	if bind_game_events:
		Game.sound_requested.connect(play_cue)
		Game.authentication_required.connect(func(_reason): stop_all())
		get_tree().node_added.connect(_node_added)
		_bind_buttons(get_tree().root)

func _create_bus() -> void:
	if AudioServer.get_bus_index(bus_name) >= 0: return
	AudioServer.add_bus()
	var index := AudioServer.bus_count - 1
	AudioServer.set_bus_name(index, bus_name)
	AudioServer.set_bus_send(index, &"Master")
	var limiter := AudioEffectLimiter.new()
	limiter.ceiling_db = -1.0
	limiter.threshold_db = -3.0
	AudioServer.add_bus_effect(index, limiter)
	_owns_bus = true

func play_cue(cue: String) -> bool:
	if muted or volume <= 0.0 or not streams.has(cue) or _voices.is_empty(): return false
	var now := Time.get_ticks_msec()
	if _last_played.has(cue) and now - int(_last_played[cue]) < int(COOLDOWN_MS.get(cue, 100)): return false
	_last_played[cue] = now
	var voice: AudioStreamPlayer = null
	for candidate in _voices:
		if not candidate.playing:
			voice = candidate
			break
	if voice == null:
		# A fixed pool bounds rapid combat bursts; replace the oldest voice.
		voice = _voices[0]
		for candidate in _voices:
			if int(_voice_order.get(candidate, 0)) < int(_voice_order.get(voice, 0)): voice = candidate
	voice.stop()
	voice.stream = streams[cue]
	voice.volume_db = 0.0
	voice.pitch_scale = 1.0
	_serial += 1
	_voice_order[voice] = _serial
	voice.play()
	cue_started.emit(cue)
	return true

func stop_all() -> void:
	for voice in _voices: voice.stop()
	_last_played.clear()

func set_volume(value: float, save: bool = true) -> void:
	volume = clampf(value, 0.0, 1.0)
	_apply_mix()
	if save: save_settings()
	settings_changed.emit()

func set_muted(value: bool) -> void:
	muted = value
	if muted: stop_all()
	_apply_mix()
	save_settings()
	settings_changed.emit()

func _apply_mix() -> void:
	var index := AudioServer.get_bus_index(bus_name)
	if index < 0: return
	AudioServer.set_bus_mute(index, muted or volume <= 0.0)
	AudioServer.set_bus_volume_db(index, linear_to_db(maxf(volume, 0.001)) - 3.0)

func _load_settings() -> void:
	if not persist_settings: return
	var config := ConfigFile.new()
	if config.load(settings_path) != OK: return
	var saved_volume: Variant = config.get_value("sound", "volume", DEFAULT_VOLUME)
	if (saved_volume is float or saved_volume is int) and is_finite(float(saved_volume)):
		volume = clampf(float(saved_volume), 0.0, 1.0)
	var saved_mute: Variant = config.get_value("sound", "muted", false)
	if saved_mute is bool: muted = saved_mute

func save_settings() -> void:
	if not persist_settings: return
	var config := ConfigFile.new()
	config.set_value("sound", "volume", volume)
	config.set_value("sound", "muted", muted)
	config.save(settings_path)

func _node_added(node: Node) -> void:
	if node is BaseButton: _bind_button.call_deferred(weakref(node))

func _bind_buttons(node: Node) -> void:
	if node is BaseButton: _bind_button(weakref(node))
	for child in node.get_children(): _bind_buttons(child)

func _bind_button(reference: WeakRef) -> void:
	var button := reference.get_ref() as BaseButton
	if button == null or button.has_meta("sound_bound"): return
	button.set_meta("sound_bound", true)
	button.pressed.connect(func():
		var current := reference.get_ref() as BaseButton
		if current == null or current.disabled: return
		play_cue(str(current.get_meta("sound_cue", "ui_click")))
	)

func _exit_tree() -> void:
	stop_all()
	if _owns_bus:
		var index := AudioServer.get_bus_index(bus_name)
		if index >= 0: AudioServer.remove_bus(index)
