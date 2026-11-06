extends RefCounted

const Http = preload("res://network/http_protocol.gd")
const Model = preload("res://ui/season_journey_reward_model.gd")
var _checks := {}

func _decode(name: String, path: String) -> Dictionary:
	var bytes := FileAccess.get_file_as_bytes("res://tests/journey-reward-client/" + name + ".bin")
	var response := Http.decode_response(Http.route(path, HTTPClient.METHOD_PUT if name == "selection" else HTTPClient.METHOD_POST if name in ["pack", "soul"] else HTTPClient.METHOD_GET), 200, PackedStringArray(["Content-Type: application/protobuf"]), bytes)
	_checks[name + " actual HTTP body decoded"] = response.get("ok", false)
	return response.get("data", {})

func run_test() -> Dictionary:
	_checks = {}
	var before := _decode("before", "/api/v1/season-journey/rewards")
	var after := _decode("after", "/api/v1/season-journey/rewards")
	var missing := _decode("missing", "/api/v1/season-journey/rewards")
	if before.is_empty() or after.is_empty() or missing.is_empty():
		return {"ok": false, "checks": _checks}
	var season: String = str(before.seasonId)
	_checks["original pending source validates"] = Model.valid_rewards(before, season)
	_checks["committed source validates"] = Model.valid_rewards(after, season)
	_checks["unknown original remains absent"] = Model.valid_rewards(missing, "unknown") and missing.state == "None"
	_checks["six actual committed reward states"] = after.rewards.filter(func(row): return row.state == "Claimed").size() == 6
	var pack_before: Dictionary = before.rewards.filter(func(row): return row.level == 5)[0]
	var soul_before: Dictionary = before.rewards.filter(func(row): return row.level == 3)[0]
	var pack := _decode("pack", "/api/v1/season-journey/rewards/" + str(pack_before.rewardId) + "/claim")
	var soul := _decode("soul", "/api/v1/season-journey/rewards/" + str(soul_before.rewardId) + "/claim")
	_checks["three real copies validate"] = Model.valid_claim(pack, pack_before, "Mage") and pack.grants[0].amount == 3
	_checks["one chosen permanent class validates"] = Model.valid_claim(soul, soul_before, "Mage") and soul.grants[0].kind == "MageSoul" and soul.grants[0].amount == 2
	_checks["class intent requires a choice"] = Model.claim_body(soul_before, "").is_empty()
	_checks["class intent contains only original source and chosen class"] = Model.claim_body(soul_before, "Mage") == {"seasonId": season, "heroClass": "Mage"}
	_checks["pack intent cannot send invented quantity"] = Model.claim_body(pack_before, "Mage") == {"seasonId": season}
	_checks["claimed rows cannot be claimed again by UI"] = Model.claim_body(after.rewards.filter(func(row): return row.level == 5)[0], "Mage").is_empty()
	var inventory := _decode("inventory", "/api/v1/cosmetics")
	var final_inventory := _decode("final-inventory", "/api/v1/cosmetics")
	var selection := _decode("selection", "/api/v1/cosmetics/selection")
	_checks["permanent owned metadata validates"] = Model.valid_inventory(inventory)
	_checks["persisted selection inventory validates"] = Model.valid_inventory(final_inventory)
	var owned := {}
	for row in inventory.get("owned", []):
		owned[row.cosmeticId] = row.kind
	_checks["actual equipped avatar frame validates"] = Model.valid_selection(selection, owned) and selection.avatarFrameId == "trail-seeker"
	var corrupt := before.duplicate(true)
	corrupt.rewards[0].amount = -1
	_checks["negative quantity rejected"] = not Model.valid_rewards(corrupt, season)
	corrupt = before.duplicate(true)
	corrupt.rewards[0].level = 1.5
	_checks["fractional level rejected"] = not Model.valid_rewards(corrupt, season)
	corrupt = before.duplicate(true)
	corrupt.rewards[0].canClaim = 1
	_checks["nonboolean claim eligibility rejected"] = not Model.valid_rewards(corrupt, season)
	corrupt = before.duplicate(true)
	corrupt.rewards[1].rewardId = corrupt.rewards[0].rewardId
	_checks["duplicate physical entitlement rejected"] = not Model.valid_rewards(corrupt, season)
	_checks["cross season response rejected"] = not Model.valid_rewards(before, "different-source")
	corrupt = pack.duplicate(true)
	corrupt.grants[0].amount = 2
	_checks["two copies cannot impersonate a three-copy pack"] = not Model.valid_claim(corrupt, pack_before, "Mage")
	corrupt = final_inventory.duplicate(true)
	corrupt.selection.titleId = "first-threshold"
	_checks["owned collection cannot impersonate a title"] = not Model.valid_inventory(corrupt)
	corrupt = final_inventory.duplicate(true)
	corrupt.selection.avatarFrameId = "unowned"
	_checks["unowned cosmetic selection rejected"] = not Model.valid_inventory(corrupt)
	return {"ok": not _checks.values().has(false), "checks": _checks, "real_csharp_http_bytes": true, "actual_native_http_network": false, "rendered_frames": false}
