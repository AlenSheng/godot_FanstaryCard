extends RefCounted

const Wallets = preload("res://ui/enhancement_wallets.gd")
const Http = preload("res://network/http_protocol.gd")
const Proto = preload("res://network/protobuf.gd")
const P = preload("res://ui/palette.gd")

func run_test() -> Dictionary:
	var checks := {}
	checks["failed quote never implies historical wallet"]=Wallets.source_text({"error":true}).is_empty()
	var target := {"instanceId":"target","quality":"Purple","location":"Inventory","seasonId":"current","assetScope":"ActiveSeason","statsVersion":"season-equipment-v1"}
	var material := target.duplicate(true)
	material.instanceId="material"
	checks["same quality and original season eligible"]=Wallets.eligible_material(target,material)
	for pair in [["quality","Blue"],["seasonId","old"],["assetScope","ArchivedSeason"],["statsVersion","foreign"],["sourceKind","BotReward"],["sourceKind","Borrowed"],["location","Equipped"],["instanceId","target"]]:
		var invalid: Dictionary=material.duplicate(true)
		invalid[pair[0]]=pair[1]
		checks["reject "+str(pair)]=not Wallets.eligible_material(target,invalid)
	var summary := {"seasonId":"current","historicalEquipmentFragments":99999,"wallet":{"seasonId":"current","equipmentFragments":500,"version":10},"fragmentWallets":[{"seasonId":"current","equipmentFragments":500,"version":10},{"seasonId":"old","equipmentFragments":300,"version":20}]}
	var receipt := {"fragmentSourceSeasonId":"current","fragmentWalletVersion":11,"equipmentFragments":460}
	var updated := Wallets.update_summary(summary,receipt)
	checks["current wallet and wallet-list row updated"]=updated.wallet.equipmentFragments==460 and updated.fragmentWallets[0].equipmentFragments==460
	checks["permanent and other-season balances untouched"]=updated.historicalEquipmentFragments==99999 and updated.fragmentWallets[1].equipmentFragments==300
	checks["summary input not mutated"]=summary.wallet.equipmentFragments==500
	checks["older replay cannot regress wallet"]=Wallets.update_summary(updated,receipt.merged({"fragmentWalletVersion":9,"equipmentFragments":900},true)).wallet.equipmentFragments==460
	var archived := Wallets.update_summary(updated,{"fragmentSourceSeasonId":"old","fragmentWalletVersion":21,"equipmentFragments":292})
	checks["archived weapon payment affects only its own wallet"]=archived.wallet.equipmentFragments==460 and archived.fragmentWallets[1].equipmentFragments==292
	var proto := Proto.new(true)
	var body := {"expectedVersion":7,"materialEquipmentId":"11111111-1111-1111-1111-111111111111","materialExpectedVersion":9007199254740993}
	var wire := Http.to_wire("EnhanceEquipmentRequest",body)
	var decoded := Http.from_wire("EnhanceEquipmentRequest",proto.decode("EnhanceEquipmentRequest",proto.encode("EnhanceEquipmentRequest",wire)))
	checks["material version is exact int64 on actual codec"]=proto.error.is_empty() and decoded.materialExpectedVersion==9007199254740993
	var old: Dictionary=Http.from_wire("EnhanceEquipmentRequest",proto.decode("EnhanceEquipmentRequest",proto.encode("EnhanceEquipmentRequest",{"expected_version":7})))
	checks["old request leaves new material version absent"]=old.materialExpectedVersion==null
	var previous := P.language()
	for locale in P.languages():
		P.set_language(str(locale))
		checks[str(locale)+" source localized"]=Wallets.source_text(receipt).contains("current") and not Wallets.source_text(receipt).contains("%s") and not Wallets.source_text({}).contains("enhance_source_")
	P.set_language(previous)
	var previous_lobby: Dictionary=Game.lobby
	Game.lobby={"season":summary,"materials":{"equipmentFragments":99999},"inventory":{"equipments":[],"summary":{"capacity":50}}}
	var host=load("res://ui/main.gd").new()
	host.inventory={"equipments":[],"summary":{"capacity":50}}
	host._apply_account_mutation("/equipment/target/enhance",{},receipt.merged({"equipment":{"instanceId":"target","slot":"Head","level":4,"version":8}},true))
	checks["actual UI receipt never overwrites historical materials"]=Game.lobby.materials.equipmentFragments==99999 and Game.lobby.season.wallet.equipmentFragments==460
	host.free()
	Game.lobby=previous_lobby
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"Actual client wallet model, codec and account receipt; no rendered frame or live network claim."}
