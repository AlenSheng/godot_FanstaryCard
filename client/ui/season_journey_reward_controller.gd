extends RefCounted

const Model = preload("res://ui/season_journey_reward_model.gd")
const P = preload("res://ui/palette.gd")
var rewards: Dictionary = {}
var source := ""
var hero := ""
var loading := false
var writing := false
var failed := false
var notice := ""
var reward_scroll := 0
var cosmetic_scroll := 0
var _host: WeakRef
var _epoch := 0
var _action := 0

func attach(host: Control) -> void:
	_host = weakref(host)

func leave() -> void:
	_epoch += 1
	loading = false

func reset() -> void:
	leave()
	_action += 1
	rewards = {}
	source = ""
	hero = ""
	writing = false
	failed = false
	notice = ""
	reward_scroll = 0
	cosmetic_scroll = 0

func _host_node() -> Control:
	return _host.get_ref() as Control if _host != null else null

func _render() -> void:
	var host := _host_node()
	if host != null:
		host._schedule_render()

func _account_scope() -> String:
	return JSON.stringify([Game.gateway.session_generation, Game.gateway.base_url, Game.lobby.get("player", {}).get("userId", "")])

func _current(scope: String, epoch: int) -> bool:
	var host := _host_node()
	return host != null and host.screen in ["journey_rewards", "cosmetics"] and scope == _account_scope() and epoch == _epoch

func open_rewards(season_id: String) -> void:
	var host := _host_node()
	if host == null or writing or Game.busy or season_id.is_empty():
		return
	if source != season_id:
		rewards = {}
		hero = ""
		reward_scroll = 0
	source = season_id
	host._navigate("journey_rewards")

func open_cosmetics() -> void:
	var host := _host_node()
	if host != null and not writing and not Game.busy:
		host._navigate("cosmetics")

func choose_hero(index: int) -> void:
	if writing or loading or Game.busy or index < 0 or index > Model.HEROES.size():
		return
	hero = "" if index == 0 else str(Model.HEROES[index - 1])
	_epoch += 1
	_render()

func inventory() -> Dictionary:
	var value: Variant = Game.lobby.get("cosmetics", {})
	return value if value is Dictionary and Model.valid_inventory(value) else {}

func reload() -> void:
	var host := _host_node()
	if host == null or host.screen not in ["journey_rewards", "cosmetics"] or loading or writing:
		return
	_epoch += 1
	var epoch := _epoch
	var scope := _account_scope()
	var page: String = host.screen
	var original := source
	loading = true
	failed = false
	_render()
	if page == "journey_rewards" and original.is_empty():
		loading = false
		failed = true
		_render()
		return
	var path := "/api/v1/cosmetics" if page == "cosmetics" else "/api/v1/season-journey/rewards?seasonId=" + original.uri_encode()
	var response: Dictionary = await Game.gateway.request(path)
	if not _current(scope, epoch) or response.get("stale_session", false):
		if epoch == _epoch:
			loading = false
		return
	loading = false
	var data: Dictionary = response.get("data", {}) if response.get("data") is Dictionary else {}
	var valid: bool = Model.valid_inventory(data) if page == "cosmetics" else Model.valid_rewards(data, original)
	if not response.get("ok", false) or not valid:
		failed = true
		if page == "journey_rewards":
			rewards = {}
		_render()
		return
	if page == "cosmetics":
		Game.update_cache("cosmetics", data)
	else:
		rewards = data
	_render()

func confirm_claim(reward: Dictionary) -> void:
	var host := _host_node()
	var body := Model.claim_body(reward, hero)
	if host == null or host.screen != "journey_rewards" or Game.busy or loading or writing or failed or body.is_empty() or rewards.get("state") not in ["Active", "Ended"]:
		return
	var captured := reward.duplicate(true)
	var chosen := hero
	var caption: String = P.localized("journey_confirm_class_claim") % [reward.level, P.localized("class_" + chosen.to_lower())] if reward.get("requiresClassChoice", false) else P.localized("journey_confirm_claim") % reward.level
	host._confirm(caption, _claim.bind(captured, body, chosen, _account_scope(), _epoch))

func _claim(captured: Dictionary, body: Dictionary, chosen: String, scope: String, epoch: int) -> void:
	if not _current(scope, epoch) or writing or loading or Game.busy or failed:
		return
	for row in rewards.get("rewards", []):
		if row == captured and Model.claim_body(row, chosen) == body:
			_write("/api/v1/season-journey/rewards/" + str(row.rewardId).uri_encode() + "/claim", HTTPClient.METHOD_POST, body, scope, epoch, row.duplicate(true), chosen)
			return

func select_cosmetic(slot: String, cosmetic_id: Variant) -> void:
	var host := _host_node()
	var owned := inventory()
	if host == null or host.screen != "cosmetics" or owned.is_empty() or Game.busy or loading or writing or failed or slot not in ["AvatarFrame", "CardBack", "Title"]:
		return
	if cosmetic_id != null:
		var matched := false
		for row in owned.owned:
			if row.cosmeticId == cosmetic_id and row.kind == slot:
				matched = true
		if not matched:
			return
	var body := {"slot": slot, "cosmeticId": cosmetic_id, "expectedVersion": owned.selection.version}
	_write("/api/v1/cosmetics/selection", HTTPClient.METHOD_PUT, body, _account_scope(), _epoch)

func _write(path: String, method: int, body: Dictionary, scope: String, epoch: int, expected: Dictionary = {}, chosen: String = "") -> void:
	if writing or Game.busy or scope != _account_scope():
		return
	_action += 1
	var action := _action
	writing = true
	notice = ""
	_render()
	var response: Dictionary = await Game.gateway.request(path, method, body)
	if action != _action:
		return
	if scope != _account_scope() or response.get("stale_session", false):
		writing = false
		return
	var valid: bool = response.get("ok", false)
	if not expected.is_empty():
		valid = valid and response.get("data") is Dictionary and Model.valid_claim(response.data, expected, chosen)
	else:
		var owned := {}
		for item in inventory().get("owned", []):
			owned[item.cosmeticId] = item.kind
		var field: String = {"AvatarFrame": "avatarFrameId", "CardBack": "cardBackId", "Title": "titleId"}.get(str(body.get("slot", "")), "")
		valid = valid and response.get("data") is Dictionary and Model.valid_selection(response.data, owned) and response.data.get(field) == body.get("cosmeticId") and int(response.data.get("version", -1)) >= int(body.get("expectedVersion", 0))
	# Current balances and permanent selections always come from fresh account
	# reads, even when a committed receipt was lost in transport.
	await Game.refresh_lobby()
	if action != _action:
		return
	writing = false
	if scope != _account_scope():
		return
	if _current(scope, epoch):
		notice = P.localized("operation_success" if valid else "journey_write_refresh")
		failed = false
		reload()
	else:
		_render()
		reload()

func save_reward_scroll(value: float) -> void:
	reward_scroll = int(value)

func save_cosmetic_scroll(value: float) -> void:
	cosmetic_scroll = int(value)
