extends Node

signal cue_started(cue: String)
signal settings_changed

const CUES := [
	"ui_click", "ui_open", "ui_tab", "ui_confirm", "ui_cancel",
	"card_select", "card_draw", "card_play", "battle_start", "battle_target",
	"player_attack", "player_hit", "monster_attack", "monster_hit", "battle_victory",
	"hit_direct", "hit_fire", "hit_water", "hit_wood", "hit_metal", "hit_earth",
	"heal", "shield", "reward", "purchase", "upgrade", "equip", "potion", "move",
	"extract_start", "extract_success", "death", "error"
]
const MUSIC_CONTEXTS := {
	"hall": "Crown_of_Blackened_Glass",
	"battle": "Throne_of_Obsidian",
	"boss_battle": "Throne_of_the_Sentinel",
	"shop": "The_Gilded_Hourglass",
	"victory": "Legendary_Gambit",
	"defeat": "Ink_and_Parchment",
}
const AMBIENCE_CONTEXTS := {"hall": "ambience_hall", "battle": "ambience_battle"}
const MAX_VOICES := 10
const DEFAULT_VOLUME := 0.65
const DEFAULT_MUSIC_VOLUME := 0.58
const DEFAULT_AMBIENCE_VOLUME := 0.42
const MUSIC_FADE_SECONDS := 0.8
const COOLDOWN_MS := {
	"ui_click": 55, "ui_tab": 75, "ui_open": 120, "ui_confirm": 120, "ui_cancel": 150,
	"card_select": 65, "card_draw": 120, "card_play": 90, "battle_target": 100,
	"player_attack": 90, "player_hit": 100, "monster_attack": 120, "monster_hit": 100,
	"battle_start": 700, "battle_victory": 700, "heal": 150, "shield": 150, "error": 600
}

var volume := DEFAULT_VOLUME
var music_volume := DEFAULT_MUSIC_VOLUME
var ambience_volume := DEFAULT_AMBIENCE_VOLUME
var muted := false
var settings_path := "user://audio_settings.cfg"
var persist_settings := true
var bind_game_events := true
var bus_name := &"FantasyCard SFX"
var music_bus_name := &"FantasyCard Music"
var ambience_bus_name := &"FantasyCard Ambience"
var streams: Dictionary = {}
var music_streams: Dictionary = {}
var ambience_streams: Dictionary = {}
var _voices: Array[AudioStreamPlayer] = []
var _music_players: Array[AudioStreamPlayer] = []
var _ambience_players: Array[AudioStreamPlayer] = []
var _last_played: Dictionary = {}
var _voice_order: Dictionary = {}
var _serial := 0
var _owns_buses: Dictionary = {}
var _music_slot := 0
var _ambience_slot := 0
var _music_tween: Tween
var _ambience_tween: Tween
var _headless_runtime := false
var requested_music_context := "hall"
var outcome_music_context := ""
var music_context := ""
var ambience_context := ""

