extends RefCounted

const P = preload("res://ui/palette.gd")

static func source_id(receipt: Dictionary) -> String:
	var value: Variant = receipt.get("fragmentSourceSeasonId")
	return "" if value == null else str(value)

static func source_text(receipt: Dictionary) -> String:
	if receipt.get("error",false): return ""
	var source := source_id(receipt)
	return P.localized("enhance_source_historical") if source.is_empty() else P.localized("enhance_source_season") % source

static func eligible_material(target: Dictionary, material: Dictionary) -> bool:
	return material.get("instanceId") != target.get("instanceId") and material.get("location") == "Inventory" \
		and material.get("quality") == target.get("quality") and material.get("seasonId") == target.get("seasonId") \
		and material.get("assetScope") == target.get("assetScope") \
		and (target.get("seasonId") == null or target.get("statsVersion") == material.get("statsVersion")) \
		and material.get("sourceKind") not in ["BotReward", "Borrowed"]

static func update_summary(summary: Dictionary, receipt: Dictionary) -> Dictionary:
	var result := summary.duplicate(true)
	var source := source_id(receipt)
	if source.is_empty(): return result
	var version := int(receipt.get("fragmentWalletVersion", 0))
	var fragments := int(receipt.get("equipmentFragments", 0))
	var wallet: Variant = result.get("wallet")
	if wallet is Dictionary and str(wallet.get("seasonId", "")) == source and version >= int(wallet.get("version", 0)):
		wallet["equipmentFragments"] = fragments
		wallet["version"] = version
	var wallets: Array = result.get("fragmentWallets", [])
	for entry in wallets:
		if str(entry.get("seasonId", "")) == source and version >= int(entry.get("version", 0)):
			entry["equipmentFragments"] = fragments
			entry["version"] = version
	return result
