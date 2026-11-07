extends RefCounted

const KINDS := ["EquipmentFragments", "WarriorSoul", "ClassSoul", "CardPack", "Cosmetic"]
const SLOTS := ["AvatarFrame", "CardBack", "Title", "Collection"]
const HEROES := ["Mage", "Priest", "Guardian"]

static func integer(value: Variant, minimum: int = 0, maximum: int = 9223372036854775807) -> bool:
	return value is int and value >= minimum and value <= maximum

static func identity(value: Variant) -> bool:
	return value is String and not value.strip_edges().is_empty() and value.length() <= 120

static func valid_reward(row: Dictionary, season: String, version: String) -> bool:
	if row.get("seasonId") != season or row.get("configVersion") != version or not integer(row.get("level"), 1, 30):
		return false
	if not integer(row.get("requiredExperience"), 1, 12525) or row.get("kind") not in KINDS or not integer(row.get("amount"), 1, 2147483647):
		return false
	if row.get("ownership") != ("SeasonalBound" if row.kind == "EquipmentFragments" else "PermanentBound"):
		return false
	if not row.get("requiresClassChoice") is bool or row.requiresClassChoice != (row.kind == "ClassSoul") or not row.get("canClaim") is bool:
		return false
	if row.kind == "Cosmetic":
		if not identity(row.get("cosmeticId")):
			return false
	elif row.get("cosmeticId") != null:
		return false
	if row.get("state") not in ["Locked", "Pending", "Claimed", "Unavailable"]:
		return false
	if row.state in ["Locked", "Unavailable"] and row.canClaim:
		return false
	if row.state == "Locked":
		return row.get("rewardId") == null and row.get("earnedAt") == null and row.get("claimedAt") == null and row.get("heroClass") == null
	if row.state in ["Pending", "Claimed"] and (not identity(row.get("rewardId")) or not identity(row.get("earnedAt"))):
		return false
	if row.state == "Claimed":
		return not row.canClaim and identity(row.get("claimedAt")) and (row.get("heroClass") in HEROES if row.requiresClassChoice else row.get("heroClass") == null)
	return row.get("claimedAt") == null and row.get("heroClass") == null

static func valid_rewards(data: Dictionary, season: String) -> bool:
	if data.get("state") not in ["None", "Disabled", "Unavailable", "Active", "Upcoming", "Ended"] or not data.get("rewards") is Array:
		return false
	if data.state == "None":
		return data.rewards.is_empty() and data.get("seasonId") == null and data.get("configVersion") == null
	if data.get("seasonId") != season or not identity(data.get("configVersion")) or data.rewards.size() > 30:
		return false
	if data.state == "Disabled":
		return data.rewards.is_empty()
	if data.state in ["Active", "Upcoming", "Ended"] and data.rewards.size() != 30:
		return false
	var levels := {}
	var ids := {}
	for row in data.rewards:
		if not row is Dictionary or not valid_reward(row, season, str(data.configVersion)) or levels.has(row.level):
			return false
		levels[row.level] = true
		if row.get("rewardId") != null:
			if not identity(row.rewardId) or ids.has(row.rewardId):
				return false
			ids[row.rewardId] = true
	return true

static func valid_selection(data: Dictionary, owned: Dictionary) -> bool:
	if not integer(data.get("version")):
		return false
	for field in {"avatarFrameId": "AvatarFrame", "cardBackId": "CardBack", "titleId": "Title"}:
		var value: Variant = data.get(field)
		if value != null and (not identity(value) or owned.get(value) != {"avatarFrameId": "AvatarFrame", "cardBackId": "CardBack", "titleId": "Title"}[field]):
			return false
	return true

static func valid_inventory(data: Dictionary) -> bool:
	if not data.get("owned") is Array or data.owned.size() > 4096 or not data.get("selection") is Dictionary:
		return false
	var owned := {}
	for row in data.owned:
		if not row is Dictionary or not identity(row.get("cosmeticId")) or owned.has(row.cosmeticId) or row.get("kind") not in SLOTS:
			return false
		for field in ["nameKey", "descriptionKey", "sourceSeasonId", "configVersion", "acquiredAt"]:
			if not identity(row.get(field)):
				return false
		owned[row.cosmeticId] = row.kind
	return valid_selection(data.selection, owned)

static func claim_body(row: Dictionary, hero: String) -> Dictionary:
	if row.get("state") != "Pending" or not row.get("canClaim", false) or not identity(row.get("rewardId")) or not identity(row.get("seasonId")):
		return {}
	var body := {"seasonId": row.seasonId}
	if row.get("requiresClassChoice", false):
		if hero not in HEROES:
			return {}
		body.heroClass = hero
	return body

static func valid_claim(data: Dictionary, expected: Dictionary, hero: String) -> bool:
	if not data.get("reward") is Dictionary or not data.get("grants") is Array or not data.get("cosmeticNewlyOwned") is bool:
		return false
	var reward: Dictionary = data.reward
	if not valid_reward(reward, str(expected.get("seasonId", "")), str(expected.get("configVersion", ""))) or reward.state != "Claimed":
		return false
	for field in ["rewardId", "level", "kind", "amount", "ownership", "requiresClassChoice", "cosmeticId", "requiredExperience"]:
		if reward.get(field) != expected.get(field):
			return false
	if reward.get("heroClass") != (hero if reward.requiresClassChoice else null):
		return false
	var total := 0
	for grant in data.grants:
		if not grant is Dictionary or not integer(grant.get("amount"), 1) or not integer(grant.get("version")):
			return false
		if reward.kind == "CardPack":
			if grant.get("kind") != "Cards" or not identity(grant.get("cardId")) or not integer(grant.get("copiesAfter"), int(grant.amount), 2147483647):
				return false
		elif grant.get("kind") != (hero + "Soul" if reward.kind == "ClassSoul" else reward.kind):
			return false
		total += int(grant.amount)
	var expected_count := 0 if reward.kind == "Cosmetic" else 3 * int(reward.amount) if reward.kind == "CardPack" else int(reward.amount)
	return total == expected_count and (data.get("balanceAfter") == null or integer(data.balanceAfter))
