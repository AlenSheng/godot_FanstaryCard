extends Control

const P = preload("res://ui/palette.gd")
const RemoteCopy = preload("res://ui/remote_copy.gd")
const Art = preload("res://ui/art.gd")
const CardView = preload("res://ui/card_view.gd")
const CardPool = preload("res://ui/card_pool.gd")
const DeckBuilder = preload("res://ui/deck_builder_view.gd")
const ReferenceUI = preload("res://ui/reference_ui.gd")
const ConfirmationModalScene = preload("res://ui/confirmation_modal.tscn")
const BoundedBar = preload("res://ui/bounded_bar.gd")
const EquipmentDetails = preload("res://ui/equipment_details.gd")
const EquipmentCompareDialog = preload("res://ui/equipment_compare_dialog.gd")
const InventoryView = preload("res://ui/inventory_view.gd")
const CardDetails = preload("res://ui/card_details.gd")
const BattleDetails = preload("res://ui/battle_details.gd")
const AudioSettings = preload("res://ui/audio_settings.gd")
const LoginLanguageSelector = preload("res://ui/login_language_selector.gd")
const TipsOverlay = preload("res://ui/tips_overlay.gd")
const LayeredBackdrop = preload("res://ui/layered_backdrop.gd")
const CatalogIndex = preload("res://data/catalog_index.gd")
const CellIndex = preload("res://ui/cell_index.gd")
const UI_CONFIG = preload("res://data/ui_config.json")
const RANDOM_NAMES_PATH := "res://data/random_names.json"
const CLOUD_SERVER_URL := "https://www.relicbound.cn"
const LOCAL_SERVER_URL := "http://127.0.0.1:5080"
const LOGIN_VIDEO_PATH := "res://assets/backgrounds/relicbound_login_ambient.ogv"
const MEMORY_PROBE_INTERVAL := 3.0
const MEMORY_TRIM_COOLDOWN_MSEC := 30000
const MEMORY_REDLINE_MIN_FREE_BYTES := 256 * 1024 * 1024
const MEMORY_REDLINE_RATIO := 0.10
var screen := "hall"
var content: VBoxContainer
var root_column: VBoxContainer
var status_label: Label
var toast_label: Label
var tips_overlay: CanvasLayer
var cards: Dictionary = {}
var owned: Array = []:
	set(value):
		owned = value
		_owned_by_id.clear()
		_owned_index_ready = false
var _owned_by_id: Dictionary = {}
var _owned_index_ready := false
var _card_text_cache: Dictionary = {}
var inventory: Dictionary = {}
var shop: Dictionary = {}
var listings: Array = []
var deck_draft: Array = []
var gear_draft: Array = []
var bag_tier := "Free"
var potion_count := 0
var edit_mode := false
var screen_loading := false
var _render_pending := false
var _left_pointer_down := false
var _pointer_render_context: Array = []
var _combat_feedback_context: Array = []
var mail_modal_lock := false
var _midlayer_seen: Dictionary = {}
var _login_name := ""
var _session_generation: int = -1
var _search := ""
var _combat_panels: Dictionary = {}
var _backdrop: Control
var _background_video: VideoStreamPlayer
var _background_shade: ColorRect
var _login_video_available := false
var _reference: Control
var _reference_screen := ""
var _card_page_cache: Dictionary = {}
var _card_page_cache_keys: Dictionary = {}
var _card_pool: Node
var _card_prewarm_started := false
var _memory_probe_elapsed := 0.0
var _last_memory_trim_msec := -MEMORY_TRIM_COOLDOWN_MSEC
var _quality := ""
var _enhance_item := ""
var _market_item := ""
var _shop_inventory_ready := false
var _market_price := 100
var _view_cell := ""
var _codex_card := ""
var _codex_scroll := 0
var _codex_deck_scroll := 0
var _deck_builder_scroll := 0
var _equipment_scroll := 0
var _shop_scroll := 0
var _shop_purchase_product_id := ""
var _codex_ready := false
var _codex_mutating := false
var _enhancement_quote: Dictionary = {}
var _enhancement_quote_key := ""
var _game_title: Label
var _login_version_label: Label
var _login_language_selector: LoginLanguageSelector
var _draw_charge_visual := 0.0
var _draw_charge_authoritative := 0.0
var _draw_charge_anchor_msec := 0
var _draw_charge_interval := 4.0
var _draw_charge_room_key := ""
var _draw_charge_revision := -1
var _draw_charge_initialized := false

func _ready() -> void:
	theme = P.theme()
	cards = CatalogIndex.cards()
	if not Game.gateway.local_account_name.is_empty(): _login_name = Game.gateway.local_account_name
	if _login_name.is_empty(): _login_name = _random_login_name()
	_session_generation = Game.gateway.session_generation
	_card_pool = CardPool.new()
	_card_pool.name = "CardPool"
	add_child(_card_pool)
	Game.changed.connect(_schedule_render)
	Game.notice.connect(_toast)
	Game.player_data_invalidated.connect(_refresh_after_admin_update)
	Game.cache_changed.connect(_on_cache_changed)
	Game.authentication_required.connect(_show_ban_dialog)
	Game.combat_feedback.connect(_feedback)
	get_window().size_changed.connect(_on_card_window_size_changed)
	_build_shell()
	var audio_settings := AudioSettings.new()
	audio_settings.name = "AudioSettings"
	add_child(audio_settings)
	_login_language_selector = LoginLanguageSelector.new()
	_login_language_selector.name = "LoginLanguageSelector"
	_login_language_selector.header_guard = status_label
	_login_language_selector.z_index = 100
	_login_language_selector.language_selected.connect(_select_login_language)
	add_child(_login_language_selector)
	_sync_account_session()
	_render()

func _process(_delta: float) -> void:
	_update_draw_charge_visual()
	_memory_probe_elapsed += _delta
	if _memory_probe_elapsed >= MEMORY_PROBE_INTERVAL:
		_memory_probe_elapsed = 0.0
		_check_memory_redline()

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_WINDOW_FOCUS_OUT:
		_left_pointer_down = false
		_pointer_render_context.clear()
		if _render_pending: _render.call_deferred()
	if what == NOTIFICATION_OS_MEMORY_WARNING and is_instance_valid(_card_pool):
		_trim_card_pool_for_memory(true)

func _exit_tree() -> void:
	if is_instance_valid(_card_pool): _card_pool.clear()
	_card_page_cache.clear()
	_card_page_cache_keys.clear()
	CardView.clear_material_cache()
	Art.clear_texture_cache()
	P.clear_runtime_fonts()

func _check_memory_redline() -> void:
	if not is_instance_valid(_card_pool): return
	var memory: Dictionary = OS.get_memory_info()
	var physical := int(memory.get("physical", -1))
	var free := int(memory.get("free", -1))
	if physical <= 0 or free < 0: return
	var redline := maxi(MEMORY_REDLINE_MIN_FREE_BYTES, int(float(physical) * MEMORY_REDLINE_RATIO))
	if free <= redline: _trim_card_pool_for_memory()

func _trim_card_pool_for_memory(force: bool = false) -> void:
	if not is_instance_valid(_card_pool): return
	var now := Time.get_ticks_msec()
	if not force and now - _last_memory_trim_msec < MEMORY_TRIM_COOLDOWN_MSEC: return
	_last_memory_trim_msec = now
	for page in _card_page_cache.keys():
		if _card_page_cache[page] != _reference: _discard_card_page(str(page))
	_card_pool.trim_to_baseline()
	Art.clear_texture_cache()

func _card_page_key(page: String) -> int:
	return hash([page, P.language(), get_window().size, _quality, _search, _codex_ready, _codex_mutating,
		Game.busy, Game.hero_class, Game.connection, owned, deck_draft, Game.deck(),
		Game.lobby.get("materials", {}), Game.lobby.get("wallet", {})])

func _on_card_window_size_changed() -> void:
	if screen in ["cards", "deck"] and not Game.lobby.is_empty() and Game.room.is_empty() and Game.settlement.is_empty():
		_schedule_render()

func _set_card_page_cache_key(page: String) -> void:
	if is_instance_valid(_card_page_cache.get(page)):
		_card_page_cache_keys[page] = _card_page_key(page)

func _free_reference_view(view: Control) -> void:
	if not is_instance_valid(view): return
	if is_instance_valid(_card_pool): _card_pool.release_descendants(view)
	if view.get_parent() != null: view.get_parent().remove_child(view)
	view.queue_free()

func _discard_card_page(page: String) -> void:
	var view: Control = _card_page_cache.get(page) as Control
	_card_page_cache.erase(page)
	_card_page_cache_keys.erase(page)
	if view == _reference:
		_reference = null
		_reference_screen = ""
	_free_reference_view(view)

func _clear_card_page_cache() -> void:
	for page in _card_page_cache.keys(): _discard_card_page(str(page))

func _park_or_free_reference() -> void:
	if not is_instance_valid(_reference):
		_reference = null
		_reference_screen = ""
		return
	if _reference_screen in ["cards", "deck"] and _card_page_cache.get(_reference_screen) == _reference:
		var details := _reference.get_node_or_null("CardDetails")
		if _reference_screen == "cards" and details != null and not details.is_queued_for_deletion():
			_discard_card_page(_reference_screen)
		else:
			_reference.visible = false
			_reference = null
			_reference_screen = ""
		return
	_free_reference_view(_reference)
	_reference = null
	_reference_screen = ""

func _restore_card_page_scroll(page: String, view: Control) -> void:
	var scroll_name := "CodexScroll" if page == "cards" else "DeckOwnedScroll"
	var scroll := view.find_child(scroll_name, true, false) as ScrollContainer
	if scroll != null:
		scroll.scroll_vertical = _codex_scroll if page == "cards" else _deck_builder_scroll

func _build_shell() -> void:
	var backdrop := LayeredBackdrop.new()
	_backdrop = backdrop
	add_child(backdrop)
	var background_video := VideoStreamPlayer.new()
	_background_video = background_video
	background_video.name = "LoginAmbientVideo"
	background_video.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	background_video.expand = true
	background_video.loop = true
	background_video.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(background_video)
	var video_stream := load(LOGIN_VIDEO_PATH) as VideoStream
	if video_stream != null:
		background_video.stream = video_stream
		background_video.autoplay = true
		background_video.play()
		_login_video_available = true
	var background_shade := ColorRect.new()
	_background_shade = background_shade
	background_shade.name = "LoginAmbientShade"
	background_shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	background_shade.color = Color(0.02, 0.055, 0.06, 0.18)
	background_shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(background_shade)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right"]: margin.add_theme_constant_override("margin_" + side, 80)
	for side in ["top", "bottom"]: margin.add_theme_constant_override("margin_" + side, 48)
	add_child(margin)
	root_column = VBoxContainer.new()
	margin.add_child(root_column)
	var top := HBoxContainer.new()
	root_column.add_child(top)
	var game_title := _label(top, P.localized("game_title"), 38, P.GOLD)
	game_title.autowrap_mode = TextServer.AUTOWRAP_OFF
	game_title.name = "GameTitle"
	_game_title = game_title
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(spacer)
	status_label = _label(top, "", 20, P.MUTED)
	status_label.custom_minimum_size.x = 420
	status_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	root_column.add_child(scroll)
	content = VBoxContainer.new()
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(content)
	tips_overlay = TipsOverlay.new()
	tips_overlay.name = "TipsOverlay"
	add_child(tips_overlay)
	# Compatibility alias for existing UI checks; rendering and animation live in TipsOverlay.
	toast_label = tips_overlay.label
	var version_label := _label(self, P.localized("client_version") % str(Game.CATALOG.data.version), 18, P.MUTED)
	version_label.name = "ClientVersion"
	version_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	version_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	version_label.offset_left = 42
	version_label.offset_top = -42
	version_label.offset_right = 942
	version_label.offset_bottom = -12
	_login_version_label = version_label

func _render_interaction_context() -> Array:
	return [Game.gateway.session_generation, Game.room.get("match_id", ""), Game.room.get("room_id", ""),
		Game.room.get("player", {}).get("phase", ""), Game._room_actions_closed(),
		Game.settlement.get("settlementId", ""), Game._settlement_recovery_match_id, screen]

func _input(event: InputEvent) -> void:
	if not event is InputEventMouseButton or event.button_index != MOUSE_BUTTON_LEFT: return
	_left_pointer_down = event.pressed
	if event.pressed:
		_pointer_render_context = _render_interaction_context()
	else:
		_pointer_render_context.clear()
		if _render_pending: _render.call_deferred()

func _schedule_render() -> void:
	if mail_modal_lock: return
	_sync_account_session()
	if is_instance_valid(_game_title): _game_title.text = P.localized("game_title")
	if _render_pending:
		if _left_pointer_down and _pointer_render_context != _render_interaction_context():
			_left_pointer_down = false
			_pointer_render_context.clear()
			_render.call_deferred()
		return
	_render_pending = true
	_render.call_deferred()

