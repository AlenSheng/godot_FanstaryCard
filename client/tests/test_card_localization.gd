extends RefCounted

const P = preload("res://ui/palette.gd")
const CardDetails = preload("res://ui/card_details.gd")
const CardView = preload("res://ui/card_view.gd")
const CATALOG = preload("res://data/catalog.json")

func run_test() -> Dictionary:
	var original_language := P.language()
	P.set_language("en")
	var missing: Array[String] = []
	for card in CATALOG.data.tables.Cards:
		var id := str(card.get("id", ""))
		if CardDetails.localized_name(id, card) == str(card.get("name", id)):
			missing.append(id)
	var sample: Dictionary = CATALOG.data.tables.Cards[0]
	var view := CardView.new()
	view.configure("C01", sample, "Fire elemental damage 8", false)
	var rendered_name := str(view.get_node("CardName").text)
	view.free()
	P.set_language("zh-CN")
	var chinese_name := CardDetails.localized_name("C01", sample)
	P.set_language(original_language)
	var checks := {
		"Every catalog card has an English name": missing.is_empty(),
		"Card faces use the localized name": rendered_name == "Fire Slash",
		"Chinese keeps the catalog name": chinese_name == "火斩",
	}
	return {"ok": not checks.values().has(false), "checks": checks, "message": "Card names follow the active language across the shared rendering path"}
