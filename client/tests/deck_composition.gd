extends Node

var failures: Array[String] = []
var checks := 0

func _ready() -> void:
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.persist_session = false
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	_run.call_deferred()

func _run() -> void:
	Game.lobby = {"player": {"userId": "deck-fixture"}, "materials": {"warriorSoul": 300}, "wallet": {"gold": 0}, "decks": []}
	Game.room = {}
	Game.settlement = {}
	Game.ready_prompt = {}
	Game.busy = false
	Game.hero_class = "Mage"
	var host = load("res://main.tscn").instantiate()
	add_child(host)
	host._codex_ready = true
	host.owned = []
	for id in host.cards:
		var info: Dictionary = host.cards[id]
		if not info.is_codex: continue
		var owned: bool = id in ["C01", "MAG-01", "PRI-01"]
		host.owned.append({"cardId": id, "unlocked": owned, "copyCount": 2 if owned else 0, "level": 1 if id == "C01" else 0, "craftCost": 10, "dismantleRefund": 2, "currencyKind": "WarriorSoul", "canDismantle": owned})
	host.screen = "cards"
	host._render()
	_check(host._reference.find_child("CardGrid", true, false).get_child_count() == 200, "Codex includes every locked and unlocked card")
	_check(host._reference.find_child("DeckScroll", true, false) == null, "Codex has no deck editor")
	_check(host._reference.find_child("ToggleDeck", true, false) == null, "Codex cannot toggle into deck editing")
	host._reference.find_child("Card_GW08", true, false).pressed.emit()
	_check(host._reference.find_child("CraftCard", true, false) != null, "Locked card opens unlock/craft action")
	_check(host._reference.find_child("AddCardToDeck", true, false) == null, "Codex details never offer deck changes")
	host._codex_card = ""
	host.screen = "deck"
	host.deck_draft = []
	host._render()
	_check(host._reference.find_child("CardGrid", true, false).get_child_count() == 3, "Deck pool contains only owned cards")
	_check(host._reference.find_child("Card_GW08", true, false) == null, "Locked cards are absent from deck pool")
	_check(host._reference.find_child("Card_PRI-01", true, false).disabled, "Other-class card is visible but unavailable")
	_check(host._reference.find_child("Card_C01", true, false).get_node_or_null("Illustration") != null, "Pool uses existing illustrated card face")
	host._reference.find_child("Card_C01", true, false).pressed.emit()
	_check(host.deck_draft == ["C01"], "Pool click adds one card directly")
	_check(host._reference.find_child("CraftCard", true, false) == null, "Deck editor does not open collection mutations")
	var row: Button = host._reference.find_child("DeckRow_0", true, false)
	_check(row.get_node("SkillName").text == host.cards.C01.name, "Deck row displays skill name")
	var expected: String = host.CardDetails.effect_text(host.CardDetails.at_level(host.cards.C01, 1))
	_check(row.get_node("EffectSummary").text == expected, "Effect uses owned card level")
	_check(row.get_theme_stylebox("normal").texture != null, "Deck row has a quality texture")
	host._reference.find_child("Card_C01", true, false).pressed.emit()
	_check(host._reference.find_child("Card_C01", true, false).disabled, "Owned copy limit disables further additions")
	host._reference.find_child("DeckRow_0", true, false).pressed.emit()
	_check(host.deck_draft == ["C01"], "Row click removes one copy")
	_check(not host._reference.find_child("Card_C01", true, false).disabled, "Removal restores pool availability")
	_check(host._reference.find_child("SaveDeck", true, false).disabled, "Incomplete deck cannot be saved")
	var codex = load("res://ui/codex_view.gd")
	for class_card in [false, true]:
		var orange_id := ""
		for id in host.cards:
			var info: Dictionary = host.cards[id]
			if info.is_codex and info.quality == "Orange" and (info.hero_class == "Mage" if class_card else info.hero_class == null):
				orange_id = id
				break
		host.deck_draft = [orange_id]
		_check(codex._add_reason(host, orange_id, host.cards[orange_id], 2) == "已达到橙卡携带上限", "Orange limit: class=%s" % class_card)
	host.deck_draft.resize(20)
	_check(codex._add_reason(host, "C01", host.cards.C01, 30) == "编组已满", "Deck capacity remains 20")
	host.deck_draft = []
	host._search = "不应匹配任何卡牌123"
	host._render()
	_check(host._reference.find_child("CardGrid", true, false).get_child(0) is Label, "Empty filtered pool shows a hint")
	print(JSON.stringify({"ok": failures.is_empty(), "checks": checks, "failures": failures, "snapshots": 0}))
	get_tree().quit(0 if failures.is_empty() else 1)

func _check(value: bool, message: String) -> void:
	checks += 1
	if not value: failures.append(message)
