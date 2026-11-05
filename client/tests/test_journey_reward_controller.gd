extends RefCounted

const Controller = preload("res://ui/season_journey_reward_controller.gd")
const Model = preload("res://ui/season_journey_reward_model.gd")
const StoreDependency = preload("res://state/game_store.gd")
const Http = preload("res://network/http_protocol.gd")
const Index = preload("res://data/catalog_index.gd")
const P = preload("res://ui/palette.gd")

class Host extends Control:
	var screen := "journey_rewards"
	var renders := 0
	var confirmation: Callable
	var confirmation_message := ""
	func _schedule_render() -> void:
		renders += 1
	func _confirm(message: String, action: Callable) -> void:
		confirmation_message = message
		confirmation = action
	func _navigate(value: String) -> void:
		screen = value

class Gateway extends Node:
	var session_generation := 1
	var base_url := "https://original.invalid"
	var token := "fixture"
	var room_id := ""
	var room_revision := 0
	var gated := ""
	var requests: Array = []
	var before: Dictionary = {}
	var after: Dictionary = {}
	var inventory: Dictionary = {}
	var final_inventory: Dictionary = {}
	var pack: Dictionary = {}
	var selection: Dictionary = {}
	var committed := false
	var selected := false
	var bootstrap_enabled := false
	signal released
	func request(path: String, method: int = HTTPClient.METHOD_GET, body: Variant = null, _quiet: Array = []) -> Dictionary:
		requests.append({"path": path, "method": method, "body": body.duplicate(true) if body is Dictionary else body})
		if not gated.is_empty() and path.begins_with(gated):
			await released
		if path == "/api/v1/bootstrap":
			if not bootstrap_enabled:
				return {"ok": false, "status": 503, "data": {}}
			return {"ok": true, "data": {"configVersion": Index.CATALOG.data.get("version", ""), "player": {"userId": "owner", "selectedClass": "Mage"}, "wallet": {}, "materials": {}, "mail": {"items": [], "unreadCount": 0}, "shop": {}, "market": [], "inventory": {}, "activePreparation": null}}
		if path == "/api/v1/cosmetics/selection":
			selected = true
			return {"ok": true, "data": selection.duplicate(true)}
		if path == "/api/v1/cosmetics":
			return {"ok": true, "data": (final_inventory if selected else inventory).duplicate(true)}
		if method == HTTPClient.METHOD_POST and path.ends_with("/claim"):
			committed = true
			return {"ok": true, "data": pack.duplicate(true)}
		if path.begins_with("/api/v1/season-journey/rewards"):
			return {"ok": true, "data": (after if committed else before).duplicate(true)}
		return {"ok": false, "status": 404, "data": {}}

func _read(name: String, path: String, method: int = HTTPClient.METHOD_GET) -> Dictionary:
	return Http.decode_response(Http.route(path, method), 200, PackedStringArray(["Content-Type: application/protobuf"]), FileAccess.get_file_as_bytes("res://tests/journey-reward-client/" + name + ".bin")).data

func _frames() -> void:
	await Game.get_tree().process_frame
	await Game.get_tree().process_frame