func _reset_draw_charge_visual() -> void:
	_draw_charge_visual = 0.0
	_draw_charge_authoritative = 0.0
	_draw_charge_anchor_msec = 0
	_draw_charge_interval = 4.0
	_draw_charge_room_key = ""
	_draw_charge_revision = -1
	_draw_charge_initialized = false

func _draw_charge_value(authoritative: float = 0.0) -> float:
	return _draw_charge_visual if _draw_charge_initialized else clampf(authoritative, 0.0, 1.0)

func _sync_draw_charge_visual() -> void:
	var player: Dictionary = Game.room.get("player", {})
	var phase := str(player.get("phase", ""))
	if phase not in ["Pve", "Pvp"]:
		_reset_draw_charge_visual()
		return
	var room_id := str(Game.room.get("room_id", ""))
	var battle: Dictionary = Game.room.get("duel", Game.room.get("pve", {}))
	var room_key := "%s:%s" % [room_id, str(battle.get("duel_id", battle.get("battle_id", "")))]
	var revision := int(Game.room.get("room_revision", -1))
	if _draw_charge_initialized and room_key == _draw_charge_room_key and revision == _draw_charge_revision: return
	var authoritative := clampf(float(player.get("draw_charge", "0")), 0.0, 1.0)
	var status: Dictionary = player.get("battle_status", {})
	var interval := maxf(0.1, float(status.get("draw_interval_seconds", "4")))
	var now := Time.get_ticks_msec()
	if not _draw_charge_initialized or room_key != _draw_charge_room_key:
		_draw_charge_visual = authoritative
		_draw_charge_authoritative = authoritative
		_draw_charge_anchor_msec = now
		_draw_charge_interval = interval
		_draw_charge_room_key = room_key
		_draw_charge_revision = revision
		_draw_charge_initialized = true
		return
	# Each snapshot is a fresh authoritative anchor. A lower value also covers
	# full-hand draw skips, where no new card arrives to signal the next cycle.
	_draw_charge_visual = authoritative
	_draw_charge_anchor_msec = now
	_draw_charge_authoritative = authoritative
	_draw_charge_interval = interval
	_draw_charge_room_key = room_key
	_draw_charge_revision = revision

func _update_draw_charge_visual() -> void:
	if not _draw_charge_initialized: return
	var player: Dictionary = Game.room.get("player", {})
	if str(player.get("phase", "")) not in ["Pve", "Pvp"]: return
	var elapsed_ms := maxi(0, Time.get_ticks_msec() - _draw_charge_anchor_msec)
	var paused_ms := maxi(int(player.get("stun_remaining_ms", 0)), int(player.get("draw_block_remaining_ms", 0)))
	var speed_ms := int(player.get("draw_speed_remaining_ms", 0))
	var double_ms := int(player.get("draw_block_speed_remaining_ms", 0))
	var base_text := str(player.get("base_draw_interval_seconds", ""))
	var base_interval := maxf(0.1, float(base_text) if not base_text.is_empty() else _draw_charge_interval)
	var speed_interval := _draw_charge_interval * (2.0 if double_ms > 0 else 1.0)
	var boundaries: Array[int] = [0, elapsed_ms]
	for boundary in [paused_ms, speed_ms, double_ms]:
		if boundary > 0 and boundary < elapsed_ms: boundaries.append(boundary)
	boundaries.sort()
	var predicted := _draw_charge_authoritative
	for index in range(1, boundaries.size()):
		var start := boundaries[index - 1]
		if start < paused_ms: continue
		var interval := speed_interval if start < speed_ms else base_interval
		if start < double_ms: interval /= 2.0
		predicted += float(boundaries[index] - start) / (1000.0 * maxf(0.1, interval))
	_draw_charge_visual = fposmod(predicted, 1.0)
	var bar: Range = _reference.get_node_or_null("DrawChargeBar") as Range if is_instance_valid(_reference) else null
	if bar != null:
		bar.value = clampf(_draw_charge_visual, 0.0, 1.0)
	var percent: Label = _reference.get_node_or_null("DrawChargePercent") as Label if is_instance_valid(_reference) else null
	if percent != null: percent.text = "%d%%" % roundi(_draw_charge_visual * 100.0)
	_update_battle_status_labels(elapsed_ms)

func _update_battle_status_labels(elapsed_ms: int) -> void:
	if not is_instance_valid(_reference): return
	var player: Dictionary = Game.room.get("player", {})
	_set_battle_status_label("PlayerStatus", int(player.get("stun_remaining_ms", 0)), int(player.get("draw_block_remaining_ms", 0)), elapsed_ms, int(player.get("draw_speed_remaining_ms", 0)), int(player.get("draw_block_speed_remaining_ms", 0)))
	var duel: Dictionary = Game.room.get("duel", {})
	if not duel.is_empty():
		_set_battle_status_label("OpponentStatus", int(duel.get("opponent_stun_remaining_ms", 0)), int(duel.get("opponent_draw_block_remaining_ms", 0)), elapsed_ms)
	for index in range(Game.room.get("pve", {}).get("monsters", []).size()):
		var monster: Dictionary = Game.room.pve.monsters[index]
		_set_battle_status_label("MonsterStatus_%d" % index, int(monster.get("stun_remaining_ms", 0)), 0, elapsed_ms)

func _set_battle_status_label(label_name: String, stun_ms: int, block_ms: int, elapsed_ms: int, speed_ms: int = 0, double_ms: int = 0) -> void:
	var label: Label = _reference.get_node_or_null(label_name) as Label
	if label == null: return
	var parts: Array[String] = []
	if stun_ms > elapsed_ms: parts.append(P.localized("battle_status_stun") % ("%.1f" % (float(stun_ms - elapsed_ms) / 1000.0)))
	if block_ms > elapsed_ms: parts.append(P.localized("battle_status_draw_block") % ("%.1f" % (float(block_ms - elapsed_ms) / 1000.0)))
	if speed_ms > elapsed_ms: parts.append(P.localized("battle_status_draw_speed") % ("%.1f" % (float(speed_ms - elapsed_ms) / 1000.0)))
	if double_ms > elapsed_ms: parts.append(P.localized("battle_status_double_charge") % ("%.1f" % (float(double_ms - elapsed_ms) / 1000.0)))
	var lines: Array[String] = []
	for index in range(0, parts.size(), 2): lines.append(" · ".join(parts.slice(index, index + 2)))
	label.text = "\n".join(lines)
	label.size.y = 32.0 * maxi(1, lines.size())
	var typeface := P.font_for_text(label.text, 23)
	label.add_theme_font_override("font", typeface)
	var fitted_size := P.fit_font_size(typeface, 23, label.size.y, label.size.x - 8.0, label.text)
	if lines.size() > 1:
		label.size.y = maxf(label.size.y, ceilf(typeface.get_height(fitted_size)) * lines.size() + label.get_theme_constant("line_spacing") * (lines.size() - 1) + 2.0)
	label.add_theme_font_size_override("font_size", fitted_size)
	label.visible = not parts.is_empty()

func _refresh_after_admin_update() -> void:
	if not Game.room.is_empty(): return
	_codex_ready = false
	if screen in ["cards", "deck", "gear", "enhance", "shop", "market", "prep"]:
		_navigate.call_deferred(screen)

func _on_cache_changed(module: String) -> void:
	_sync_account_session()
	if screen == "shop" and module in ["shop", "inventory", "wallet"] and is_instance_valid(_reference) and not screen_loading:
		if bool(_reference.call("sync_shop_state", _shop_purchase_product_id)): return
	var affected := {
		"shop": ["shop"], "market": ["market"],
		"inventory": ["gear", "enhance", "prep", "shop", "market"],
		"cards": ["cards", "deck"], "decks": ["cards", "deck", "prep"], "mail": ["hall"],
		"wallet": ["hall", "shop", "market", "prep"]
	}
	if screen in affected.get(module, []) and Game.room.is_empty(): _schedule_render()

func _sync_account_session() -> void:
	var new_session: bool = _session_generation != Game.gateway.session_generation
	if new_session:
		_session_generation = Game.gateway.session_generation
		_reset_account_ui()
	var lobby_cards: Variant = Game.lobby.get("cards", null)
	if lobby_cards is Array:
		owned = lobby_cards
		_codex_ready = true
	if Game.lobby.get("inventory") is Dictionary:
		inventory = Game.lobby.inventory
		_shop_inventory_ready = not inventory.is_empty()
	if Game.lobby.get("shop") is Dictionary: shop = Game.lobby.shop
	if Game.lobby.get("market") is Array: listings = Game.lobby.market
	if not Game.lobby.is_empty() and not Game.gateway.token.is_empty() and not Game.gateway.local_account_name.is_empty():
		_login_name = Game.gateway.local_account_name
	if not _card_prewarm_started and not Game.lobby.is_empty() and lobby_cards is Array:
		_card_prewarm_started = true
		_card_pool.begin_prewarm(cards, owned, func(id): return _card_text(id))

func _reset_account_ui() -> void:
	if is_instance_valid(_card_pool):
		_clear_card_page_cache()
		if is_instance_valid(_reference):
			_free_reference_view(_reference)
			_reference = null
			_reference_screen = ""
		_card_pool.clear()
	_card_prewarm_started = false
	screen = "hall"
	owned = []
	inventory = {}
	shop = {}
	listings = []
	deck_draft = []
	gear_draft = []
	bag_tier = "Free"
	potion_count = 0
	edit_mode = false
	screen_loading = false
	_midlayer_seen.clear()
	_search = ""
	_quality = ""
	_enhance_item = ""
	_market_item = ""
	_market_price = 100
	_view_cell = ""
	_codex_card = ""
	_codex_scroll = 0
	_codex_deck_scroll = 0
	_deck_builder_scroll = 0
	_equipment_scroll = 0
	_shop_scroll = 0
	_shop_purchase_product_id = ""
	_codex_ready = false
	_codex_mutating = false
	_shop_inventory_ready = false
	_enhancement_quote = {}
	_enhancement_quote_key = ""
	_combat_panels.clear()
	_reset_draw_charge_visual()
	if is_instance_valid(tips_overlay): tips_overlay.clear()
	for key in ["exploration_map_open", "inventory_open", "relic_pile", "inventory_selected", "relic_selected", "pending_move", "item_detail_scroll"]:
		if has_meta(key): remove_meta(key)
	# Account-bound dialogs must not retain actions against the next login.
	for child in get_children():
		if child is Window or child.name == "ConfirmationModal":
			remove_child(child)
			child.queue_free()

func _current_combat_feedback_context() -> Array:
	if not Game.settlement.is_empty() or Game.gateway.recovering: return []
	var phase: String = str(Game.room.get("player", {}).get("phase", ""))
	if phase not in ["Pve", "Pvp"]: return []
	var battle: Dictionary = Game.room.get("duel", Game.room.get("pve", {}))
	var battle_id: String = str(battle.get("duel_id", battle.get("battle_id", "")))
	if battle_id.is_empty(): return []
	return [Game.gateway.session_generation, Game._room_context_epoch,
		Game.room.get("match_id", ""), Game.room.get("room_id", ""), phase, battle_id]

func _sync_combat_feedback_context() -> void:
	var context := _current_combat_feedback_context()
	if context == _combat_feedback_context: return
	_combat_feedback_context = context
	for child in get_children():
		if child.get_meta("combat_float", false) != true: continue
		var tween: Variant = child.get_meta("combat_float_tween", null)
		if tween is Tween: tween.kill()
		remove_child(child)
		child.queue_free()

