extends RefCounted

const Model = preload("res://ui/season_archive_model.gd")
var seasons: Array = []
var selected: Dictionary = {}
var section := "equipment"
var state: Dictionary = {}
var list_offset := 0
var list_next: Variant = null
var page_offset := 0
var page_next: Variant = null
var loading := false
var failed := false
var catalog_loading := false
var catalog_ready := false
var catalog_index: Dictionary = {}
var _epoch := 0
var _host: WeakRef

func attach(host: Control) -> void:
	_host = weakref(host)

func leave() -> void:
	_epoch += 1
	loading = false
	catalog_loading = false

func reset() -> void:
	leave()
	seasons = []; selected = {}; state = {}; catalog_index = {}
	list_offset = 0; list_next = null; page_offset = 0; page_next = null
	section = "equipment"; failed = false; catalog_ready = false

func _host_node() -> Control:
	return _host.get_ref() as Control if _host != null else null

func _current(generation: int, epoch: int, address: String) -> bool:
	var host := _host_node()
	return host != null and host.screen == "archive" and generation == Game.gateway.session_generation and epoch == _epoch and address == Game.gateway.base_url

func _render() -> void:
	var host := _host_node()
	if host != null: host._schedule_render()

func reload(offset: int = 0) -> void:
	if offset < 0 or offset > 1000000 or loading: return
	_epoch += 1
	var epoch := _epoch
	var generation: int = Game.gateway.session_generation
	var address: String = Game.gateway.base_url
	loading = true; failed = false; catalog_loading = false; _render()
	var response: Dictionary = await Game.gateway.request("/api/v1/season-archives?limit=20&offset=" + str(offset))
	if not _current(generation, epoch, address) or response.get("stale_session", false): return
	loading = false
	if not response.get("ok", false) or not Model.list_valid(response.get("data"), offset):
		failed = true; seasons = []; _render(); return
	seasons = response.data.items.duplicate(true); list_offset = offset; list_next = response.data.get("nextOffset")
	if selected.is_empty() and not seasons.is_empty():
		choose(0)
	else: _render()

func choose(index: int) -> void:
	if loading or index < 0 or index >= seasons.size(): return
	selected = seasons[index].duplicate(true)
	section = "equipment"; state = {}; page_offset = 0; page_next = null
	catalog_index = {}; catalog_ready = false
	load_page(0)

func choose_section(value: String) -> void:
	if loading or value not in Model.SECTIONS or selected.is_empty(): return
	section = value; state = {}; page_offset = 0; page_next = null
	load_page(0)

func load_page(offset: int = 0) -> void:
	if loading or selected.is_empty() or offset < 0 or offset > 1000000: return
	_epoch += 1
	var epoch := _epoch
	var generation: int = Game.gateway.session_generation
	var address: String = Game.gateway.base_url
	var source := selected.duplicate(true)
	var target := section
	loading = true; failed = false; catalog_loading = false; state = {}; _render()
	var path := "/api/v1/season-archives/" + str(source.seasonId).uri_encode() + "/" + target + "?limit=20&offset=" + str(offset)
	var response: Dictionary = await Game.gateway.request(path, HTTPClient.METHOD_GET, null, [404])
	if not _current(generation, epoch, address) or response.get("stale_session", false): return
	loading = false
	if not response.get("ok", false) or not Model.section_valid(response.get("data"), source, target, offset):
		failed = true; state = {}; _render(); return
	state = response.data.duplicate(true); selected = state.season.duplicate(true)
	page_offset = offset; page_next = state.get("nextOffset"); _render()
	if source.get("configVersion") is String and source.get("configSha256") is String and not catalog_ready:
		catalog_loading = true; _render()
		var index: Dictionary = await Game.read_historical_catalog(str(source.configVersion), str(source.configSha256))
		if not _current(generation, epoch, address): return
		catalog_loading = false
		catalog_ready = not index.is_empty()
		catalog_index = index if catalog_ready else {}
		_render()
