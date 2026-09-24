extends SceneTree

const CardPool = preload("res://ui/card_pool.gd")
const CardGridView = preload("res://ui/card_grid_view.gd")
var _clicks := 0
var _sound_hits := 0

class Host extends Control:
	var pool: Node
	func _card_button(parent: Node, id: String, callback: Callable, selected: bool = false, disabled: bool = false, options: Dictionary = {}) -> Button:
		return pool.acquire(parent, id, {"name": id, "quality": "White", "source": "Initial"}, "face", selected, disabled, options, callback)
	func release_card(card: Button) -> void:
		pool.release(card)
	func ensure_card_pool(required: int) -> bool:
		return pool.ensure_available(required)

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var errors: Array[String] = []
	var pool := CardPool.new()
	root.add_child(pool)
	var host := Host.new()
	host.pool = pool
	root.add_child(host)
	var first := Button.new()
	var callback := Callable(self, "_clicked")
	var card: Button = pool.acquire(first, "C01", {"name": "Card", "quality": "White", "source": "Initial"}, "face", false, false, {}, callback)
	card.pressed.connect(Callable(self, "_sound_clicked"))
	pool.release(card)
	var second := Button.new()
	var reused: Button = pool.acquire(second, "C01", {"name": "Card", "quality": "White", "source": "Initial"}, "face", false, false, {}, callback)
	if reused != card: errors.append("Same card must reuse the complete control tree")
	reused.pressed.emit()
	if _clicks != 1: errors.append("A reused card must have exactly one live click callback")
	if _sound_hits != 1: errors.append("Reuse must preserve shared click sound binding")
	pool.release(reused)
	first.free()
	second.free()
	pool.clear()
	var catalog: Dictionary = {}
	for i in range(100): catalog["warm-%s" % i] = {"name": "Warm", "quality": "White", "source": "Initial", "is_codex": true}
	pool.begin_prewarm(catalog, [], Callable(self, "_describe"))
	pool._process(0.0)
	if pool._idle.size() != pool.CREATE_PER_FRAME: errors.append("Login prewarm must build ten cards per frame")
	for i in range(4): pool._process(0.0)
	if pool._idle.size() != pool.BASELINE_CARDS: errors.append("Login prewarm must reach the initial 50-card baseline")
	var scroll := ScrollContainer.new()
	scroll.size = Vector2(800, 600)
	host.add_child(scroll)
	var grid := CardGridView.new()
	grid.columns = 4
	grid.add_theme_constant_override("v_separation", 42)
	scroll.add_child(grid)
	var entries: Array = []
	for i in range(220):
		entries.append({"id": "card-%s" % i, "callback": Callable(self, "_noop")})
	grid.configure(host, scroll, entries, 150.0)
	await process_frame
	await process_frame
	for i in range(4): grid._sync_visible()
	if grid.get_child_count() != 220: errors.append("All cards need stable scroll slots")
	if _mounted_count(grid) > 32 or _mounted_count(grid) == 0: errors.append("Only nearby cards should have complete controls")
	if grid._slots[0].get_child_count() == 0: errors.append("First row must be ready when the collection opens")
	scroll.scroll_vertical = 2400
	await process_frame
	for i in range(4): grid._sync_visible()
	if _mounted_count(grid) > 32 or _mounted_count(grid) == 0: errors.append("Scrolling must recycle old cards and mount the new visible rows")
	if grid._slots[0].get_child_count() != 0 or grid._slots[36].get_child_count() == 0:
		errors.append("Scroll position must control which card rows are mounted")
	if pool._all_cards.size() > pool.MAX_POOL_CARDS: errors.append("Card pool exceeded its configured limit")
	grid.clear_cards()
	if _mounted_count(grid) != 0: errors.append("Filtering must return every visible card to the pool")
	pool.clear()
	if not pool._idle.is_empty(): errors.append("Account switch must discard pooled cards")
	print({"ok": errors.is_empty(), "errors": errors})
	quit(0 if errors.is_empty() else 1)

func _mounted_count(grid: GridContainer) -> int:
	var result := 0
	for slot in grid._slots: result += slot.get_child_count()
	return result

func _clicked() -> void:
	_clicks += 1

func _sound_clicked() -> void:
	_sound_hits += 1

func _noop() -> void:
	pass

func _describe(_id: String) -> String:
	return "face"