func _render() -> void:
	# Rebuilding the pressed button before release cancels its native click.
	# Keep only this interaction's view; a new session/room/phase still renders.
	if _left_pointer_down and _pointer_render_context == _render_interaction_context():
		_render_pending = true
		return
	if _left_pointer_down:
		_left_pointer_down = false
		_pointer_render_context.clear()
	_render_pending = false
	_sync_combat_feedback_context()
	tips_overlay.set_viewport_anchor(_notice_anchor(), _notice_width_ratio())
	_sync_draw_charge_visual()
	var room_cell := "%s:%s:%s" % [Game.room.get("room_id", ""), Game.room.get("self", {}).get("row", -1), Game.room.get("self", {}).get("column", -1)]
	if room_cell != _view_cell or Game.room.get("player", {}).get("phase", "") != "ActionBar":
		set_meta("exploration_map_open", false)
		for key in ["inventory_open", "relic_pile", "inventory_selected", "relic_selected"]:
			if has_meta(key): remove_meta(key)
		if has_meta("pending_move"): remove_meta("pending_move")
	_view_cell = room_cell
	var use_reference: bool = not Game.lobby.is_empty() and Game.lobby.get("unfinishedMatch") == null
	if not Game.room.is_empty() or not Game.settlement.is_empty() or not Game._settlement_recovery_match_id.is_empty(): use_reference = true
	if Game.room_authority_recovering(): use_reference = true
	var card_page := screen if use_reference and screen in ["cards", "deck"] and not screen_loading and Game.room.is_empty() and Game.settlement.is_empty() and Game.ready_prompt.is_empty() else ""
	var page_key := _card_page_key(card_page) if not card_page.is_empty() else 0
	var cached_view: Control = _card_page_cache.get(card_page) as Control
	var reuse_current: bool = not card_page.is_empty() and is_instance_valid(_reference) and _reference == cached_view and _card_page_cache_keys.get(card_page) == page_key
	if not reuse_current: _park_or_free_reference()
	content.add_theme_constant_override("separation", 10 if not Game.room.is_empty() else 18)
	content.size_flags_vertical = Control.SIZE_FILL
	var show_login_video: bool = Game.lobby.is_empty() and Game.room.is_empty() and Game.settlement.is_empty()
	if is_instance_valid(_login_language_selector): _login_language_selector.refresh(_can_show_login_language(), not Game.busy)
	if is_instance_valid(_login_version_label):
		_login_version_label.text = P.localized_text(P.localized("client_version") % str(Game.CATALOG.data.version))
		_login_version_label.visible = show_login_video
	if show_login_video:
		Sound.set_music_context("")
	elif not Game.room.is_empty():
		if Sound.outcome_music_context.is_empty():
			var phase := str(Game.room.get("player", {}).get("phase", ""))
			Sound.set_music_context("battle" if phase in ["Pve", "Pvp"] else "hall")
	elif not Game.settlement.is_empty():
		Sound.set_music_context("defeat" if str(Game.settlement.get("result", "")) in ["Dead", "Defeated", "Death"] else "victory")
	else:
		Sound.set_music_context("shop" if screen in ["shop", "market"] else "hall")
	if is_instance_valid(_backdrop):
		_backdrop.visible = not show_login_video
		if not show_login_video:
			_backdrop.call("set_mode", "exploration" if not Game.room.is_empty() else ("codex" if screen in ["cards", "deck"] else "hall"))
	if is_instance_valid(_background_video):
		_background_video.visible = show_login_video and _login_video_available
		if _background_video.visible and not _background_video.is_playing(): _background_video.play()
	if is_instance_valid(_background_shade): _background_shade.visible = show_login_video and _login_video_available
	_combat_panels = {}
	for node in content.get_children():
		_card_pool.release_descendants(node)
		content.remove_child(node)
		node.queue_free()
	status_label.text = P.localized_text(Game.connection)
	if not Game.lobby.is_empty(): status_label.text += P.localized_text(P.localized("connection_gold_suffix") % Game.lobby.get("wallet", {}).get("gold", 0))
	root_column.get_parent().visible = not use_reference
	if use_reference:
		if not card_page.is_empty():
			cached_view = _card_page_cache.get(card_page) as Control
			if is_instance_valid(cached_view) and _card_page_cache_keys.get(card_page) != page_key:
				_discard_card_page(card_page)
				cached_view = null
			if is_instance_valid(cached_view):
				var was_hidden := not cached_view.visible
				_reference = cached_view
				_reference_screen = card_page
				if was_hidden: _restore_card_page_scroll(card_page, cached_view)
				cached_view.visible = true
				return
		_reference = ReferenceUI.new()
		add_child(_reference)
		_reference_screen = card_page
		if not card_page.is_empty():
			_card_page_cache[card_page] = _reference
			_card_page_cache_keys[card_page] = page_key
		_reference.build(self)
		return
	if not Game.settlement.is_empty():
		_settlement()
		return
	if not Game.room.is_empty():
		_room()
		return
	if Game.lobby.is_empty():
		_login()
		return
	if not Game.ready_prompt.is_empty():
		_ready_screen()
		return
	if Game.lobby.get("unfinishedMatch") != null:
		_label(content, P.localized("ui_restoring_run"), 42, P.GOLD)
		_label(content, Game.connection, 24, P.MUTED)
		_button(content, P.localized("reconnect"), Game.reconnect, Game.busy)
		return
	_nav()
	if screen_loading:
		_label(content, P.localized("loading"), 32)
		return
	match screen:
		"hall": _hall()
		"prep": _preparation()
		"cards": _codex()
		"deck": _codex()
		"gear": _equipment()
		"shop": _shop()
		"market": _market()

func _label(parent: Node, text: String, size: int = 24, color: Color = P.PAPER, localize: bool = true) -> Label:
	var node := Label.new()
	var display_text := P.localized_text(text) if localize else text
	var typeface := P.font_for_text(display_text, size)
	node.add_theme_font_override("font", typeface)
	node.text = display_text
	node.add_theme_font_size_override("font_size", size)
	node.add_theme_color_override("font_color", color)
	node.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	# Container-managed labels need their shaped text height for layout. Fixed
	# overlay labels still clip to their authored rectangles.
	node.clip_text = not parent is Container
	parent.add_child(node)
	P.fit_control_font(node, typeface, size)
	return node

func _button(parent: Node, text: String, callback: Callable, disabled: bool = false, key: String = "") -> Button:
	var button := Button.new()
	button.text = P.localized_text(text)
	button.disabled = disabled
	button.custom_minimum_size.y = 62
	button.clip_text = true
	button.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	button.pressed.connect(callback)
	var button_key := key if not key.is_empty() else ("UI/CardCodex/card_codex_action_button_orange.png" if _is_positive_button(text) else "UI/CardCodex/card_codex_action_button_blue.png")
	Art.button(button, button_key)
	if parent is HBoxContainer:
		var caption_width := 0.0
		for line in button.text.split("\n"):
			caption_width = maxf(caption_width, button.get_theme_font("font").get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, 24).x)
		button.custom_minimum_size.x = clampf(ceilf(caption_width) + 48.0, 120.0, 420.0)
	parent.add_child(button)
	P.fit_control_font(button, button.get_theme_font("font"), 24, 48.0)
	return button

func _is_positive_button(value: String) -> bool:
	for keyword in [P.localized("confirm"), P.localized("claim"), P.localized("login"), P.localized("register"), "Login", P.localized("begin_action"), P.localized("save"), P.localized("buy"), P.localized("empower"), P.localized("equip"), P.localized("list_for_sale"), P.localized("select"), P.localized("ready"), P.localized("nav_prep"), P.localized("random_name"), "Randomize"]:
		if value.contains(keyword): return true
	return false

func _panel(parent: Node, minimum_width: float = 0, scrollable: bool = false) -> VBoxContainer:
	var panel := PanelContainer.new()
	panel.custom_minimum_size.x = minimum_width
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel.add_theme_stylebox_override("panel", Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png"))
	parent.add_child(panel)
	var content_parent: Node = panel
	if scrollable:
		var scroll := ScrollContainer.new()
		scroll.name = "LoginControlsScroll"
		scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
		scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
		panel.add_child(scroll)
		content_parent = scroll
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content_parent.add_child(column)
	return column

func _row(parent: Node) -> HBoxContainer:
	var row := HBoxContainer.new()
	parent.add_child(row)
	return row

func _login() -> void:
	content.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_label(content, P.localized("chaos_realm"), 76, P.GOLD)
	_label(content, P.localized("login_subtitle"), 30)
	var row := _row(content)
	row.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var panel := _panel(row, 0, true)
	panel.add_theme_constant_override("separation", 12)
	var panel_frame: Control = panel.get_parent().get_parent()
	panel_frame.name = "LoginPanel"
	panel_frame.size_flags_stretch_ratio = 0.32
	panel_frame.custom_minimum_size.x = 340
	_label(panel, P.localized("start"), 40)
	_label(panel, P.localized("nickname"), 22, P.MUTED)
	var name_input := LineEdit.new()
	name_input.text = _login_name
	name_input.placeholder_text = P.localized_text(P.localized("account_placeholder"))
	name_input.max_length = 20
	name_input.text_changed.connect(func(value): _login_name = value)
	panel.add_child(name_input)
	var randomize_button := _button(panel, P.localized("random_name"), func():
		_login_name = _random_login_name(_login_name)
		name_input.text = _login_name
	, Game.busy, "UI/CardCodex/card_codex_action_button_orange.png")
	randomize_button.tooltip_text = P.localized("random_name_hint")
	if OS.is_debug_build():
		var local_button := _button(panel, P.localized("local_dev_login"), func(): Game.login(LOCAL_SERVER_URL, _login_name), Game.busy, "UI/CardCodex/card_codex_action_button_blue.png")
		local_button.tooltip_text = P.localized_text(P.localized("ui_local_server_hint"))
	_label(panel, P.localized("nickname_hint"), 20, P.MUTED)
	_button(panel, P.localized("cloud_login"), func(): Game.login(CLOUD_SERVER_URL, _login_name), Game.busy, "UI/CardCodex/card_codex_action_button_orange.png")
	var steam_reason: String = Game.platform.login_unavailable_reason()
	_button(panel, P.localized("steam_login"), func(): Game.login_steam(CLOUD_SERVER_URL, _login_name), Game.busy or not steam_reason.is_empty())
	if not steam_reason.is_empty(): _label(panel, steam_reason, 20, P.MUTED)
	if not Game.authentication_reason.is_empty(): _label(panel, Game.authentication_reason, 22, P.GOLD)
	if not Game.configuration_error.is_empty(): _label(panel, Game.configuration_error, 22, P.GOLD)
	var center_space := Control.new()
	center_space.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	center_space.size_flags_stretch_ratio = 0.38
	row.add_child(center_space)
	var about := _panel(row)
	var about_frame: Control = about.get_parent()
	about_frame.name = "AnnouncementPanel"
	about_frame.size_flags_stretch_ratio = 0.30
	about_frame.custom_minimum_size.x = 400
	var announcement: Dictionary = Game.server_info.get("announcement", {})
	var title := RemoteCopy.field(announcement, "title")
	var body := RemoteCopy.field(announcement, "body")
	var announcement_title := _label(about, title if not title.is_empty() else P.localized("ui_announcement_title"), 34, P.GOLD, false)
	announcement_title.name = "AnnouncementTitle"
	announcement_title.custom_minimum_size.y = 58
	announcement_title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	announcement_title.tooltip_text = announcement_title.text
	var announcement_scroll := ScrollContainer.new()
	announcement_scroll.name = "AnnouncementScroll"
	announcement_scroll.custom_minimum_size.y = 230
	announcement_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	announcement_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	announcement_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	announcement_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	_about_scroll_content(announcement_scroll, body)
	about.add_child(announcement_scroll)

func _can_show_login_language() -> bool:
	return Game.lobby.is_empty() and Game.room.is_empty() and Game.settlement.is_empty() and Game.ready_prompt.is_empty() and Game.gateway.token.is_empty() and not Game.room_authority_recovering() and Game._settlement_recovery_match_id.is_empty()

func _select_login_language(code: String) -> void:
	# A queued click from the login screen must not change an authenticated
	# session or race a login request that is already in progress.
	if not _can_show_login_language() or Game.busy: return
	P.set_language(code)
	theme = P.theme()
	if is_instance_valid(_game_title): _game_title.text = P.localized("game_title")
	for label in [_game_title, status_label, _login_version_label]:
		if not is_instance_valid(label): continue
		var requested: int = label.get_theme_font_size("font_size")
		var typeface := P.font_for_text(label.text, requested)
		label.add_theme_font_override("font", typeface)
		P.fit_control_font(label, typeface, requested)
	var audio: Node = get_node_or_null("AudioSettings")
	if audio != null: audio._refresh()
	Game.changed.emit()

func _random_login_name(previous: String = "") -> String:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(RANDOM_NAMES_PATH))
	var language_key := "zh-CN" if P.language() == "zh-CN" else "en"
	var names: Array = []
	if parsed is Dictionary:
		var available: Variant = parsed.get("languages", {}).get(language_key, [])
		if available is Array: names = available
	if names.is_empty(): names = [P.localized("traveler_default_name")]
	var random := RandomNumberGenerator.new()
	random.randomize()
	var candidate := previous
	for _attempt in 4:
		candidate = "%s#%04d" % [str(names[random.randi_range(0, names.size() - 1)]), random.randi_range(0, 9999)]
		if candidate != previous: return candidate
	return candidate

func _about_scroll_content(scroll: ScrollContainer, body: String) -> void:
	var text := Label.new()
	text.text = body if not body.is_empty() else P.localized("ui_no_announcement")
	text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	text.add_theme_font_override("font", P.font_for_text(text.text, 24))
	text.add_theme_font_size_override("font_size", 24)
	text.add_theme_color_override("font_color", P.PAPER)
	scroll.add_child(text)

