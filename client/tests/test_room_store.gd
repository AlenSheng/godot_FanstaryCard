extends RefCounted

func run_test() -> Dictionary:
	var Store = load("res://state/game_store.gd")
	var Gateway = load("res://network/gateway.gd")
	var store = Store.new()
	var gateway = Gateway.new()
	gateway.persist_session = false
	gateway.online = true
	store.gateway = gateway
	store.selected_cards = ["kept", "removed"]
	store._on_event("room.snapshot", {"room_id": "test", "player": {"hand": [{"instance_id": "kept", "card_id": "C01"}]}, "allowed_actions": ["choice.pick", "choice.refresh"]})
	var ok: bool = store.selected_cards == ["kept"] and store.allowed("reward.choice.claim") and store.allowed("reward.choice.refresh") and not store.allowed("action.extract")
	gateway.recovering = true
	ok = ok and not store.allowed("reward.choice.claim")
	store.room = {"player": {"hand": [{"instance_id": "kept"}]}, "pve": {"battle_id": "battle", "current_target_id": "dead", "monsters": [{"monster_id": "dead", "hp": 0}, {"monster_id": "alive", "hp": 12}]}}
	var intent := {"battle_id": "battle", "target_id": "dead", "card_instance_ids": ["kept"]}
	ok = ok and not store._intent_valid("battle.play_cards", intent)
	intent.target_id = "alive"
	ok = ok and store._intent_valid("battle.play_cards", intent)
	intent.card_instance_ids = ["removed"]
	ok = ok and not store._intent_valid("battle.play_cards", intent)
	intent.card_instance_ids = []
	ok = ok and not store._intent_valid("battle.play_cards", intent)
	ok = ok and store._intent_valid("battle.select_target", {"battle_id": "battle", "target_id": "alive"})
	ok = ok and not store._intent_valid("battle.select_target", {"battle_id": "old", "target_id": "alive"})
	store.room.pve.monsters[1].hp = 0
	ok = ok and not store._intent_valid("battle.select_target", {"battle_id": "battle", "target_id": "alive"})
	store.room = {"duel": {"opponent_id": "other"}}
	ok = ok and store.target_alive("other") and not store.target_alive("dead")
	store.free()
	gateway.free()
	return {"ok": ok, "message": "Authoritative action gating, recovery lock, stale hand/battle/target rejection and duel target validation"}
