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