func _nav() -> void:
	var nav := _row(content)
	var names := {"hall": P.localized("nav_hall"), "cards": P.localized("cards_title"), "gear": P.localized("nav_gear"), "shop": P.localized("nav_shop"), "market": P.localized("nav_market"), "prep": P.localized("nav_prep")}
	for key in names:
		var button := _button(nav, names[key], _navigate.bind(key), Game.busy or not Game.ticket.is_empty())
		button.set_meta("sound_cue", "")
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		if screen == key: button.add_theme_stylebox_override("normal", Art.style("UI/CardCodex/card_codex_action_button_orange.png"))

func _navigate(value: String) -> void:
	var generation: int = Game.gateway.session_generation
	if value != screen: Sound.play_cue("ui_open")
	if value == "gear" and screen != "gear": _equipment_scroll = 0
	if value == "shop" and screen != "shop": _shop_scroll = 0
	screen = value
	edit_mode = false
	_codex_card = ""
	_codex_scroll = 0
	_deck_builder_scroll = 0
	_enhancement_quote_key = ""
	_enhancement_quote = {}
	_sync_account_session()
	if generation != Game.gateway.session_generation: return
	if value in ["cards", "deck"]: deck_draft = Game.deck().get("cardIds", []).duplicate()
	if value in ["gear", "enhance", "prep"]:
		gear_draft = Game.loadout().get("equipmentIds", []).duplicate()
		gear_draft.resize(5)
	screen_loading = false
	_render()

func _hall() -> void:
	_label(content, P.localized("camp_title"), 56, P.GOLD)
	var identity := _row(content)
	_label(identity, P.localized("account_uid_inline") % [Game.lobby.player.get("displayName", ""), Game.lobby.player.get("userId", "")], 20, P.MUTED, false)
	_button(identity, P.localized("switch_account"), Game.logout, Game.busy)
	var classes := _row(content)
	for key in P.CLASSES:
		var info: Array = P.CLASSES[key]
		var button := _button(classes, P.localized("class_health_summary") % [P.word(key), info[0], info[2]], func(): Game.select_class(key), Game.busy or not Game.preparation.is_empty())
		button.icon = Art.texture("UI/Codex/class_badge_%s.png" % key.to_lower())
		button.expand_icon = true
		button.add_theme_constant_override("icon_max_width", 44)
		# 当前职业的元素图标放在职业条旁边，而不是职业选择框内部。
		if Game.hero_class == key:
			var element_icon := TextureRect.new()
			element_icon.texture = Art.texture("UI/Battle/battle_element_icon_fire.png")
			element_icon.custom_minimum_size = Vector2(44, 44)
			element_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			element_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			classes.add_child(element_icon)
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		if Game.hero_class == key: button.add_theme_stylebox_override("normal", Art.style("UI/CardCodex/card_codex_action_button_orange.png"))
	var row := _row(content)
	var hero := _panel(row, 740)
	Art.image(hero, Art.portrait(Game.hero_class), Vector2(200, 240))
	var info: Array = P.CLASSES[Game.hero_class]
	_label(hero, info[0], 52)
	_label(hero, info[3], 25, P.MUTED)
	_label(hero, info[4], 30, P.TEAL)
	_label(hero, P.localized("ui_deck_battle_count") % Game.deck().get("cardIds", []).size(), 26)
	var portal := _panel(row, 740)
	Art.image(portal, Art.texture("UI/Hall/portal_background_clean.png"), Vector2(360, 240))
	_label(portal, P.localized("chaos_realm"), 60, P.GOLD)
	_label(portal, P.localized("ui_expedition_intro"), 28)
	var prep_button := _button(portal, P.localized("ui_prep_arrow"), _navigate.bind("prep"))
	prep_button.set_meta("sound_cue", "")
	_label(portal, P.localized("ui_room_hint"), 22, P.MUTED)

func _preparation() -> void:
	_label(content, P.localized("ui_prep_tagline"), 46, P.GOLD)
	if not Game.preparation.is_empty():
		var panel := _panel(content)
		var snap: Dictionary = Game.preparation.snapshot
		_label(panel, P.localized("ui_prep_locked") % [P.CLASSES[snap.heroClass][0], snap.cardIds.size()], 32)
		_label(panel, P.localized("ui_prep_bag_summary") % [snap.backpackCapacity, snap.safeSlotIndexes.size(), snap.potionCount])
		if not Game.ticket.is_empty():
			_label(panel, P.localized("ui_matchmaking_hint"), 30, P.TEAL)
		else:
			_button(panel, P.localized("start_match"), Game.enqueue, Game.busy or not Game.gateway.online)
		_button(panel, P.localized("cancel_match") if not Game.ticket.is_empty() else P.localized("cancel_prep"), Game.cancel_preparation, Game.busy)
		return
	var row := _row(content)
	var left := _panel(row, 650)
	var identity := _row(left)
	Art.image(identity, Art.portrait(Game.hero_class), Vector2(90, 110))
	_label(identity, P.CLASSES[Game.hero_class][0], 36)
	_label(left, P.localized("ui_locked_weapon_prefix") + P.CLASSES[Game.hero_class][1], 26, P.GOLD)
	_label(left, P.localized("deck_count_summary") % Game.deck().get("cardIds", []).size())
	var consumables: Dictionary = inventory.get("consumables", {})
	for key in ["Free", "Advanced", "Top"]:
		var text_key: String = {"Free": "bag_option_free", "Advanced": "bag_option_advanced", "Top": "bag_option_top"}[key]
		var text: String = P.localized(text_key)
		var button := _button(left, text, func(): bag_tier = key; _render())
		if bag_tier == key: button.add_theme_stylebox_override("normal", Art.style("UI/CardCodex/card_codex_action_button_orange.png"))
	_label(left, P.localized("health_potion_summary") % consumables.get("healthPotionCount", 0), 22)
	var potion := SpinBox.new()
	potion.max_value = mini(2, int(consumables.get("healthPotionCount", 0)))
	potion.value = potion_count
	potion.value_changed.connect(func(value): potion_count = int(value))
	left.add_child(potion)
	_button(left, P.localized("confirm_prep"), func(): Game.prepare(bag_tier, potion_count), Game.busy)
	var right := _panel(row, 880)
	_label(right, P.localized("temporary_bag"), 34)
	_label(right, P.localized("ui_safe_slot_hint"), 22, P.MUTED)
	var capacity: int = {"Free": 20, "Advanced": 28, "Top": 36}[bag_tier]
	var safe: int = {"Free": 0, "Advanced": 1, "Top": 3}[bag_tier]
	var slot_order: Array = []
	for safe_index in range(capacity - safe, capacity): slot_order.append(safe_index)
	for slot_index in range(capacity):
		if not slot_order.has(slot_index): slot_order.append(slot_index)
	var rows := int(ceil(float(capacity) / 6.0))
	var scroll := ScrollContainer.new()
	scroll.name = "PreparationBackpackScroll"
	scroll.custom_minimum_size.y = 4 * 96 + 3 * Art.COMMON_CELL_GAP
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	right.add_child(scroll)
	var grid := GridContainer.new()
	grid.name = "PreparationBackpackGrid"
	grid.columns = 6
	grid.add_theme_constant_override("h_separation", Art.COMMON_CELL_GAP)
	grid.add_theme_constant_override("v_separation", Art.COMMON_CELL_GAP)
	grid.custom_minimum_size.y = rows * (96 + Art.COMMON_CELL_GAP) - Art.COMMON_CELL_GAP
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(grid)
	for display_index in range(capacity):
		var slot_index: int = int(slot_order[display_index])
		var is_safe: bool = slot_index >= capacity - safe
		var cell := _button(grid, "" if is_safe else str(slot_index + 1), func(): pass, true)
		cell.custom_minimum_size = Art.COMMON_CELL_DISPLAY_SIZE
		if is_safe: Art.apply_safe_slot_button(cell)
		else: Art.button(cell, Art.COMMON_CELL_KEY)

func _ready_screen() -> void:
	var panel := _panel(content)
	_label(panel, P.localized("ui_party_gathering"), 60, P.GOLD)
	_label(panel, P.localized("ui_match_found"), 32)
	_label(panel, P.localized("ui_confirmed_count") % [Game.ready_prompt.get("ready_players", 0), Game.ready_prompt.get("required_players", 1)])
	var remaining := maxi(0, int((int(Game.ready_prompt.get("deadline_unix_ms", 0)) - Time.get_unix_time_from_system() * 1000) / 1000))
	_label(panel, P.localized("ui_confirm_remaining") % remaining, 32, P.TEAL)
	_button(panel, P.localized("ready"), func(): Game.gateway.send("room.ready"), not Game.gateway.online)

func card_description(id: String, kind: String = "face", level: int = 0) -> String:
	if kind == "face":
		var summary := CardDetails.face_description(id, level, cards.get(id, {}))
		if not summary.is_empty(): return summary
	var locale := P.language()
	if locale not in ["zh-CN", "en"]:
		return CardDetails.effect_text(CardDetails.at_level(cards.get(id, {}), level))
	var descriptions: Dictionary = P.language_pack_section("card_descriptions")
	var description := str(descriptions.get("card.%s.desc.%s" % [kind, id], ""))
	# Existing full descriptions use the legacy `card.desc.full.<id>` order.
	# Keep reading them until the localized table is migrated to the newer key.
	if description.is_empty() and kind == "full":
		description = str(descriptions.get("card.desc.full." + id, ""))
	return description

func _card_text(id: String, level: int = 0, element_override: String = "") -> String:
	var cache_key := "%s|%s|%s|%s" % [P.language(), id, level, element_override]
	if _card_text_cache.has(cache_key): return _card_text_cache[cache_key]
	var info: Dictionary = CardDetails.with_element(cards.get(id, {}), element_override)
	var source: String = info.get("source", "")
	var badge := P.localized("monster") if not info.get("is_codex", true) else P.word(info.get("hero_class", ""))
	var name := CardDetails.localized_name(id, info)
	var description: String = CardDetails.face_description(id, level, info)
	if description.is_empty(): description = card_description(id, "face", level)
	if description.is_empty():
		# Cards without a configured face description use the structured fallback.
		var lines: Array = []
		for key in ["elemental_damage", "direct_damage", "heal", "shield"]:
			if int(info.get(key, 0)) > 0:
				lines.append("%s %s" % [{"elemental_damage": P.word(info.get("element", "None")), "direct_damage": P.localized("direct_damage"), "heal": P.localized("healing"), "shield": P.localized("word_shield")}[key], info[key]])
		description = " / ".join(lines)
	var result := "%s %s\n%s\n\n%s" % [badge, name, P.word(info.get("quality", "")) if source != "Monster" else P.localized("ui_red_run"), description]
	_card_text_cache[cache_key] = result
	return result

func _card_button(parent: Node, id: String, callback: Callable, selected: bool = false, disabled: bool = false, options: Dictionary = {}) -> Button:
	var element_override: String = options.get("element_override", "")
	return _card_pool.acquire(parent, id, CardDetails.with_element(cards.get(id, {}), element_override), _card_text(id, int(options.get("level", 0)), element_override), selected, disabled, options, callback)

func release_card(button: Button) -> void:
	_card_pool.release(button)

func ensure_card_pool(required: int) -> bool:
	return _card_pool.ensure_available(required)

func _owned_card(id: String) -> Dictionary:
	if not _owned_index_ready:
		_owned_index_ready = true
		for entry in owned:
			if entry is Dictionary:
				var card_id := str(entry.get("cardId", ""))
				if not card_id.is_empty() and not _owned_by_id.has(card_id):
					_owned_by_id[card_id] = entry
	var found: Variant = _owned_by_id.get(id, {})
	return found if found is Dictionary else {}

func _card_material(kind: String) -> int:
	var field := kind.left(1).to_lower() + kind.substr(1)
	return int(Game.lobby.get("materials", {}).get(field, 0))

func _card_action_block_reason(id: String, action: String) -> String:
	var entry := _owned_card(id)
	if entry.is_empty() or not entry.has("craftCost"): return P.localized("quote_unavailable_short")
	var kind := str(entry.get("currencyKind", "WarriorSoul"))
	var material := P.localized_word(kind)
	var balance := _card_material(kind)
	if action == "upgrade":
		if int(entry.get("level", 0)) >= 5: return P.localized("max_level")
		var cost := int(entry.get("upgradeCost", 0))
		if balance < cost: return P.localized("codex_insufficient") % [material, cost - balance]
		if not entry.get("canUpgrade", false): return P.localized("state_changed")
	elif action == "craft":
		if entry.get("unlocked", false) or int(entry.get("copyCount", 0)) > 0: return P.localized("ui_card_activated")
		var craft_cost := int(entry.get("craftCost", 0))
		if balance < craft_cost: return P.localized("codex_insufficient") % [material, craft_cost - balance]
	elif action == "dismantle" and deck_draft.count(id) >= int(entry.get("copyCount", 0)):
		return P.localized("card_in_deck")
	return ""

