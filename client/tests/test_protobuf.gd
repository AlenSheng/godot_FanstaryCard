extends RefCounted

const Proto = preload("res://network/protobuf.gd")

func run_test() -> Dictionary:
	var proto := Proto.new()
	if proto.decode("RoomRelicPile", PackedByteArray([40, 1])).get("owner_name_is_fallback") != true:
		return {"ok": false, "message": "Relic name provenance tag changed"}
	if proto.decode("RoomDuel", PackedByteArray([128, 1, 1])).get("opponent_name_is_fallback") != true:
		return {"ok": false, "message": "Opponent name provenance tag changed"}
	if proto.decode("RoomRelicPile", PackedByteArray()).has("owner_name_is_fallback") or proto.decode("RoomDuel", PackedByteArray()).has("opponent_name_is_fallback"):
		return {"ok": false, "message": "Legacy names acquired an inferred provenance marker"}
	# Independent golden wire: version=1, type=ping, request_id=a.
	var golden := PackedByteArray([8, 1, 18, 4, 112, 105, 110, 103, 26, 1, 97])
	var decoded: Dictionary = proto.decode("ClientEnvelope", golden)
	if decoded.get("type") != "ping" or decoded.get("protocol_version") != 1:
		return {"ok": false, "message": "Golden envelope decode failed"}
	if proto.encode("ClientEnvelope", {"protocol_version": 1, "type": "ping", "request_id": "a"}) != golden:
		return {"ok": false, "message": "Golden envelope encode failed"}
	var snapshot := {"room_id": "room", "room_revision": 32768, "self": {"row": 0, "column": 5}, "player": {"hero_class": "Mage", "combat": {"hp": 70}, "hand": [{"instance_id": "first", "card_id": "C01"}, {"instance_id": "second", "card_id": "C02"}]}, "allowed_actions": ["battle.play_cards"]}
	var wire: PackedByteArray = proto.encode("RoomSnapshotEvent", snapshot)
	# Unknown length-delimited field must be skipped without losing subsequent values.
	wire.append_array(PackedByteArray([250, 7, 2, 65, 66]))
	decoded = proto.decode("RoomSnapshotEvent", wire)
	if decoded.get("room_revision") != 32768 or decoded.get("player", {}).get("hand", []).size() != 2:
		return {"ok": false, "message": "Nested repeated snapshot failed"}
	if decoded.self.row != 0 or decoded.player.combat.shield != 0 or decoded.player.hand[1].card_id != "C02":
		return {"ok": false, "message": "Defaults or repeated order broken"}
	# Independent wire for RoomMonster field 11 (varint), preserving the server's phase.
	for phase in [1, 2]:
		var monster: Dictionary = proto.decode("RoomMonster", PackedByteArray([88, phase]))
		if monster.get("boss_phase") != phase:
			return {"ok": false, "message": "Authoritative monster phase lost in wire decode"}
	var legacy: Dictionary = proto.decode("RoomMonster", PackedByteArray([16, 1]))
	if maxi(1, int(legacy.get("boss_phase", 1))) != 1:
		return {"ok": false, "message": "Legacy low-HP monster must remain phase one"}
	var market_event := {"action": "market.listed", "item_id": "listing-1", "listing": {
		"listing_id": "listing-1", "seller_id": "seller", "equipment_id": "item-1",
		"price_gold": 150, "status": "Active", "version": 2,
		"expires_at_unix_ms": 1790000000000,
		"equipment": {"instance_id": "item-1", "slot": "Head", "quality": "Blue", "version": 4}}}
	var market_decoded: Dictionary = proto.decode("InventoryChangedEvent", proto.encode("InventoryChangedEvent", market_event))
	if market_decoded.get("listing", {}).get("equipment", {}).get("quality", "") != "Blue" or int(market_decoded.listing.price_gold) != 150:
		return {"ok": false, "message": "Market listing delta lost nested equipment"}
	for malformed in [PackedByteArray([18, 127, 65]), PackedByteArray([8, 128]), PackedByteArray([0]), PackedByteArray([13, 0])]:
		proto.decode("ClientEnvelope", malformed)
		if proto.error.is_empty(): return {"ok": false, "message": "Malformed packet accepted"}
	return {"ok": true, "message": "Golden wire, nested defaults, unknown fields and truncation passed"}
