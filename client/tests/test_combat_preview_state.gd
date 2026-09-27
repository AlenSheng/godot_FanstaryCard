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
	store.room.pve.monsters.append({"monster_id": "monster-b", "hp": 10})
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
	# Most catalog cards have a null is_class_reveal field. Local previews must
	# treat that as false rather than attempting an invalid bool conversion.
	store.room = {"room_id": "room-a", "allowed_actions": ["battle.play_cards"], "player": {"hero_class": "Mage", "hand": [{"instance_id": "card-a", "card_id": "C01", "level": 0, "element_override": ""}], "battle_status": {}}, "pve": {"battle_id": "battle-a", "current_target_id": "monster-a", "monsters": [{"monster_id": "monster-a", "hp": 100, "shield": 0}]}}
	var local_preview: Dictionary = store._calculate_combat_preview(["card-a"])
	ok = ok and not local_preview.is_empty()
	store.room.player.hand = [{"instance_id": "direct-card", "card_id": "C11", "level": 0, "element_override": ""}]
	var direct_preview: Dictionary = store._calculate_combat_preview(["direct-card"])
	ok = ok and int(direct_preview.get("damage", 0)) == 6 and direct_preview.get("damage_segments", []).any(func(value): return value.get("kind", "") == "Direct" and int(value.get("amount", 0)) == 6)
	store.room.player.hand = [{"instance_id": "earth-card", "card_id": "C09"}, {"instance_id": "water-card", "card_id": "C06"}]
	var core_preview: Dictionary = store._calculate_combat_preview(["earth-card", "water-card"])
	ok = ok and core_preview.get("core_element", "") == "Earth"
	store.clear_combat_preview()
	ok = ok and store._preview_request.is_empty()
	store.free()
	gateway.free()
	return {"ok": ok, "message": "Combat previews reject stale state, include printed direct damage, and preserve first-card core selection"}