func _replace_owned_card(card: Dictionary) -> void:
	var id := str(card.get("cardId", ""))
	if id.is_empty(): return
	for index in range(owned.size()):
		if str(owned[index].get("cardId", "")) == id:
			owned[index] = card
			if _owned_index_ready: _owned_by_id[id] = card
			return
	owned.append(card)
	if _owned_index_ready: _owned_by_id[id] = card

func _set_codex_action_busy(value: bool) -> void:
	if not is_instance_valid(_reference): return
	for node_name in ["UpgradeCard", "DismantleCard", "CraftCard", "CloseCardDetails"]:
		var button := _reference.find_child(node_name, true, false) as Button
		if button != null: button.disabled = value
	var primary := _reference.find_child("UpgradeCard", true, false) as Button
	if value and primary != null: primary.text = P.localized_text(P.localized("processing"))

func _card_action(id: String, action: String) -> void:
	if Game.busy or _codex_mutating or not _codex_ready: return
	var entry := _owned_card(id)
	if entry.is_empty() or not entry.has("craftCost"): return
	var blocked := _card_action_block_reason(id, action)
	if not blocked.is_empty():
		_toast(blocked)
		return
	_codex_mutating = true
	Game.busy = true
	_set_codex_action_busy(true)
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1/cards/%s/%s" % [id.uri_encode(), action], HTTPClient.METHOD_POST, {"expectedVersion": int(entry.get("version", 0))})
	if not _session_result_current(generation, result):
		_codex_mutating = false
		return
	if result.ok:
		if result.data.get("card") is Dictionary: _replace_owned_card(result.data.card)
		Game.update_cache("cards", owned)
		if result.data.get("materials") is Dictionary: Game.lobby["materials"] = result.data.materials
		_codex_ready = true
		Sound.play_cue("upgrade" if action == "upgrade" else "reward")
		_toast({"craft": P.localized("ui_crafted_card"), "dismantle": P.localized("ui_dismantled_card"), "upgrade": P.localized("upgrade_success")}.get(action, P.localized("operation_done")))
	else:
		Sound.play_cue("error")
		var refreshed: Dictionary = await Game.gateway.request("/api/v1/cards")
		if not _session_result_current(generation, refreshed):
			_codex_mutating = false
			return
		_codex_ready = refreshed.ok
		if refreshed.ok:
			owned = refreshed.data
			Game.update_cache("cards", owned)
	_codex_mutating = false
	if not _session_result_current(generation): return
	Game.busy = false
	_render()

func _codex() -> void:
	var header := _row(content)
	_label(header, P.localized("cards_title"), 42, P.GOLD)
	_label(header, P.localized("deck_count_summary") % deck_draft.size(), 30)
	_button(header, P.localized("save_deck"), _save_deck, deck_draft.size() != 20 or Game.busy)
	_button(header, P.localized("restore"), func(): deck_draft = Game.deck().get("cardIds", []).duplicate(); _render())
	var deck_row := HFlowContainer.new()
	content.add_child(deck_row)
	for index in range(deck_draft.size()):
		var id: String = deck_draft[index]
		_button(deck_row, "%s ×" % CardDetails.localized_name(id, cards.get(id, {})), func(): deck_draft.remove_at(index); _render())
	var resources: Dictionary = Game.lobby.get("materials", {})
	_label(content, P.localized("ui_soul_summary") % [resources.get("warriorSoul", 0), resources.get(Game.hero_class.to_lower() + "Soul", 0)], 22, P.MUTED)
	var grid := GridContainer.new()
	grid.columns = 6
	content.add_child(grid)
	for card in owned:
		var class_value: Variant = card.get("heroClass")
		if class_value != null and class_value != Game.hero_class: continue
		var id: String = card.cardId
		var can_add: bool = card.get("unlocked", false) and deck_draft.size() < 20 and deck_draft.count(id) == 0
		if cards.get(id, {}).get("quality", "") == "Orange":
			for entry in deck_draft:
				var existing: Dictionary = cards.get(entry, {})
				if existing.get("quality") == "Orange" and (existing.get("hero_class") == null) == (class_value == null): can_add = false
		var button := _card_button(grid, id, func(): deck_draft.append(id); _render(), false, not can_add)
		button.tooltip_text += P.localized("ui_owned_card_summary") % [deck_draft.count(id), card.copyCount, card.level]

func _save_deck() -> void:
	if Game.busy: return
	if deck_draft.size() != DeckBuilder.DECK_SIZE:
		_toast(P.localized("deck_requires_twenty"))
		return
	Game.busy = true
	_render()
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1/decks/" + Game.hero_class, HTTPClient.METHOD_PUT, {"cardIds": deck_draft, "expectedVersion": Game.deck().get("version", 0)}, [0, 400, 409, 429, 500, 502, 503, 504])
	if not _session_result_current(generation, result): return
	if result.ok:
		var decks: Array = Game.lobby.get("decks", []).duplicate(true)
		for index in decks.size():
			if str(decks[index].get("heroClass", "")) == Game.hero_class:
				decks[index] = result.data
				break
		Game.update_cache("decks", decks)
		deck_draft = Game.deck().get("cardIds", []).duplicate()
		Sound.play_cue("equip")
		_toast(P.localized("deck_saved"))
	elif int(result.get("status", 0)) == 409:
		await Game.refresh_cache("decks")
		if not _session_result_current(generation): return
		deck_draft = Game.deck().get("cardIds", []).duplicate()
		_toast(P.localized("deck_changed_retry"))
	elif int(result.get("status", 0)) == 400:
		_toast(P.localized("deck_invalid"))
	else:
		_toast(P.localized("deck_save_failed"))
	Game.busy = false
	_render()

func _equipment_name(item: Dictionary) -> String:
	return EquipmentDetails.title(item)

func _equipment() -> void:
	_label(content, P.localized("gear_title"), 44, P.GOLD)
	var weapon: Dictionary = {}
	for value in Game.lobby.get("classWeapons", []):
		if value.heroClass == Game.hero_class: weapon = value
	var top := _row(content)
	Art.image(top, Art.texture("UI/Item/exploration_prep_item_icon_weapon_%s.png" % Game.hero_class.to_lower()), Vector2(80, 100))
	_label(top, P.localized("locked_item_level") % [P.CLASSES[Game.hero_class][1], weapon.get("level", 0)], 30, P.GOLD)
	_button(top, P.localized("enhance_weapon"), _enhance_weapon, Game.busy or int(weapon.get("level", 0)) >= 5)
	_label(content, P.localized("ui_fragments_amount") % Game.lobby.get("materials", {}).get("equipmentFragments", 0), 24, P.MUTED)
	var slot_names := [P.localized("word_head"), P.localized("word_chest"), P.localized("word_hands"), P.localized("word_legs"), P.localized("word_feet")]
	var row := _row(content)
	for index in range(5):
		var id: Variant = gear_draft[index] if index < gear_draft.size() else null
		var name := P.localized("not_equipped")
		var worn_item: Dictionary = {}
		for item in inventory.get("equipments", []):
			if item.instanceId == id:
				name = _equipment_name(item)
				worn_item = item
		var slot := _button(row, slot_names[index] + "\n" + name + (P.localized("click_unequip_suffix") if id != null else ""), func(): gear_draft[index] = null; _render(), id == null)
		slot.icon = Art.equipment_texture(worn_item) if not worn_item.is_empty() else Art.texture("UI/Item/exploration_prep_item_icon_%s.png" % ["helmet", "chest", "gauntlet", "legs", "boots"][index])
		slot.expand_icon = true
		slot.add_theme_constant_override("icon_max_width", 58)
		if id == null:
			for state in ["normal", "hover", "pressed", "disabled", "focus"]:
				slot.add_theme_color_override("icon_%s_color" % state, Art.UNEQUIPPED_ITEM_MODULATE)
	_button(content, P.localized("save_loadout"), func(): _mutate("/loadouts/" + Game.hero_class, HTTPClient.METHOD_PUT, {"equipmentIds": gear_draft, "expectedVersion": Game.loadout().get("version", 0)}), Game.busy)
	for item in inventory.get("equipments", []):
		var line := _row(_panel(content))
		_label(line, _equipment_name(item), 26)
		_label(line, P.word(item.get("effectAffix")), 24, P.TEAL)
		_button(line, P.localized("equip"), func(): _equip(item), Game.busy or item.get("location") not in ["Inventory", "Equipped"])
		_button(line, P.localized("empower"), func(): _enhance(item), Game.busy or int(item.get("level", 0)) >= 5)
	if inventory.get("equipments", []).is_empty(): _label(content, P.localized("no_equipment_hint"), 28, P.MUTED)

func _equip(item: Dictionary) -> void:
	var slots := {"Head": 0, "Helmet": 0, "Chest": 1, "Body": 1, "Hands": 2, "Gloves": 2, "Legs": 3, "Feet": 4, "Boots": 4}
	if not slots.has(item.slot): _toast(P.localized("unknown_equipment_slot")); return
	gear_draft.resize(5)
	var target_slot: int = slots[item.slot]
	var item_id: Variant = item.get("instanceId", "")
	if gear_draft[target_slot] == item_id:
		gear_draft[target_slot] = null
		_render()
		return
	if _draft_high_quality_limit_would_block(item):
		_toast(P.localized("loadout_high_quality_limit"))
		return
	gear_draft[target_slot] = item_id
	_render()

func _draft_high_quality_limit_would_block(item: Dictionary) -> bool:
	var slots := {"Head": 0, "Helmet": 0, "Chest": 1, "Body": 1, "Hands": 2, "Gloves": 2, "Legs": 3, "Feet": 4, "Boots": 4}
	var slot := str(item.get("slot", ""))
	return slots.has(slot) and _draft_has_other_high_quality(item, int(slots[slot]))

func _draft_has_other_high_quality(item: Dictionary, target_slot: int) -> bool:
	var quality := Art.quality_name(item.get("quality", item.get("Quality", "")))
	if quality not in ["Orange", "Red"]: return false
	for index in range(gear_draft.size()):
		if index == target_slot: continue # Replacing this slot preserves the one-item limit.
		var draft_id: Variant = gear_draft[index]
		if draft_id == null: continue
		for candidate in inventory.get("equipments", []):
			if candidate.get("instanceId", "") == draft_id and Art.quality_name(candidate.get("quality", candidate.get("Quality", ""))) in ["Orange", "Red"]:
				return true
	return false

func _equipped_items() -> Array:
	if not Game.room.is_empty(): return Game.room.get("player", {}).get("equipped_items", [])
	return inventory.get("equipments", []).filter(func(value): return value.get("instanceId", "") in gear_draft)

func _current_equipment(item: Dictionary, worn: Array = []) -> Dictionary:
	var gear: Dictionary = EquipmentDetails.equipment(item)
	if worn.is_empty(): worn = _equipped_items()
	var current: Dictionary = {}
	for candidate in worn:
		if EquipmentDetails.equipment(candidate).get("slot", "") == gear.get("slot", ""):
			current = candidate
			break
	return current

func _show_equipment_details(item: Dictionary, action: Callable = Callable(), action_title: String = P.localized("equip")) -> void:
	var worn := _equipped_items()
	var current := _current_equipment(item, worn)
	# Wearing into an empty slot has no baseline to compare. Follow the GDD/UI
	# flow and execute the requested equip action without opening a modal.
	if current.is_empty() and action.is_valid():
		if not Game.busy: action.call()
		return
	var dialog := EquipmentCompareDialog.new()
	add_child(dialog)
	dialog.open(item, current, worn, action, action_title, Game.busy)

func _show_battle_details(status: Dictionary) -> void:
	var existing := get_node_or_null("BattleDetailsModal")
	if existing != null:
		if existing.has_method("dismiss"): existing.call("dismiss")
		return
	var dialog := ConfirmationModalScene.instantiate()
	dialog.name = "BattleDetailsModal"
	add_child(dialog)
	dialog.configure(
		BattleDetails.description(status) if not status.is_empty() else P.localized("battle_stats_waiting"),
		Callable(),
		{"title": "battle_stats_set", "confirm_text": "confirm", "info_only": true, "tall": true})

