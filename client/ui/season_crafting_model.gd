extends RefCounted

# Preview only. The server checks its original configuration, versions, and balances again.
static func payment(offer: Dictionary, wallet: Dictionary) -> Dictionary:
	var cost := int(offer.get("markCost",0))
	var blue := mini(maxi(0,int(wallet.get("blueprintMarks",0))),cost) if offer.get("markKind")=="Blueprint" else 0
	var orange := cost-blue
	return {"blueprints":blue,"orangeBlueprints":orange,"canAfford":cost>0 and orange<=int(wallet.get("orangeBlueprintMarks",0))}

static func learnable(item: Dictionary, season_id: String) -> bool:
	return item.get("seasonId")==season_id and item.get("assetScope")=="ActiveSeason" \
		and item.get("quality") in ["Purple","Orange"] and item.get("sourceKind") in ["NaturalDrop","MarkCraft"] \
		and not item.get("recipeExtracted",false) and item.get("location") in ["Inventory","Equipped"]

static func rebuild_body(item: Dictionary, recipe: Dictionary) -> bool:
	return item.get("seasonId")==recipe.get("seasonId") and item.get("assetScope")=="ActiveSeason" \
		and item.get("quality")==recipe.get("quality") and item.get("statsVersion")==recipe.get("statsVersion") \
		and item.get("sourceKind") in ["NaturalDrop","MarkCraft","TemplateReforge"] \
		and item.get("location") in ["Inventory","Equipped"]

static func wish_progress(state: Dictionary, selection: Dictionary) -> int:
	for row in state.get("wishes",[]):
		if row.get("quality")==selection.get("quality") and row.get("slot")==selection.get("slot") \
			and row.get("element")==selection.get("element") and row.get("wishedEffect")==selection.get("wishedEffect"):
			return int(row.get("failures",0))
	return 0

static func sample_status(item: Dictionary) -> String:
	if item.get("sourceKind")=="TemplateReforge": return "season_craft_status_reforged"
	if item.get("recipeExtracted",false): return "season_craft_status_extracted"
	if item.get("quality") in ["Purple","Orange"] and item.get("sourceKind") in ["NaturalDrop","MarkCraft"]: return "season_craft_status_sample"
	return "season_craft_status_unavailable"

static func wallet_summary(summary: Dictionary, wallet: Dictionary) -> Dictionary:
	var result := summary.duplicate(true)
	var source: String=str(wallet.get("seasonId",""))
	var current: Variant=result.get("wallet")
	if current is Dictionary and current.get("seasonId")==source and int(wallet.get("version",0))>=int(current.get("version",0)):
		result["wallet"]=wallet.duplicate(true)
	var rows: Array=result.get("fragmentWallets",[])
	for index in rows.size():
		if rows[index].get("seasonId")==source and int(wallet.get("version",0))>=int(rows[index].get("version",0)):
			rows[index]=wallet.duplicate(true)
	return result
