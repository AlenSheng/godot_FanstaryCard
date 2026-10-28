extends RefCounted

const COUNTER_TARGET := {"Water": "Fire", "Fire": "Metal", "Metal": "Wood", "Wood": "Earth", "Earth": "Water"}
const GENERATED_ELEMENT := {"Wood": "Fire", "Fire": "Earth", "Earth": "Metal", "Metal": "Water", "Water": "Wood"}
const CONFLICT_WITH := {
	"Wood": {"Earth": true, "Metal": true},
	"Earth": {"Wood": true, "Water": true},
	"Water": {"Earth": true, "Fire": true},
	"Fire": {"Water": true, "Metal": true},
	"Metal": {"Fire": true, "Wood": true},
}

static func counters(attacker: String, target: String) -> bool:
	return COUNTER_TARGET.get(attacker, "") == target

static func conflicts(left: String, right: String) -> bool:
	return left != right and bool(CONFLICT_WITH.get(left, {}).get(right, false))

static func generated(element: String) -> String:
	return str(GENERATED_ELEMENT.get(element, "None"))