func _enhance(item: Dictionary) -> void:
	if Game.busy: return
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1/equipment/" + item.instanceId + "/enhancement-quote")
	if not _session_result_current(generation, result): return
	if not result.ok: return
	var quote: Dictionary = result.data
	if not quote.get("canEnhance", false): _toast(P.localized("enhance_unavailable")); return
	var body := {"expectedVersion": quote.expectedVersion}
	var cost_text := P.localized("enhance_cost_confirm") % [quote.fragmentCost, quote.nextLevel]
	if int(quote.materialCount) == 0:
		_confirm(cost_text + "？", func(): _mutate("/equipment/" + item.instanceId + "/enhance", HTTPClient.METHOD_POST, body))
		return
	var dialog := AcceptDialog.new()
	dialog.title = P.localized("enhance_material_dialog")
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(720, 390)
	dialog.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(column)
	_label(column, P.localized("enhance_material_cost") % cost_text, 24)
	var count := 0
	for material in inventory.get("equipments", []):
		if material.instanceId == item.instanceId or material.get("location") != "Inventory" or material.quality != item.quality: continue
		count += 1
		_button(column, _equipment_name(material), func(): body.materialEquipmentId = material.instanceId; dialog.queue_free(); _confirm(P.localized("enhance_material_confirm") % [cost_text, _equipment_name(material)], func(): _mutate("/equipment/" + item.instanceId + "/enhance", HTTPClient.METHOD_POST, body)))
	if count == 0: _label(column, P.localized("enhance_no_material"))
	add_child(dialog)
	dialog.popup_centered(Vector2i(750, 360))
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)

func _enhance_weapon() -> void:
	if Game.busy: return
	var generation: int = Game.gateway.session_generation
	var hero_class: String = Game.hero_class
	var result: Dictionary = await Game.gateway.request("/api/v1/class-weapons/" + hero_class + "/enhancement-quote")
	if not _session_result_current(generation, result): return
	if not result.ok: return
	var quote: Dictionary = result.data
	if not quote.get("canEnhance", false): _toast(P.localized("enhance_weapon_unavailable")); return
	_confirm(P.localized("enhance_weapon_confirm") % [quote.fragmentCost, quote.nextLevel], func(): _mutate("/class-weapons/" + hero_class + "/enhance", HTTPClient.METHOD_POST, {"expectedVersion": quote.expectedVersion}))

func _read_enhancement_quote(item: Dictionary, weapon: Dictionary) -> void:
	var id: String = item.get("instanceId", Game.hero_class)
	var key := "%s:%s" % [id, item.get("version", weapon.get("version", 0))]
	if key == _enhancement_quote_key: return
	_enhancement_quote_key = key
	_enhancement_quote = {}
	var prefix := "/equipment/" if not item.is_empty() else "/class-weapons/"
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1" + prefix + id + "/enhancement-quote")
	if not _session_result_current(generation, result): return
	if key != _enhancement_quote_key or screen != "enhance": return
	_enhancement_quote = result.data if result.ok else {"error": true}
	_schedule_render()

func _weapon_benefit(level: int) -> String:
	var percent: int = [6, 8, 10, 11, 13, 14][clampi(level, 0, 5)]
	match Game.hero_class:
		"Priest": return P.localized("weapon_benefit_heal") % percent
		"Mage": return P.localized("weapon_benefit_charge") % [P.localized("class_mage_weapon"), percent]
		_: return P.localized("weapon_benefit_shield") % (3 if level >= 4 else (2 if level >= 2 else 1))

func _shop() -> void:
	_label(content, P.localized("shop_title"), 44, P.GOLD)
	var grid := GridContainer.new()
	grid.columns = 3
	content.add_child(grid)
	for item in shop.get("products", []):
		var panel := _panel(grid, 535)
		_label(panel, P.product_name(item.kind), 30)
		var payload: Variant = item.get("payload", {})
		if payload is Dictionary and payload.has("cardId"):
			var card_id := str(payload.cardId)
			_label(panel, CardDetails.localized_name(card_id, cards.get(card_id, {})), 26, P.TEAL)
		_label(panel, P.localized("shop_price") % item.priceGold, 36, P.GOLD)
		_label(panel, P.localized("shop_purchase_count") % [item.purchased, item.limit], 22, P.MUTED)
		_button(panel, P.localized("activated") if item.get("alreadyOwned", false) else P.localized("buy"), func(): _confirm(P.localized("ui_buy_confirm") % item.priceGold, func(): _complete_shop_purchase(item)), Game.busy or item.get("alreadyOwned", false) or int(item.purchased) >= int(item.limit) or int(item.priceGold) > int(Game.lobby.wallet.gold))
	if shop.get("products", []).is_empty(): _label(content, P.localized("no_products_later"), 28)

func _market() -> void:
	_label(content, P.localized("market_title"), 44, P.GOLD)
	_label(content, P.localized("market_terms"), 24, P.MUTED)
	for listing in listings:
		var row := _row(_panel(content))
		_label(row, P.localized("equipment_name_prefix") + str(listing.equipmentId).left(8), 25)
		_label(row, P.localized("shop_price") % listing.priceGold, 32, P.GOLD)
		if listing.sellerId == Game.lobby.player.userId:
			_label(row, P.localized("ui_seller_receives") % (int(listing.priceGold) - maxi(1, int(int(listing.priceGold) / 10.0))), 22)
			_button(row, P.localized("remove_listing"), func(): _mutate("/market/listings/" + listing.listingId, HTTPClient.METHOD_DELETE), Game.busy)
		else:
			_button(row, P.localized("buy"), func(): _confirm(P.localized("ui_buy_equipment_confirm") % listing.priceGold, func(): _mutate("/market/" + listing.listingId + "/purchase?expectedVersion=" + str(int(listing.version)), HTTPClient.METHOD_POST)), Game.busy or int(listing.priceGold) > int(Game.lobby.wallet.gold))
	if listings.is_empty(): _label(content, P.localized("no_listings"), 28, P.MUTED)
	_label(content, P.localized("select_item_to_list"), 32)
	for item in inventory.get("equipments", []):
		if item.get("isBound", false) or item.get("location") != "Inventory": continue
		var row := _row(content)
		_label(row, _equipment_name(item))
		var price := SpinBox.new()
		price.min_value = 1
		price.max_value = 100000000
		price.value = 100
		row.add_child(price)
		_button(row, P.localized("list_for_sale"), func(): _confirm(P.localized("confirm_listing_price") % int(price.value), func(): _mutate("/market/listings", HTTPClient.METHOD_POST, {"equipmentId": item.instanceId, "priceGold": int(price.value)})), Game.busy)

func _mutate(path: String, method: int, body: Variant = null) -> void:
	if Game.busy: return
	Game.busy = true
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1" + path, method, body)
	if not _session_result_current(generation, result): return
	if result.ok:
		_apply_account_mutation(path, body, result.data)
		var cue := "equip"
		if path.ends_with("/enhance"): cue = "upgrade"
		elif path == "/shop/purchases" or path.contains("/purchase?"): cue = "purchase"
		Sound.play_cue(cue)
		_toast(P.localized("operation_success"))
	else:
		Sound.play_cue("error")
		if path.begins_with("/market/"): Game.refresh_cache("market")
		elif path.begins_with("/loadouts/"): Game.refresh_cache("inventory")
	Game.busy = false
	_render()

func _apply_account_mutation(path: String, body: Variant, response: Variant) -> void:
	var data: Dictionary = response if response is Dictionary else {}
	if path.begins_with("/loadouts/") and not data.is_empty():
		var loadouts: Array = Game.lobby.get("equippedLoadouts", []).duplicate(true)
		for index in loadouts.size():
			if str(loadouts[index].get("heroClass", "")) == str(data.get("heroClass", "")):
				loadouts[index] = data
				break
		Game.update_cache("equippedLoadouts", loadouts)
		gear_draft = data.get("equipmentIds", []).duplicate()
		Game.refresh_cache("inventory")
	elif path.ends_with("/enhance") and data.get("equipment") is Dictionary:
		var equipment: Dictionary = data.equipment
		var materials: Dictionary = Game.lobby.get("materials", {}).duplicate(true)
		materials["equipmentFragments"] = int(data.get("equipmentFragments", materials.get("equipmentFragments", 0)))
		Game.update_cache("materials", materials)
		if str(equipment.get("slot", "")) == "ClassWeapon":
			var weapons: Array = Game.lobby.get("classWeapons", []).duplicate(true)
			for index in weapons.size():
				if str(weapons[index].get("heroClass", "")) == Game.hero_class:
					weapons[index]["level"] = equipment.get("level", weapons[index].get("level", 0))
					weapons[index]["version"] = equipment.get("version", weapons[index].get("version", 0))
					break
			Game.update_cache("classWeapons", weapons)
		else:
			var items: Array = inventory.get("equipments", []).duplicate(true)
			for index in items.size():
				if str(items[index].get("instanceId", "")) == str(equipment.get("instanceId", "")):
					items[index] = equipment
					break
			var consumed := str(data.get("consumedMaterialEquipmentId", ""))
			if not consumed.is_empty(): items = items.filter(func(item): return str(item.get("instanceId", "")) != consumed)
			_set_inventory_items(items)
	elif path == "/market/listings" and not data.is_empty():
		var equipment_id := str(data.get("equipmentId", ""))
		var items: Array = inventory.get("equipments", []).duplicate(true)
		var listing: Dictionary = data.duplicate(true)
		for item in items:
			if str(item.get("instanceId", "")) == equipment_id:
				listing["equipment"] = item.duplicate(true)
				listing.equipment["location"] = "MarketListed"
				break
		if not listing.has("equipment"):
			for existing in listings:
				if str(existing.get("listingId", "")) == str(listing.get("listingId", "")):
					listing["equipment"] = existing.get("equipment", {})
					break
		items = items.filter(func(item): return str(item.get("instanceId", "")) != equipment_id)
		_set_inventory_items(items)
		var updated: Array = listings.duplicate(true)
		updated = updated.filter(func(entry): return str(entry.get("listingId", "")) != str(listing.get("listingId", "")))
		updated.push_front(listing)
		Game.update_cache("market", updated)
	elif path.begins_with("/market/"):
		var listing_id := ""
		if path.begins_with("/market/listings/"):
			listing_id = path.trim_prefix("/market/listings/").split("/")[0]
		else:
			listing_id = path.trim_prefix("/market/").split("/")[0]
		var previous: Dictionary = {}
		for listing in listings:
			if str(listing.get("listingId", "")) == listing_id:
				previous = listing
				break
		var updated: Array = listings.filter(func(entry): return str(entry.get("listingId", "")) != listing_id)
		Game.update_cache("market", updated)
		if data.has("buyerGoldAfter"):
			var wallet: Dictionary = Game.lobby.get("wallet", {}).duplicate(true)
			wallet["gold"] = int(data.buyerGoldAfter)
			Game.update_cache("wallet", wallet)
		var item: Dictionary = previous.equipment if previous.get("equipment") is Dictionary else {}
		if not item.is_empty():
			item = item.duplicate(true)
			item["location"] = "Inventory"
			item["version"] = int(item.get("version", 0)) + 1
			var items: Array = inventory.get("equipments", []).duplicate(true)
			items.append(item)
			_set_inventory_items(items)
		else:
			Game.refresh_cache("inventory")
func _set_inventory_items(items: Array) -> void:
	var next_inventory: Dictionary = inventory.duplicate(true)
	next_inventory["equipments"] = items
	var summary: Dictionary = next_inventory.get("summary", {}).duplicate(true)
	var count := 0
	for item in items:
		if str(item.get("location", "")) == "Inventory": count += 1
	summary["equipmentCount"] = count
	summary["freeSlots"] = maxi(0, int(summary.get("capacity", 50)) - count)
	next_inventory["summary"] = summary
	Game.update_cache("inventory", next_inventory)

func _purchase_shop_item(item: Dictionary, product_title: String) -> void:
	var purchase := func(): _complete_shop_purchase(item)
	if item.get("kind", "") == "Cards":
		_confirm(P.localized("ui_buy_named_confirm") % [item.get("priceGold", 0), product_title], purchase)
	else:
		purchase.call()

func _refresh_shop() -> void:
	if Game.busy: return
	Game.busy = true
	var generation: int = Game.gateway.session_generation
	var result: Dictionary = await Game.gateway.request("/api/v1/shop/refresh", HTTPClient.METHOD_POST, {})
	if not _session_result_current(generation, result): return
	if result.ok:
		shop = result.data
		Game.update_cache("shop", shop)
		Sound.play_cue("reward")
		_toast(P.localized("ui_shop_refreshed"))
	else:
		Sound.play_cue("error")
		_toast(result.error)
	Game.busy = false
	_render()

func _complete_shop_purchase(item: Dictionary) -> void:
	if Game.busy: return
	Game.busy = true
	var generation: int = Game.gateway.session_generation
	var product_id: String = str(item.get("productId", ""))
	var result: Dictionary = await Game.gateway.request("/api/v1/shop/purchases", HTTPClient.METHOD_POST, {"productId": product_id, "quantity": 1})
	if not _session_result_current(generation, result): return
	if result.ok:
		_shop_purchase_product_id = product_id
		_apply_shop_purchase(product_id, result.data)
		_shop_purchase_product_id = ""
		Sound.play_cue("purchase")
		_toast(P.localized("operation_success"))
	else:
		Sound.play_cue("error")
	Game.busy = false
	if screen == "shop" and is_instance_valid(_reference):
		if not bool(_reference.call("sync_shop_state", product_id)): _render()

