extends RefCounted

static func living(battle: Dictionary) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for monster in battle.get("monsters", []):
		if monster is Dictionary and int(monster.get("hp", 0)) > 0:
			result.append(monster)
	return result

static func current(battle: Dictionary) -> Dictionary:
	var monsters := living(battle)
	for monster in monsters:
		if str(monster.get("monster_id", "")) == str(battle.get("current_target_id", "")):
			return monster
	return monsters[0] if not monsters.is_empty() else {}
