extends RefCounted

const Proto=preload("res://network/protobuf.gd")
const Http=preload("res://network/http_protocol.gd")

func run_test() -> Dictionary:
	var checks := {}
	var proto := Proto.new(true)
	var wallet: Dictionary=proto.decode_http("SeasonWalletResponse",proto.encode("SeasonWalletResponse",{"season_id":"current","challenge_marks":77,"blueprint_marks":4,"orange_blueprint_marks":14}))
	checks["three balances remain independent"]=wallet.challengeMarks==77 and wallet.blueprintMarks==4 and wallet.orangeBlueprintMarks==14
	var old: Dictionary=proto.decode_http("SeasonWalletResponse",proto.encode("SeasonWalletResponse",{"season_id":"old","challenge_marks":77}))
	checks["old marks never become new blueprint money"]=old.challengeMarks==77 and old.blueprintMarks==0 and old.orangeBlueprintMarks==0
	var craft := {"seasonId":"current","quality":"Orange","slot":"Feet","element":"Water","wishedEffect":"Vitality","expectedWalletVersion":9007199254740993}
	var decoded: Dictionary=proto.decode_http("CraftEquipmentRequest",proto.encode("CraftEquipmentRequest",Http.to_wire("CraftEquipmentRequest",craft)))
	checks["craft choice and exact wallet version roundtrip"]=decoded==craft
	var recipe := {"recipeId":"11111111-1111-1111-1111-111111111111","seasonId":"current","quality":"Purple","slot":"Feet","element":"Fire","secondaryTrait":"ForcedEscape","statsVersion":"season-equipment-v1","sourceItemId":"22222222-2222-2222-2222-222222222222"}
	decoded=proto.decode_http("SeasonRecipeResponse",proto.encode("SeasonRecipeResponse",Http.to_wire("SeasonRecipeResponse",recipe)))
	checks["unaffixed purple recipe remains null"]=decoded.effectAffix==null and decoded.secondaryTrait=="ForcedEscape"
	var rebuild := {"seasonId":"current","recipeId":recipe.recipeId,"bodyEquipmentId":recipe.sourceItemId,"expectedBodyVersion":9007199254740993,"expectedWalletVersion":11}
	decoded=proto.decode_http("ReforgeEquipmentRequest",proto.encode("ReforgeEquipmentRequest",Http.to_wire("ReforgeEquipmentRequest",rebuild)))
	checks["one real body and both versions roundtrip"]=decoded==rebuild
	for row in [["/api/v1/season-crafting/",HTTPClient.METHOD_GET,"SeasonCraftingResponse"],["/api/v1/season-crafting/reforge-quote?seasonId=current",HTTPClient.METHOD_GET,"ReforgeQuoteResponse"],["/api/v1/season-crafting/craft",HTTPClient.METHOD_POST,"CraftEquipmentResponse"],["/api/v1/season-crafting/recipes/learn",HTTPClient.METHOD_POST,"LearnSeasonRecipeResponse"],["/api/v1/season-crafting/reforge",HTTPClient.METHOD_POST,"ReforgeEquipmentResponse"]]:
		checks[str(row[0])+" route contract"]=Http.route(str(row[0]),int(row[1])).get("response")==row[2]
	checks["codec reports no error"]=proto.error.is_empty()
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"Native typed blueprint/recipe/crafting HTTP codec and route controls; no UI or live API claim."}