func _ready() -> void:
	_headless_runtime = DisplayServer.get_name().to_lower() == "headless"
	_load_settings()
	_create_bus(bus_name, &"Master", true)
	_create_bus(music_bus_name, &"Master", true)
	_create_bus(ambience_bus_name, &"Master", true)
	for cue in CUES:
		var stream := load("res://assets/audio/%s.wav" % cue) as AudioStream
		if stream != null: streams[cue] = stream
	# The headless autoload used by static validation does not need long-running
	# loop streams. Explicit test instances set bind_game_events=false and still
	# load these maps to exercise the complete mixer path.
	if not _headless_runtime or not bind_game_events:
		for context in MUSIC_CONTEXTS:
			var music_key: String = MUSIC_CONTEXTS[context]
			var music := load("res://assets/audio/%s.mp3" % music_key) as AudioStream
			if music != null: music_streams[context] = music
		for context in AMBIENCE_CONTEXTS:
			var ambience_key: String = AMBIENCE_CONTEXTS[context]
			var ambience := load("res://assets/audio/%s.wav" % ambience_key) as AudioStream
			if ambience != null: ambience_streams[context] = ambience
	for index in range(MAX_VOICES):
		var player := AudioStreamPlayer.new()
		player.bus = bus_name
		player.name = "Voice%s" % index
		add_child(player)
		_voices.append(player)
	for index in range(2):
		var music_player := AudioStreamPlayer.new()
		music_player.bus = music_bus_name
		music_player.name = "MusicVoice%s" % index
		add_child(music_player)
		_music_players.append(music_player)
		var ambience_player := AudioStreamPlayer.new()
		ambience_player.bus = ambience_bus_name
		ambience_player.name = "AmbienceVoice%s" % index
		add_child(ambience_player)
		_ambience_players.append(ambience_player)
	_apply_mix()
	if bind_game_events:
		Game.sound_requested.connect(_handle_sound_request)
		Game.authentication_required.connect(func(_reason):
			stop_all()
			stop_music()
		)
		Game.changed.connect(_sync_context)
		get_tree().node_added.connect(_node_added)
		_bind_buttons(get_tree().root)
		if not _headless_runtime: _sync_context()

func _process(_delta: float) -> void:
	# A process fallback also catches room transitions that happen before the
	# UI emits its next changed signal (for example after a reconnect snapshot).
	if bind_game_events and not _headless_runtime: _sync_context()

func _create_bus(name: StringName, send: StringName, limiter_enabled: bool) -> void:
	if AudioServer.get_bus_index(name) >= 0: return
	AudioServer.add_bus()
	var index := AudioServer.bus_count - 1
	AudioServer.set_bus_name(index, name)
	AudioServer.set_bus_send(index, send)
	if limiter_enabled:
		var limiter := AudioEffectLimiter.new()
		limiter.ceiling_db = -1.0
		limiter.threshold_db = -3.0
		AudioServer.add_bus_effect(index, limiter)
	_owns_buses[name] = true

func _set_loop(stream: AudioStream) -> void:
	if stream is AudioStreamWAV:
		var wav := stream as AudioStreamWAV
		wav.loop_mode = AudioStreamWAV.LOOP_FORWARD
		wav.loop_begin = 0
		wav.loop_end = maxi(1, int(round(wav.get_length() * float(wav.mix_rate))))
	elif stream is AudioStreamMP3:
		(stream as AudioStreamMP3).loop = true

func _is_battle_context() -> bool:
	var phase := str(Game.room.get("player", {}).get("phase", ""))
	return phase in ["Pve", "Pvp"]

func _is_boss_battle() -> bool:
	if not _is_battle_context() or Game.room.has("duel"): return false
	for monster in Game.room.get("pve", {}).get("monsters", []):
		if bool(monster.get("is_boss", false)) or str(monster.get("monster_id", "")) == "annihilation-core": return true
	return false

func _music_context() -> String:
	if MUSIC_CONTEXTS.has(outcome_music_context): return outcome_music_context
	if _is_battle_context(): return "boss_battle" if _is_boss_battle() else "battle"
	return requested_music_context if MUSIC_CONTEXTS.has(requested_music_context) else ""

func _ambience_context() -> String:
	if _is_battle_context(): return "battle"
	return "hall" if not requested_music_context.is_empty() else ""

func set_music_context(context: String) -> void:
	if MUSIC_CONTEXTS.has(context) and context in ["victory", "defeat"]:
		outcome_music_context = context
	else:
		outcome_music_context = ""
	requested_music_context = context if context.is_empty() or MUSIC_CONTEXTS.has(context) else "hall"
	if not _headless_runtime: _sync_context()

func _clear_outcome_music() -> void:
	if outcome_music_context.is_empty(): return
	outcome_music_context = ""
	if requested_music_context in ["victory", "defeat"]: requested_music_context = "hall"
	_sync_context()