func _restore_shop_scroll(scroll: ScrollContainer) -> void:
	await get_tree().process_frame
	if not is_instance_valid(scroll) or screen != "shop" or not is_instance_valid(_reference): return
	if _reference.get_node_or_null("ShopScroll") != scroll: return
	scroll.scroll_horizontal = _shop_scroll
	scroll.get_h_scroll_bar().value_changed.connect(func(value: float):
		if is_instance_valid(_reference) and _reference.get_node_or_null("ShopScroll") == scroll:
			_shop_scroll = int(value))

func _apply_shop_purchase(product_id: String, response: Dictionary) -> void:
	var quantity: int = int(response.get("quantity", 1))
	var products: Array = shop.get("products", [])
	for index in products.size():
		var product: Dictionary = products[index]
		if str(product.get("productId", "")) != product_id: continue
		product["purchased"] = int(product.get("purchased", 0)) + quantity
		if product.get("kind", "") == "Cards" and product.get("payload") is Dictionary and product.payload.has("cardId"):
			product["alreadyOwned"] = true
		products[index] = product
		var kind: String = str(product.get("kind", ""))
		var parsed: Variant = product.get("payload", {})
		var payload: Dictionary = parsed if parsed is Dictionary else {}
		var amount: int = int(payload.get("amount", 1)) * quantity
		if kind in ["AdvancedBag", "TopBag", "HealthPotion"]:
			var consumables: Dictionary = inventory.get("consumables", {}).duplicate()
			var key: String = {"AdvancedBag": "advancedBagCount", "TopBag": "topBagCount", "HealthPotion": "healthPotionCount"}[kind]
			consumables[key] = int(consumables.get(key, 0)) + amount
			inventory["consumables"] = consumables
			Game.update_cache("inventory", inventory)
		elif kind in ["WarriorSoul", "EquipmentFragments", "ClassSoul"]:
			var materials: Dictionary = Game.lobby.get("materials", {}).duplicate(true)
			var key := kind.left(1).to_lower() + kind.substr(1)
			if kind == "ClassSoul": key = str(payload.get("heroClass", "")).to_lower() + "Soul"
			materials[key] = int(materials.get(key, 0)) + amount
			Game.update_cache("materials", materials)
		elif kind == "Cards":
			Game.refresh_cache("cards")
		break
	shop["products"] = products
	Game.update_cache("shop", shop)
	var wallet: Dictionary = Game.lobby.get("wallet", {}).duplicate()
	wallet["gold"] = int(response.get("goldAfter", wallet.get("gold", 0)))
	Game.update_cache("wallet", wallet)

func _session_result_current(generation: int, result: Dictionary = {}) -> bool:
	return generation == Game.gateway.session_generation and not result.get("stale_session", false)

func _confirm(message: String, action: Callable, options: Dictionary = {}) -> void:
	if get_node_or_null("ConfirmationModal") != null: return
	var dialog := ConfirmationModalScene.instantiate()
	add_child(dialog)
	dialog.configure(message, action, options)

func _room() -> void:
	var state: Dictionary = Game.room
	var player: Dictionary = state.get("player", {})
	var combat: Dictionary = player.get("combat", {})
	var row := _row(content)
	_label(row, P.localized("chaos_realm_prefix") + P.word(player.get("phase", "")), 38, P.GOLD)
	_label(row, P.localized("combat_health_shield_summary") % [combat.get("hp", 0), combat.get("maximum_hp", 0), combat.get("shield", 0)], 28)
	if Game.has_pending_commands(): _label(row, P.localized("ui_operation_pending"), 24, P.TEAL)
	_button(row, P.localized("sync"), Game.refresh_room_snapshot)
	if player.get("phase", "") in ["Pve", "Pvp"]:
		_button(row, P.localized("battle_exit"), func(): _confirm(
			P.localized("battle_abandon_warning"),
			func(): Game.command("battle.abandon"),
			{"title": P.localized("battle_abandon_title"), "confirm_text": P.localized("battle_abandon_confirm"), "cancel_text": P.localized("cancel"), "tall": true}),
			not Game.allowed("battle.abandon"))
		_battle(state)
	elif state.has("reward_choice"):
		_rewards(state.reward_choice)
	else:
		_map(state)
		_action_bar(state)
	for key in ["extraction_remaining_ms", "spring_remaining_ms"]:
		if state.has(key): _label(content, (P.localized("extracting_prefix") if key.begins_with("extraction") else P.localized("drinking_spring_prefix")) + P.localized("seconds_decimal") % (float(state[key]) / 1000.0), 32, P.TEAL)

func _battle(state: Dictionary) -> void:
	var stage := _row(content)
	var hero := _panel(stage, 560)
	hero.add_theme_constant_override("separation", 8)
	_combat_panels[state.player.player_id] = hero.get_parent()
	_label(hero, P.CLASSES.get(state.player.hero_class, P.CLASSES.Mage)[0], 32)
	Art.image(hero, Art.portrait(state.player.hero_class), Vector2(120, 110))
	_health_bar(hero, state.player.combat)
	if state.has("duel"):
		var opponent := _panel(stage, 900)
		_combat_panels[state.duel.opponent_id] = opponent.get_parent()
		_label(opponent, P.localized("same_cell_traveler"), 42, P.GOLD)
		_health_bar(opponent, state.duel.opponent)
		_label(opponent, P.localized("ui_hp_shield") % [state.duel.opponent.hp, state.duel.opponent.maximum_hp, state.duel.opponent.shield], 28)
		if Game.allowed("duel.leave"): _button(opponent, P.localized("leave_duel"), func(): Game.command("duel.leave", {"duel_id": state.duel.duel_id}))
		if Game.allowed("duel.escape"): _button(opponent, P.localized("force_escape"), func(): Game.command("duel.escape", {"duel_id": state.duel.duel_id}))
		if state.duel.has("escape_remaining_ms"): _label(opponent, P.localized("ui_escape_progress") % (float(state.duel.escape_remaining_ms) / 1000.0))
	else:
		var monsters: Array = state.get("pve", {}).get("monsters", [])
		var alive_monster_count := 0
		for monster in monsters:
			if int(monster.hp) > 0: alive_monster_count += 1
		var multiple_monsters: bool = alive_monster_count > 1
		for monster in monsters:
			var enemy := _panel(stage, 420)
			enemy.add_theme_constant_override("separation", 8)
			_combat_panels[monster.monster_id] = enemy.get_parent()
			var portrait := Art.image(enemy, Art.monster(monster.monster_id), Vector2(110, 90))
			if portrait.texture == null:
				portrait.custom_minimum_size.y = 40
				_label(enemy, _monster_name(monster.monster_id), 28, P.MUTED)
			_label(enemy, P.localized("combat_health_short_shield") % [monster.hp, monster.maximum_hp, monster.shield], 20)
			_health_bar(enemy, monster)
			if multiple_monsters and int(monster.hp) > 0:
				var button := _button(enemy, _monster_name(monster.monster_id) + (P.localized("current_target_suffix") if Game.combat_target_id() == monster.monster_id else P.localized("choose_target_suffix")), func(): Game.command("battle.select_target", {"battle_id": state.pve.battle_id, "target_id": monster.monster_id}), not Game.allowed("battle.select_target"), "UI/CardCodex/card_codex_action_button_orange.png")
				button.custom_minimum_size.y = 60
			var intent: String = {"Charge": P.localized("charge_intent"), "Empower": P.localized("empower"), "Shield": P.localized("word_shield")}.get(monster.intent_kind, P.word(monster.intent_element))
			_label(enemy, P.localized("ui_intent_value") % [intent, monster.intent_value if int(monster.intent_value) > 0 else ""], 23, P.ELEMENT.get(monster.intent_element, Color.WHITE))
	var charge := BoundedBar.new()
	charge.name = "DrawChargeBar"
	charge.configure("UI/Battle/battle_energy_cell_lit.png", "UI/Battle/battle_energy_cell_unlit.png")
	charge.max_value = 1.0
	charge.value = _draw_charge_value(float(state.player.get("draw_charge", "0")))
	charge.custom_minimum_size.y = 16
	content.add_child(charge)
	_label(content, P.localized("ui_combat_hand_hint") % Game.selected_cards.size(), 22, P.MUTED)
	var hand := _row(content)
	hand.alignment = BoxContainer.ALIGNMENT_CENTER
	for index in range(5):
		if index < state.player.hand.size():
			var card: Dictionary = state.player.hand[index]
			var button := _card_button(hand, card.card_id, func(): Game.toggle_card(card.instance_id), card.instance_id in Game.selected_cards, not Game.allowed("battle.play_cards"))
			button.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		else:
			var empty := _button(hand, "", func(): pass, true)
			Art.button(empty, "UI/Codex/qframe_common.png")
			empty.custom_minimum_size = Vector2(218, 376)
			empty.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	var play := _button(hand, P.localized("play"), Game.play_cards, Game.selected_cards.is_empty() or not Game.allowed("battle.play_cards"))
	Art.button(play, "UI/Battle/battle_play_button.png")
	play.custom_minimum_size = Vector2(100, 100)
	play.size_flags_vertical = Control.SIZE_SHRINK_CENTER

func _map(state: Dictionary) -> void:
	var row := _row(content)
	var grid := GridContainer.new()
	grid.columns = 6
	row.add_child(grid)
	var cells := CellIndex.by_position(state.get("map", []))
	var moves := CellIndex.by_position(state.get("legal_moves", []))
	for y in range(6):
		for x in range(6):
			var pos := Vector2i(y, x)
			var cell: Dictionary = cells.get(pos, {})
			var text := ""
			if cell.get("is_boss", false): text = P.localized("boss")
			elif cell.get("has_spring", false): text = P.localized("spring")
			var current: bool = state.get("self", {}).get("row", -1) == y and state.get("self", {}).get("column", -1) == x
			if current: text += P.localized("self_newline")
			var legal: bool = moves.has(pos)
			var button := _button(grid, text, _move.bind(y, x), not legal or not Game.allowed("room.move"))
			button.custom_minimum_size = Vector2(148, 88)
			var layer: int = mini(mini(x, y), mini(5 - x, 5 - y))
			button.add_theme_stylebox_override("disabled", P.box([Color("243e40"), Color("3b4842"), Color("594d3e")][layer], P.GOLD if current else Color("486368"), 3 if current else 1))
	var side := _panel(row, 630)
	_label(side, P.localized("enter_chaos"), 38, P.GOLD)
	_label(side, P.localized("map_legend"), 26, P.TEAL)
	_label(side, P.localized("ui_map_discovery_hint"), 24, P.MUTED)
	_label(side, P.localized("bag"), 30)
	for item in state.get("player", {}).get("inventory", []):
		_label(side, "%s ×%s%s" % [P.word(item.kind), item.quantity, P.localized("safe_suffix") if item.is_safe else ""], 22)

func _monster_name(id: String) -> String:
	var keys := {"fire-bat": "monster_fire_bat", "thorn-mite": "monster_thorn_mite", "murk-snail": "monster_murk_snail", "sand-lizard": "monster_sand_lizard", "rust-rat": "monster_rust_rat", "metal-guard": "monster_metal_guard", "fire-herald": "monster_fire_herald", "marsh-mother": "monster_marsh_mother", "stone-guard": "monster_stone_guard", "thorn-guard": "monster_thorn_guard", "annihilation-core": "monster_annihilation_core", "box-spirit": "monster_box_spirit", "treasure-box-spirit": "monster_box_spirit"}
	var normalized_id := id.trim_suffix("-a").trim_suffix("-b")
	var key: String = keys.get(normalized_id, "")
	return P.localized(key) if not key.is_empty() else id

func _move(row: int, column: int) -> void:
	var layer: int = mini(mini(row, column), mini(5 - row, 5 - column))
	var id: String = Game.room.get("room_id", "")
	if layer > 0 and not _midlayer_seen.has(id):
		set_meta("pending_move", Vector2i(row, column))
		_render()
	else: Game.command("room.move", {"row": row, "column": column})

func _action_bar(_state: Dictionary) -> void:
	var row := _row(content)
	for action in {"action.spring": P.localized("drink_spring"), "action.potion": P.localized("use_health_potion"), "action.extract": P.localized("extract")}:
		if Game.allowed(action):
			_button(row, {"action.spring": P.localized("drink_spring"), "action.potion": P.localized("use_health_potion"), "action.extract": P.localized("extract")}[action], func(): Game.command(action))