func run_test() -> Dictionary:
	var checks := {}
	Game.set_process(false)
	var original: Node = Game.gateway
	var gateway := Gateway.new()
	Game.add_child(gateway)
	Game.gateway = gateway
	Game._clear_authenticated_state()
	Game.lobby = {"player": {"userId": "owner"}}
	gateway.before = _read("before", "/api/v1/season-journey/rewards")
	gateway.after = _read("after", "/api/v1/season-journey/rewards")
	gateway.inventory = _read("inventory", "/api/v1/cosmetics")
	gateway.final_inventory = _read("final-inventory", "/api/v1/cosmetics")
	gateway.selection = _read("selection", "/api/v1/cosmetics/selection", HTTPClient.METHOD_PUT)
	var pack_row: Dictionary = gateway.before.rewards.filter(func(row): return row.level == 5)[0]
	gateway.pack = _read("pack", "/api/v1/season-journey/rewards/" + str(pack_row.rewardId) + "/claim", HTTPClient.METHOD_POST)
	var host := Host.new()
	Game.get_tree().root.add_child(host)
	var c := Controller.new()
	c.attach(host)
	c.source = gateway.before.seasonId
	# Let the store's existing deferred server-info read finish before request
	# counts are used to detect an unexpected claim or selection submission.
	await _frames()
	await c.reload()
	checks["source scoped read loads actual rewards"] = Model.valid_rewards(c.rewards, c.source) and not c.loading
	var before_count: int = gateway.requests.size()
	var soul: Dictionary = c.rewards.rewards.filter(func(row): return row.level == 3)[0]
	c.confirm_claim(soul)
	checks["class claim cannot auto choose current hero"] = not host.confirmation.is_valid() and gateway.requests.size() == before_count
	c.hero = "Mage"
	c.confirm_claim(soul)
	checks["chosen class requires explicit confirmation"] = host.confirmation.is_valid()
	checks["class confirmation uses full localized class name"] = host.confirmation_message.contains(P.localized("class_mage"))
	c.leave()
	host.confirmation.call()
	await _frames()
	checks["confirmation from old page cannot submit"] = gateway.requests.size() == before_count
	gateway.gated = "/api/v1/season-journey/rewards"
	c.rewards = {}
	c.reload()
	await _frames()
	gateway.base_url = "https://different.invalid"
	gateway.released.emit()
	await _frames()
	checks["origin swap rejects old response and releases loading"] = c.rewards.is_empty() and not c.loading
	gateway.base_url = "https://original.invalid"
	c.rewards = {}
	c.reload()
	await _frames()
	Game.lobby.player.userId = "different-owner"
	gateway.released.emit()
	await _frames()
	checks["account swap cannot adopt pending response"] = c.rewards.is_empty() and not c.loading
	Game.lobby.player.userId = "owner"
	gateway.gated = ""
	await c.reload()
	c.confirm_claim(pack_row)
	host.confirmation.call()
	await _frames()
	checks["claim uses original source only"] = gateway.requests.any(func(row): return row.method == HTTPClient.METHOD_POST and row.body == {"seasonId": c.source})
	checks["write reconciles authenticated account after receipt"] = gateway.requests.any(func(row): return row.path == "/api/v1/bootstrap")
	checks["write reloads authoritative committed states"] = c.rewards.rewards.filter(func(row): return row.state == "Claimed").size() == 6 and not c.writing
	checks["controller does not steal global busy ownership"] = not Game.busy
	host.screen = "cosmetics"
	c.leave()
	await c.reload()
	checks["owned inventory enters shared account cache"] = Model.valid_inventory(Game.lobby.cosmetics)
	before_count = gateway.requests.size()
	c.select_cosmetic("Title", "first-threshold")
	c.select_cosmetic("Title", "unowned")
	checks["wrong slot and unowned selections cannot submit"] = gateway.requests.size() == before_count
	c.select_cosmetic("AvatarFrame", "trail-seeker")
	await _frames()
	checks["selection sends authoritative version and reloads owner state"] = gateway.requests.any(func(row): return row.method == HTTPClient.METHOD_PUT and row.body == {"slot": "AvatarFrame", "cosmeticId": "trail-seeker", "expectedVersion": gateway.inventory.selection.version}) and Game.lobby.cosmetics.selection.avatarFrameId == "trail-seeker"
	gateway.gated = "/api/v1/cosmetics"
	Game.lobby.cosmetics = {}
	Game.refresh_cache("cosmetics")
	await _frames()
	gateway.base_url = "https://different.invalid"
	gateway.released.emit()
	await _frames()
	checks["shared cosmetic cache rejects old origin"] = Game.lobby.cosmetics.is_empty()
	gateway.base_url = "https://original.invalid"
	gateway.gated = ""
	gateway.bootstrap_enabled = true
	await Game.refresh_lobby()
	checks["bootstrap adopts validated own cosmetic state"] = Model.valid_inventory(Game.lobby.get("cosmetics", {})) and Game.lobby.cosmetics.selection.avatarFrameId == "trail-seeker"
	c.reset()
	checks["reset removes source and chosen class"] = c.rewards.is_empty() and c.source.is_empty() and c.hero.is_empty() and not c.writing
	host.queue_free()
	Game.gateway = original
	Game._clear_authenticated_state()
	gateway.queue_free()
	return {"ok": not checks.values().has(false), "checks": checks, "fixture_only": true, "actual_native_network": false}
