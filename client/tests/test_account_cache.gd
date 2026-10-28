extends RefCounted

func run_test() -> Dictionary:
	var Store = load("res://state/game_store.gd")
	var store = Store.new()
	store.lobby = {
		"player": {"userId": "seller"}, "wallet": {"gold": 100}, "market": [],
		"inventory": {"equipments": [{"instanceId": "item-1", "location": "Inventory"}],
			"summary": {"capacity": 50, "equipmentCount": 1, "freeSlots": 49}}
	}
	var modules: Array = []
	store.cache_changed.connect(func(module): modules.append(module))
	var future := int(Time.get_unix_time_from_system() * 1000) + 60000
	var listing := {
		"listing_id": "listing-1", "seller_id": "seller", "equipment_id": "item-1",
		"price_gold": 50, "status": "Active", "version": 1,
		"created_at_unix_ms": future - 60000, "expires_at_unix_ms": future,
		"equipment": {"instance_id": "item-1", "slot": "Head", "quality": "Blue",
			"location": "MarketListed", "version": 2}
	}
	store._apply_market_event({"action": "market.listed", "listing": listing})
	var ok: bool = store.lobby.market.size() == 1 and store.lobby.inventory.equipments.is_empty()
	listing["status"] = "Sold"
	listing["version"] = 2
	store._apply_market_event({"action": "market.sold", "listing": listing, "seller_gold_after": 145})
	ok = ok and store.lobby.market.is_empty() and int(store.lobby.wallet.gold) == 145
	listing["status"] = "Active"
	listing["version"] = 3
	store._apply_market_event({"action": "market.listed", "listing": listing})
	listing["status"] = "Cancelled"
	listing["version"] = 4
	listing.equipment["location"] = "Inventory"
	store._apply_market_event({"action": "market.cancelled", "listing": listing})
	ok = ok and store.lobby.market.is_empty() and store.lobby.inventory.equipments.size() == 1
	ok = ok and int(store.lobby.inventory.summary.equipmentCount) == 1
	ok = ok and modules.has("market") and modules.has("inventory") and modules.has("wallet")
	store.free()
	return {"ok": ok, "message": "Market listing deltas update account cache and seller balance without a read request"}
