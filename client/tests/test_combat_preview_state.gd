extends RefCounted

func run_test() -> Dictionary:
	var store = load("res://state/game_store.gd").new()
	var gateway = load("res://network/gateway.gd").new()
	gateway.persist_session = false
	gateway.online = true
	store.gateway = gateway
	store.selected_cards = ["card-a"]
	store.room = {"room_id": "room-a", "room_revision": 8, "allowed_actions": ["battle.play_cards"], "player": {"hand": [{"instance_id": "card-a"}]}, "pve": {"battle_id": "battle-a", "current_target_id": "monster-a", "monsters": [{"monster_id": "monster-a", "hp": 10}]}}
	store._preview_request = {"request_id": "request-a", "context": store._preview_context(store.selected_cards), "revision": 8}
	store._preview_deadline = Time.get_ticks_msec() + 1000
	var payload := {"_request_id": "older-request", "_room_revision": 8, "damage": 5}
	store._accept_combat_preview(payload)
	var ok: bool = store.combat_preview.is_empty()
	payload._request_id = "request-a"
	payload._room_revision = 7
	store._accept_combat_preview(payload)
	ok = ok and store.combat_preview.is_empty()
	payload._room_revision = 8
	store._accept_combat_preview(payload)
	ok = ok and store.combat_preview.damage == 5 and store.combat_preview.source_revision == 8
	store.combat_preview = {}
	store.selected_cards = ["card-b"]
	store._accept_combat_preview(payload)
	ok = ok and store.combat_preview.is_empty()
	store.selected_cards = ["card-a"]
	store.room.pve.current_target_id = "monster-b"
	store._accept_combat_preview(payload)
	ok = ok and store.combat_preview.is_empty()
	store.room.pve.current_target_id = "monster-a"
	store.room.room_revision = 9
	store._accept_combat_preview(payload)
	ok = ok and store.combat_preview.is_empty()
	store.room.room_revision = 8
	store._preview_deadline = Time.get_ticks_msec() - 1
	store._accept_combat_preview(payload)
	ok = ok and store.combat_preview.is_empty()
	store.clear_combat_preview()
	ok = ok and store._preview_request.is_empty()
	store.free()
	gateway.free()
	return {"ok": ok, "message": "Combat previews reject wrong request IDs, old revisions, changed card selections/targets, and expired responses"}
