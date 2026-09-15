extends Node

var checks: Array = []
var output := "res://evidence/codex-live"
var started := Time.get_ticks_msec()
var finished := false

func _ready() -> void:
	Game.gateway.persist_session = false
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	Game.gateway.base_url = "http://127.0.0.1:5080"
	Game.gateway.device_id = "codex-economy-test-" + Game.gateway.new_id()
	_run.call_deferred()

func _process(_delta: float) -> void:
	if not finished and Time.get_ticks_msec() - started > 90000: _finish(false, "Live card integration timed out")

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	var login: Dictionary = await Game.gateway.request("/api/v1/auth/local", HTTPClient.METHOD_POST, {"deviceId": Game.gateway.device_id, "displayName": "图鉴联调-" + Game.gateway.new_id().left(12)})
	if not _check(login.ok, "Independent development account login"): return _finish(false)
	Game.gateway.token = login.data.accessToken
	await Game.refresh_lobby()
	await $UI._navigate("cards")
	if not _check($UI._codex_ready and $UI.owned.size() == 200, "Server returns all 200 cards with quotes"): return _finish(false)
	await _capture("collection")
	var card_id := "GW08"
	var cost: int = $UI._owned_card(card_id).craftCost
	_check(cost == 10, "White general card costs 10 warrior souls")
	# Use only cards belonging to this newly created test account to fund the craft.
	var spare_cards: Array = $UI.owned.filter(func(card): return card.canDismantle and card.currencyKind == "WarriorSoul")
	for spare in spare_cards:
		if $UI._card_material("WarriorSoul") >= cost: break
		await $UI._card_action(spare.cardId, "dismantle")
	if not _check($UI._card_material("WarriorSoul") >= cost, "Spare-card refunds reach the craft price"): return _finish(false)
	var before: Dictionary = Game.lobby.materials.duplicate(true)
	$UI._codex_card = card_id
	$UI._render()
	await _capture("craft")
	_check(not $UI._reference.find_child("CraftCard", true, false).disabled, "Live craft button is enabled with enough souls")
	await $UI._card_action(card_id, "craft")
	_check($UI._owned_card(card_id).copyCount == 1, "Craft refreshes the owned copy count")
	_check(Game.lobby.materials.warriorSoul == before.warriorSoul - cost, "Craft deducts the quoted warrior souls")
	_check($UI._reference.find_child("DismantleCard", true, false) != null, "Craft switches the open dialog to dismantle")
	await _capture("crafted")
	var refund: int = $UI._owned_card(card_id).dismantleRefund
	await $UI._card_action(card_id, "dismantle")
	_check($UI._owned_card(card_id).copyCount == 0 and not $UI._owned_card(card_id).unlocked, "Last-copy dismantle returns card to unowned")
	_check(Game.lobby.materials.warriorSoul == before.warriorSoul - cost + refund and refund == 2, "Dismantle returns floor(10 * 25%) = 2 souls")
	_check($UI._reference.find_child("CraftCard", true, false) != null, "Dismantle switches the open dialog back to craft")
	for field in ["priestSoul", "mageSoul", "guardianSoul"]:
		_check(Game.lobby.materials[field] == before[field], "Other soul balance is unchanged: " + field)
	var protected_cards: Array = $UI.owned.filter(func(card): return card.copyCount > 0 and not card.canDismantle)
	if not protected_cards.is_empty():
		$UI._codex_card = protected_cards[0].cardId
		$UI._render()
		_check($UI._reference.find_child("DismantleCard", true, false).disabled, "Live saved deck blocks dismantling its required copy")
	await _capture("protected")
	var draft: Array = $UI.deck_draft.duplicate()
	draft.remove_at(draft.size() - 1)
	$UI.deck_draft = draft.duplicate()
	await $UI._save_deck()
	_check($UI.deck_draft == draft, "Rejected deck save preserves the current draft")
	_finish(true)

func _capture(label: String) -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(output + "/" + label + ".png")

func _check(value: bool, label: String) -> bool:
	checks.append({"passed": value, "name": label})
	return value

func _finish(ok: bool, error: String = "") -> void:
	if finished: return
	finished = true
	var report := {"ok": ok and checks.all(func(check): return check.passed), "fixture_only": false, "checks": checks, "error": error}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	get_tree().quit(0 if report.ok else 1)
