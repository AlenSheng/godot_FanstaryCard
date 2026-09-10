extends RefCounted

func run_test() -> Dictionary:
	var details = load("res://ui/card_details.gd")
	var proto = load("res://network/protobuf.gd").new()
	var card: Dictionary = details.CATALOG.data.tables.Cards.filter(func(value): return value.id == "M-BOXSPIRIT")[0]
	var original := card.duplicate(true)
	var ok := true
	for element in ["Fire", "None"]:
		var room_card := {"instance_id": "box-" + element, "card_id": "M-BOXSPIRIT", "element_override": element}
		var decoded: Dictionary = proto.decode("RoomCard", proto.encode("RoomCard", room_card))
		ok = ok and decoded.get("element_override", "") == element
		var instance: Dictionary = details.with_element(card, decoded.element_override)
		if element == "Fire":
			ok = ok and instance.elemental_damage == 7 and instance.direct_damage == 0 and details.effect_text(instance) == "火伤 7"
		else:
			ok = ok and instance.elemental_damage == 0 and instance.direct_damage == 7 and details.effect_text(instance) == "直伤 7"
	var ordinary := {"id": "C01", "element": "Fire", "elemental_damage": 4}
	ok = ok and details.with_element(ordinary, "None") == ordinary
	ok = ok and details.with_element(card, "") == original and card == original
	return {"ok": ok, "message": "Box spirit instance overrides round-trip and render Fire 7 or Direct 7 without changing catalog or ordinary cards"}