func _rewards(reward: Dictionary) -> void:
	_label(content, P.localized("choose_reward"), 46, P.GOLD)
	var row := _row(content)
	for option in reward.get("options", []):
		var panel := _panel(row, 510)
		var index := int(option.kind)
		_label(panel, {1: P.localized("word_equipment"), 2: P.localized("word_equipment_fragments"), 3: P.localized("exploration_heal_reward")}.get(index, P.localized("loot")), 38)
		_label(panel, P.localized("ui_combat_hp_percent") % option.heal_percent if index == 3 else P.localized("ui_quantity") % option.quantity, 28, P.TEAL)
		_button(panel, P.localized("select"), func(): _claim(option), not Game.allowed("reward.choice.claim"))
	var count := int(reward.get("refresh_count", 0))
	if count < 3:
		_button(content, P.localized("ui_refresh_remaining") % [[60, 180, 450][count], 3 - count], func(): Game.command("reward.choice.refresh"), not Game.allowed("reward.choice.refresh"))

func _claim(option: Dictionary, equip: bool = false) -> void:
	var player: Dictionary = Game.room.get("player", {})
	var items: Array = player.get("inventory", [])
	var reward_item := {"kind": "Equipment" if int(option.kind) == 1 else "EquipmentFragments", "item_id": option.get("item_id", "")}
	var payload := {"option_id": option.option_id, "equip": equip}
	if not equip and int(option.kind) != 3 and not InventoryView.can_add(player, reward_item):
		var dialog := AcceptDialog.new()
		dialog.title = P.localized("bag_full_replace")
		var scroll := ScrollContainer.new()
		scroll.custom_minimum_size = Vector2(720, 460)
		dialog.add_child(scroll)
		var column := VBoxContainer.new()
		column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		scroll.add_child(column)
		for item in items:
			_button(column, "%s ×%s%s" % [EquipmentDetails.title(item), item.quantity, P.localized("safe_slot_suffix") if item.get("is_safe", false) else ""], func():
				dialog.queue_free()
				_confirm(P.localized("recycle_for_loot") % EquipmentDetails.title(item), func(): payload.replace_item_id = item.item_id; Game.command("reward.choice.claim", payload)))
		add_child(dialog)
		dialog.confirmed.connect(dialog.queue_free)
		dialog.popup_centered(Vector2i(750, 550))
	elif equip:
		_confirm(P.localized("direct_equip_recycle"), func(): Game.command("reward.choice.claim", payload))
	else: Game.command("reward.choice.claim", payload)

func _settlement() -> void:
	_label(content, P.word(Game.settlement.get("result", P.localized("journey_end"))), 66, P.GOLD)
	_label(content, P.localized("settlement_synced"), 30)
	var details: Dictionary = Game.settlement.details if Game.settlement.get("details") is Dictionary else {}
	for key in ["gold", "goldEarned", "equipmentFragments", "warriorSoul"]:
		if details.has(key): _label(content, "%s  %s" % [P.word(key), details[key]], 30)
	_button(content, P.localized("back"), _return_from_settlement, Game.busy)

func _return_from_settlement() -> void:
	Game.acknowledge_settlement()
	_navigate("hall")

func _notice_anchor() -> float:
	# Battle headers contain Guardian remainder and separate-loot controls.
	if str(Game.room.get("player", {}).get("phase", "")) in ["Pve", "Pvp"]:
		return TipsOverlay.VIEWPORT_Y_RATIO
	# Action HP and action information occupy the default notice height.
	return 0.09 if not Game.room.is_empty() or not Game.settlement.is_empty() else TipsOverlay.VIEWPORT_Y_RATIO

func _notice_width_ratio() -> float:
	return TipsOverlay.COMBAT_MAX_WIDTH_RATIO if str(Game.room.get("player", {}).get("phase", "")) in ["Pve", "Pvp"] else TipsOverlay.MAX_WIDTH_RATIO

func _toast(message: String) -> void:
	if is_instance_valid(tips_overlay):
		tips_overlay.show_tip(message, _notice_anchor(), _notice_width_ratio())

func _show_ban_dialog(reason: String) -> void:
	var ban := RemoteCopy.account_ban(reason)
	if ban.is_empty(): return
	var dialog := AcceptDialog.new()
	dialog.name = "AccountBanDialog"
	dialog.title = P.localized("ui_account_banned")
	dialog.theme = P.theme()
	dialog.get_ok_button().text = P.localized("confirm")
	dialog.dialog_text = P.localized("ui_account_banned")
	if not str(ban.reason).is_empty(): dialog.dialog_text += "\n" + str(ban.reason)
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	add_child(dialog)
	dialog.popup_centered(Vector2i(700, 360))

func _health_bar(parent: Node, combat: Dictionary) -> void:
	var bar := BoundedBar.new()
	bar.configure("UI/Encounter/encounter_hp_fill_normal.png", "UI/Encounter/encounter_hp_track_normal.png")
	bar.max_value = maxf(1, float(combat.get("effective_maximum_hp", combat.get("maximum_hp", 1))))
	bar.value = float(combat.get("hp", 0))
	bar.custom_minimum_size.y = 20
	parent.add_child(bar)
	if int(combat.get("shield", 0)) > 0:
		var shield := BoundedBar.new()
		shield.configure_solid(Color("102128"), Color("c4d2d4"))
		shield.max_value = bar.max_value
		shield.value = float(combat.shield)
		shield.custom_minimum_size.y = 8
		parent.add_child(shield)

func _feedback(payload: Dictionary) -> void:
	var context := _current_combat_feedback_context()
	if context.is_empty() or context != _combat_feedback_context: return
	# Preview invalidation queues a view rebuild after this signal. Let that
	# render finish, then animate the current controls for the captured owner.
	var owned_payload := payload.duplicate(true)
	await get_tree().process_frame
	_play_combat_feedback(owned_payload, context)

func _play_combat_feedback(payload: Dictionary, context: Array) -> void:
	if not is_inside_tree() or is_queued_for_deletion(): return
	if context != _current_combat_feedback_context() or context != _combat_feedback_context: return
	var target: Control = _combat_panels.get(payload.get("target_id", ""))
	if is_instance_valid(target):
		_hit_reaction(target)
		var index := 0
		for segment in payload.get("damage_segments", []):
			if int(segment.get("amount", 0)) <= 0: continue
			var kind := str(segment.get("kind", "Direct"))
			_float_number(target, "%s %s" % [P.localized("direct_damage_badge") if _is_direct_damage(kind) else P.word(kind), segment.get("amount", 0)], _damage_color(kind), index)
			index += 1
	var source_id: String = payload.get("source_id", "")
	if source_id.is_empty(): source_id = payload.get("attacker_id", "")
	var source: Control = _combat_panels.get(source_id)
	if is_instance_valid(source):
		_attack_reaction(source, target if is_instance_valid(target) else null)
		for key in ["heal", "shield_gain"]:
			if int(payload.get(key, 0)) <= 0: continue
			_float_number(source, "+%s" % payload[key], P.TEAL if key == "heal" else Color("c4d2d4"), 0 if key == "heal" else 1)

func _is_direct_damage(kind: String) -> bool:
	return kind.to_lower() in ["direct", "none", ""]

func _damage_color(kind: String) -> Color:
	if _is_direct_damage(kind): return P.DIRECT_DAMAGE
	for element in P.ELEMENT:
		if str(element).to_lower() == kind.to_lower(): return P.ELEMENT[element]
	return P.DIRECT_DAMAGE

func _reaction_base(node: Control) -> Dictionary:
	if not node.has_meta("combat_base_position"):
		node.set_meta("combat_base_position", node.position)
	if not node.has_meta("combat_base_scale"):
		node.set_meta("combat_base_scale", node.scale)
	if not node.has_meta("combat_base_modulate"):
		node.set_meta("combat_base_modulate", node.modulate)
	var previous: Variant = node.get_meta("combat_reaction_tween") if node.has_meta("combat_reaction_tween") else null
	if previous is Tween and previous.is_running(): previous.kill()
	var base_position: Vector2 = node.get_meta("combat_base_position")
	var base_scale: Vector2 = node.get_meta("combat_base_scale")
	var base_modulate: Color = node.get_meta("combat_base_modulate")
	node.position = base_position
	node.scale = base_scale
	node.modulate = base_modulate
	node.pivot_offset = node.size / 2.0
	return {"position": base_position, "scale": base_scale, "modulate": base_modulate}

func _hit_reaction(node: Control) -> void:
	var base := _reaction_base(node)
	var position: Vector2 = base.position
	var scale: Vector2 = base.scale
	var normal: Color = base.modulate
	var red := Color(1.0, 0.28, 0.24, normal.a)
	var tween := node.create_tween()
	node.set_meta("combat_reaction_tween", tween)
	tween.tween_property(node, "position", position + Vector2(0, -18), 0.08).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tween.parallel().tween_property(node, "scale", scale * 0.97, 0.08)
	tween.parallel().tween_property(node, "modulate", red, 0.06)
	tween.tween_property(node, "position", position + Vector2(0, 7), 0.07).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN_OUT)
	tween.parallel().tween_property(node, "modulate", red.lightened(0.12), 0.07)
	tween.tween_property(node, "position", position + Vector2(0, -4), 0.06).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tween.parallel().tween_property(node, "scale", scale * 0.99, 0.06)
	tween.tween_property(node, "position", position, 0.13).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN_OUT)
	tween.parallel().tween_property(node, "scale", scale, 0.13)
	tween.parallel().tween_property(node, "modulate", normal, 0.16)

func _attack_reaction(node: Control, target: Control) -> void:
	var base := _reaction_base(node)
	var position: Vector2 = base.position
	var scale: Vector2 = base.scale
	var direction := 1.0
	if is_instance_valid(target) and target.global_position.x < node.global_position.x: direction = -1.0
	var toward := Vector2(28.0 * direction, 0)
	var recoil := Vector2(-15.0 * direction, 0)
	var tween := node.create_tween()
	node.set_meta("combat_reaction_tween", tween)
	tween.tween_property(node, "position", position + toward, 0.11).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tween.parallel().tween_property(node, "scale", scale * 1.04, 0.11)
	tween.tween_property(node, "position", position + recoil, 0.07).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN_OUT)
	tween.parallel().tween_property(node, "scale", scale * 0.98, 0.07)
	tween.tween_property(node, "position", position + Vector2(7.0 * direction, 0), 0.06).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tween.parallel().tween_property(node, "scale", scale * 1.02, 0.06)
	tween.tween_property(node, "position", position, 0.14).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN_OUT)
	tween.parallel().tween_property(node, "scale", scale, 0.14)

func _float_number(node: Control, value: String, tint: Color, index: int) -> void:
	var number := _label(self, value, 42, tint)
	number.add_theme_font_override("font", P.font("number"))
	number.name = "CombatNumber"
	number.set_meta("combat_float", true)
	number.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	number.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var actor_to_ui := get_global_transform_with_canvas().affine_inverse() * node.get_global_transform_with_canvas()
	var ui_scale := maxf(0.1, minf(absf(actor_to_ui.get_scale().x), absf(actor_to_ui.get_scale().y)))
	var base_scale := Vector2.ONE * ui_scale
	var text_width := P.font("number").get_string_size(value, HORIZONTAL_ALIGNMENT_LEFT, -1, 42).x
	number.size = Vector2(maxf(170.0, text_width + 16.0), 54)
	number.scale = base_scale
	var top: Vector2 = actor_to_ui * Vector2(node.size.x * 0.5, 0)
	var travel := 72.0 * ui_scale
	var margin := 12.0 * ui_scale
	var peak_size := number.size * ui_scale * 1.08
	var position := top + Vector2(-number.size.x * ui_scale * 0.5 + index * 32.0 * ui_scale, (maxf(98.0, node.size.y * 0.25) + index * 26.0) * ui_scale)
	position.x = clampf(position.x, margin, maxf(margin, size.x - peak_size.x - margin))
	position.y = clampf(position.y, travel + margin, maxf(travel + margin, size.y - peak_size.y - margin))
	number.position = position
	number.set_meta("combat_float_travel", travel)
	number.set_meta("combat_float_ui_scale", ui_scale)
	number.z_index = 20
	number.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var tween := number.create_tween().set_parallel(true)
	number.set_meta("combat_float_tween", tween)
	tween.tween_property(number, "position:y", position.y - travel, 0.78).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tween.tween_property(number, "scale", base_scale * 1.08, 0.1)
	tween.chain().tween_property(number, "scale", base_scale, 0.12)
	tween.parallel().tween_property(number, "modulate:a", 0.0, 0.78)
	tween.chain().tween_callback(number.queue_free)

func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo or Game.room.is_empty(): return
	if event.keycode >= KEY_1 and event.keycode <= KEY_5:
		var index: int = event.keycode - KEY_1
		var hand: Array = Game.room.get("player", {}).get("hand", [])
		if Game.allowed("battle.play_cards") and index < hand.size(): Game.toggle_card(hand[index].instance_id)
	elif event.keycode == KEY_SPACE: Game.play_cards()
	elif event.keycode == KEY_R: Game.refresh_room_snapshot()
