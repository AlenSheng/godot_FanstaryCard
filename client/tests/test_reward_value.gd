extends RefCounted

const Model = preload("res://ui/reward_value_model.gd")
const P = preload("res://ui/palette.gd")

static func gear(slot: String, quality: String = "Purple", effect: String = "Piercing", level: int = 3) -> Dictionary:
	return {"kind": "Equipment", "equipment": {"slot": slot, "quality": quality, "element": "Water", "effect_affix": effect, "secondary_trait": "DrawInterval", "level": level, "stats_version": "season-equipment-v1"}}

static func player() -> Dictionary:
	return {"inventory_capacity": 20, "inventory": [], "equipped_items": [], "combat": {"maximum_hp": 70, "effective_maximum_hp": 98, "hp": 80}}

func run_test() -> Dictionary:
	var checks := {}
	var actor := player()
	var initial := actor.duplicate(true)
	var heal := {"kind": 3, "heal_percent": 30}
	var result := Model.evaluate(heal, actor)
	checks["projection neverwrites input actor"] = actor == initial
	checks["legal80over70 uses98effective cap"] = result.heal_gain == 18 and result.heal_overflow == 3 and not result.carry_required
	checks["heal decision leads its detail lines"] = Model.display_lines(result)[0] == P.localized("reward_value_heal") % [18, 3]
	actor.combat.hp = 98
	result = Model.evaluate(heal, actor)
	checks["effective full health haszero gain"] = result.heal_gain == 0 and result.heal_overflow == 21
	actor.combat = {"maximum_hp": 80, "effective_maximum_hp": 80, "hp": 70}
	result = Model.evaluate(heal, actor)
	checks["priest70of80 lawful missing10"] = result.heal_gain == 10 and result.heal_overflow == 14
	actor = player()
	var offer := {"kind": 1, "equipment": gear("Head").equipment}
	result = Model.evaluate(offer, actor)
	checks["empty slot is described withoutrating"] = result.slot_empty and result.current_item.is_empty() and result.carry_required
	actor.equipped_items = [gear("Head"), gear("Chest"), gear("Hands")]
	offer.equipment = gear("Head", "Purple", "Vitality").equipment
	result = Model.evaluate(offer, actor)
	var loss: Dictionary = result.set_changes.filter(func(value): return value.kind == "Piercing")[0]
	checks["replacement showsactive setloss"] = loss.before_count == 3 and loss.after_count == 2 and loss.before_active and not loss.after_active
	checks["setloss leads generic carry explanation"] = Model.display_lines(result)[0] == P.localized("reward_value_set") % [P.word("Piercing"), 3, 3, 2, 3]
	checks["existing armorlevel3not projected"] = result.current_item.equipment.level == 3
	actor.equipped_items = [gear("Head", "Blue", ""), gear("Chest"), gear("Hands")]
	offer.equipment = gear("Head").equipment
	result = Model.evaluate(offer, actor)
	var gain: Dictionary = result.set_changes.filter(func(value): return value.kind == "Piercing")[0]
	checks["replacement showsnew active set"] = gain.before_count == 2 and gain.after_count == 3 and not gain.before_active and gain.after_active
	actor.equipped_items = [gear("Chest", "Orange")]
	offer.equipment = gear("Head", "Orange").equipment
	result = Model.evaluate(offer, actor)
	checks["second highquality piece isnot projected aslegal upgrade"] = result.high_quality_blocked and result.set_changes.is_empty()
	checks["illegal equip warning leads item details"] = Model.display_lines(result)[0] == P.localized("reward_value_high_quality")
	offer.equipment = gear("Chest", "Orange").equipment
	checks["same highquality slotreplacement remainslegal"] = not Model.evaluate(offer, actor).high_quality_blocked
	actor = player(); actor.inventory_capacity = 1
	actor.inventory = [{"kind": "HealthPotion", "item_id": "potion", "quantity": 1}]
	checks["full bag equipment needsreplacement"] = Model.evaluate(offer, actor).bag_full
	var fragments := {"kind": 2, "item_id": "equipment_fragments", "quantity": 12}
	checks["full bag new fragmentstack needsreplacement"] = Model.evaluate(fragments, actor).bag_full
	actor.inventory = [{"kind": "EquipmentFragments", "item_id": "equipment_fragments", "quantity": 5}]
	checks["existing fragmentstack canmerge"] = not Model.evaluate(fragments, actor).bag_full
	checks["fragment amount leads generic carry explanation"] = Model.display_lines(Model.evaluate(fragments, actor))[0] == P.localized("exploration_reward_quantity") % 12
	checks["heal neverneedsbagspace"] = not Model.evaluate(heal, actor).bag_full
	var missing := {"version": "missing-original", "tables": {}, "qualities": {}}
	result = Model.evaluate(offer, actor, missing)
	checks["missing original doesnot invent current setstats"] = not result.catalog_ready and result.set_changes.is_empty()
	return {"ok": not checks.values().has(false), "checks": checks, "scope": "Public rewarddecision projection, no monetization/equivalence or actualmatch claim."}