func _handle_sound_request(cue: String) -> void:
	match cue:
		"battle_start": _clear_outcome_music()
		"battle_victory", "extract_success": set_music_context("victory")
		"death": set_music_context("defeat")
		"reward", "move", "extract_start": _clear_outcome_music()
	play_cue(cue)

func _sync_context() -> void:
	var music_target := _music_context()
	if music_target != music_context:
		if music_target.is_empty(): _stop_music_tracks()
		else: play_music_for_context(music_target)
	var ambience_target := _ambience_context()
	if ambience_target != ambience_context:
		if ambience_target.is_empty(): _stop_ambience_tracks()
		else: play_ambience_for_context(ambience_target)

func play_music_for_context(context: String) -> bool:
	if not music_streams.has(context): return false
	var stream: AudioStream = music_streams[context]
	if context == music_context:
		var active := _music_players[_music_slot] if not _music_players.is_empty() else null
		if active != null and active.playing: return true
	if _music_players.is_empty(): return false
	if is_instance_valid(_music_tween): _music_tween.kill()
	_set_loop(stream)
	var incoming_index := 1 - _music_slot
	var incoming: AudioStreamPlayer = _music_players[incoming_index]
	var outgoing: AudioStreamPlayer = _music_players[_music_slot]
	incoming.stop()
	incoming.stream = stream
	incoming.volume_db = -80.0
	incoming.play()
	music_context = context
	_music_slot = incoming_index
	var tween := create_tween().set_parallel(true)
	_music_tween = tween
	tween.tween_property(incoming, "volume_db", _music_db(), MUSIC_FADE_SECONDS)
	if outgoing.playing: tween.tween_property(outgoing, "volume_db", -80.0, MUSIC_FADE_SECONDS)
	tween.chain().tween_callback(func():
		if is_instance_valid(outgoing) and outgoing != incoming: outgoing.stop()
	)
	return true

func play_ambience_for_context(context: String) -> bool:
	if not ambience_streams.has(context) or _ambience_players.is_empty(): return false
	var stream: AudioStream = ambience_streams[context]
	if context == ambience_context and _ambience_players[_ambience_slot].playing: return true
	if is_instance_valid(_ambience_tween): _ambience_tween.kill()
	_set_loop(stream)
	var incoming_index := 1 - _ambience_slot
	var incoming: AudioStreamPlayer = _ambience_players[incoming_index]
	var outgoing: AudioStreamPlayer = _ambience_players[_ambience_slot]
	incoming.stop()
	incoming.stream = stream
	incoming.volume_db = -80.0
	incoming.play()
	ambience_context = context
	_ambience_slot = incoming_index
	var tween := create_tween().set_parallel(true)
	_ambience_tween = tween
	tween.tween_property(incoming, "volume_db", _ambience_db(), MUSIC_FADE_SECONDS)
	if outgoing.playing: tween.tween_property(outgoing, "volume_db", -80.0, MUSIC_FADE_SECONDS)
	tween.chain().tween_callback(func():
		if is_instance_valid(outgoing) and outgoing != incoming: outgoing.stop()
	)
	return true

func stop_music() -> void:
	_stop_music_tracks()
	_stop_ambience_tracks()

func _stop_music_tracks() -> void:
	if is_instance_valid(_music_tween): _music_tween.kill()
	_music_tween = null
	for player in _music_players:
		player.stop()
		player.stream = null
	music_context = ""

func _stop_ambience_tracks() -> void:
	if is_instance_valid(_ambience_tween): _ambience_tween.kill()
	_ambience_tween = null
	for player in _ambience_players:
		player.stop()
		player.stream = null
	ambience_context = ""

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
	for voice in _voices:
		voice.stop()
		voice.stream = null
	_last_played.clear()

