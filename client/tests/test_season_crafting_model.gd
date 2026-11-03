extends RefCounted

const Model=preload("res://ui/season_crafting_model.gd")

func run_test() -> Dictionary:
	var checks := {}
	var wallet := {"challengeMarks":77,"blueprintMarks":1,"orangeBlueprintMarks":3}
	var paid := Model.payment({"markKind":"Blueprint","markCost":4},wallet)
	checks["higher type offsets lower one-to-one"]=paid.blueprints==1 and paid.orangeBlueprints==3 and paid.canAfford
	checks["lower cannot pay orange"]=not Model.payment({"markKind":"OrangeBlueprint","markCost":14},wallet).canAfford
	checks["legacy opaque balance cannot pay"]=not Model.payment({"markKind":"Blueprint","markCost":4},{"challengeMarks":77}).canAfford
	var sample := {"seasonId":"s","assetScope":"ActiveSeason","quality":"Purple","sourceKind":"NaturalDrop","recipeExtracted":false,"location":"Inventory","statsVersion":"season-equipment-v1","effectAffix":null}
	checks["legal unaffixed purple remains learnable"]=Model.learnable(sample,"s")
	checks["extracted sample blocked"]=not Model.learnable(sample.merged({"recipeExtracted":true},true),"s")
	checks["recast never teaches"]=not Model.learnable(sample.merged({"sourceKind":"TemplateReforge"},true),"s")
	checks["recast may remain a real rebuild body"]=Model.rebuild_body(sample.merged({"sourceKind":"TemplateReforge"},true),sample)
	checks["wrong season body blocked"]=not Model.rebuild_body(sample.merged({"seasonId":"old"},true),sample)
	checks["bot and activity pure material blocked"]=not Model.rebuild_body(sample.merged({"sourceKind":"BotReward"},true),sample) and not Model.rebuild_body(sample.merged({"sourceKind":"ActivityMaterial"},true),sample)
	var selected := {"quality":"Purple","slot":"Head","element":"Fire","wishedEffect":"Vitality"}
	var state := {"wishes":[selected.merged({"failures":2},true)]}
	checks["wish groups do not share progress"]=Model.wish_progress(state,selected)==2 and Model.wish_progress(state,selected.merged({"wishedEffect":"Bulwark"},true))==0
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"Crafting UI data-model controls only; no rendered screen or live API claim."}
