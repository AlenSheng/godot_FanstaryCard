extends RefCounted

const Details = preload("res://ui/equipment_details.gd")

func run_test() -> Dictionary:
	var gear := {"quality": "Purple", "element": "Water", "slot": "Feet", "level": 0, "effectAffix": "Vitality"}
	var nested := {"kind": "Equipment", "equipment": {"quality": "Purple", "element": "Water", "slot": "Feet", "level": 0, "effect_affix": "Vitality"}}
	var plain := {"quality": "Purple", "element": "Water", "slot": "Feet", "level": 0}
	var white := {"quality": "White", "element": "Fire", "slot": "Head", "level": 0, "secondaryTrait": "DrawInterval"}
	var upgraded_white := white.duplicate()
	upgraded_white.level = 1
	var checks := {
		"stored equipment includes set prefix": Details.title(gear) == "生息·紫水鞋子 +0",
		"exploration equipment includes set prefix": Details.title(nested) == "生息·紫水鞋子 +0",
		"tooltip uses the same name": Details.description(nested).begins_with("生息·紫水鞋子 +0"),
		"equipment without set affix keeps its name": Details.title(plain) == "紫水 鞋子 +0",
		"zero draw interval is hidden": not Details.description(white).contains("抽牌间隔"),
		"upgraded draw interval is shown": Details.description(upgraded_white).contains("抽牌间隔 -1%"),
	}
	return {"ok": not checks.values().has(false), "message": "Equipment set-affix names", "checks": checks}