func set_volume(value: float, save: bool = true) -> void:
	volume = clampf(value, 0.0, 1.0)
	_apply_mix()
	if save: save_settings()
	settings_changed.emit()

func set_music_volume(value: float, save: bool = true) -> void:
	music_volume = clampf(value, 0.0, 1.0)
	for player in _music_players:
		if player.playing: player.volume_db = _music_db()
	_apply_mix()
	if save: save_settings()
	settings_changed.emit()

func set_ambience_volume(value: float, save: bool = true) -> void:
	ambience_volume = clampf(value, 0.0, 1.0)
	for player in _ambience_players:
		if player.playing: player.volume_db = _ambience_db()
	_apply_mix()
	if save: save_settings()
	settings_changed.emit()

func set_muted(value: bool) -> void:
	muted = value
	if muted: stop_all()
	_apply_mix()
	save_settings()
	settings_changed.emit()

func _music_db() -> float:
	return linear_to_db(maxf(music_volume, 0.001)) - 3.0

func _ambience_db() -> float:
	return linear_to_db(maxf(ambience_volume, 0.001)) - 3.0

func _apply_mix() -> void:
	var sfx_index := AudioServer.get_bus_index(bus_name)
	if sfx_index >= 0:
		AudioServer.set_bus_mute(sfx_index, muted or volume <= 0.0)
		AudioServer.set_bus_volume_db(sfx_index, linear_to_db(maxf(volume, 0.001)) - 3.0)
	var music_index := AudioServer.get_bus_index(music_bus_name)
	if music_index >= 0:
		AudioServer.set_bus_mute(music_index, muted or music_volume <= 0.0)
		AudioServer.set_bus_volume_db(music_index, _music_db())
	var ambience_index := AudioServer.get_bus_index(ambience_bus_name)
	if ambience_index >= 0:
		AudioServer.set_bus_mute(ambience_index, muted or ambience_volume <= 0.0)
		AudioServer.set_bus_volume_db(ambience_index, _ambience_db())

func _load_settings() -> void:
	if not persist_settings: return
	var config := ConfigFile.new()
	if config.load(settings_path) != OK: return
	var saved_volume: Variant = config.get_value("sound", "volume", DEFAULT_VOLUME)
	if (saved_volume is float or saved_volume is int) and is_finite(float(saved_volume)):
		volume = clampf(float(saved_volume), 0.0, 1.0)
	var saved_music: Variant = config.get_value("sound", "music_volume", DEFAULT_MUSIC_VOLUME)
	if (saved_music is float or saved_music is int) and is_finite(float(saved_music)):
		music_volume = clampf(float(saved_music), 0.0, 1.0)
	var saved_ambience: Variant = config.get_value("sound", "ambience_volume", DEFAULT_AMBIENCE_VOLUME)
	if (saved_ambience is float or saved_ambience is int) and is_finite(float(saved_ambience)):
		ambience_volume = clampf(float(saved_ambience), 0.0, 1.0)
	var saved_mute: Variant = config.get_value("sound", "muted", false)
	if saved_mute is bool: muted = saved_mute

func save_settings() -> void:
	if not persist_settings: return
	var config := ConfigFile.new()
	config.set_value("sound", "volume", volume)
	config.set_value("sound", "music_volume", music_volume)
	config.set_value("sound", "ambience_volume", ambience_volume)
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
		var cue := str(current.get_meta("sound_cue", "ui_click"))
		if not cue.is_empty(): play_cue(cue)
	)

func _exit_tree() -> void:
	stop_all()
	stop_music()
	# Release imported streams and player references before the autoload is
	# torn down; this also keeps headless validation free of leaked audio refs.
	streams.clear()
	music_streams.clear()
	ambience_streams.clear()
	_voice_order.clear()
	_voices.clear()
	_music_players.clear()
	_ambience_players.clear()
	for name in _owns_buses:
		var index := AudioServer.get_bus_index(name)
		if index >= 0: AudioServer.remove_bus(index)
