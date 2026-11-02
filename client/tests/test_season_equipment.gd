extends RefCounted

const Model=preload("res://ui/equipment_compare_model.gd")
const Details=preload("res://ui/equipment_details.gd")
const Numbers=preload("res://ui/numerical_details.gd")
const Index=preload("res://data/catalog_index.gd")
const P=preload("res://ui/palette.gd")
const SLOTS=["Head","Chest","Hands","Legs","Feet"]

func _armor(sample: int, level: int) -> Array:
	var result: Array=[]
	for slot_index in 5:
		var quality := "Purple"
		if sample == 1: quality = "Green" if slot_index < 3 else "Blue"
		elif sample == 2: quality = "Blue"
		elif sample >= 4: quality = "Orange" if slot_index == 0 else "Purple"
		result.append({"slot":SLOTS[slot_index],"quality":quality,"level":level,"element":"Fire","secondaryTrait":"DrawInterval","statsVersion":"season-equipment-v1"})
	return result

func run_test() -> Dictionary:
	var checks := {}
	var vectors := [[1,0,.43,.24,3.24],[2,1,.65,.325,2.93],[3,2,1.0,.51,2.44],[4,3,1.21,.586,2.228],[5,5,1.47,.65,2.06]]
	for row in vectors:
		var armor := _armor(int(row[0]),int(row[1]))
		var data := Numbers.inspect(armor,"Mage")
		checks["sample %s damage" % row[0]]=is_equal_approx(data.damage_Fire.raw,float(row[2]))
		checks["sample %s raw resistance" % row[0]]=is_equal_approx(data.resistance_Fire.raw,float(row[3]))
		checks["sample %s capped resistance" % row[0]]=is_equal_approx(data.resistance_Fire.effective,minf(.6,float(row[3])))
		checks["sample %s natural interval" % row[0]]=is_equal_approx(data.interval_seconds.effective,float(row[4]))
		checks["sample %s no unrelated elemental cap" % row[0]]=not data.has("resistance_Water")
	var armor := _armor(5,5)
	armor[0].quality="Red"
	var red := Numbers.inspect(armor,"Mage")
	checks["red .71 raw .6 effective"]=is_equal_approx(red.resistance_Fire.raw,.71) and is_equal_approx(red.resistance_Fire.effective,.6)
	checks["red base 1.62 and 1.96 seconds"]=is_equal_approx(red.damage_Fire.raw,1.62) and is_equal_approx(red.interval_seconds.effective,1.96)
	armor[0]["uniqueAffix"]="Inferno"
	checks["inferno uses main element and adds .15"]=is_equal_approx(Numbers.inspect(armor,"Mage").damage_Fire.raw,1.77)
	armor[0].uniqueAffix="RapidDraw"
	checks["rapid floor remains 1.8"]=is_equal_approx(Numbers.inspect(armor,"Mage").interval_seconds.effective,1.8)
	var shoes := _armor(3,0)
	shoes[4].secondaryTrait="ForcedEscape"
	checks["escape shoes omit interval"]=is_equal_approx(Numbers.inspect(shoes,"Mage").interval_seconds.effective,2.88)
	var legacy := _armor(3,0)
	for item in legacy: item.erase("statsVersion")
	checks["legacy purple0 retains old floor"]=is_equal_approx(Numbers.inspect(legacy,"Mage").interval_seconds.effective,1.8)
	checks["unknown current stats version rejected"]=Index.quality("Purple",{},"unknown-stats").is_empty()
	var unknown := _armor(3,0)
	unknown[0].statsVersion="unknown-stats"
	checks["unknown inspection unavailable"]=Numbers.inspect(unknown,"Mage").is_empty()
	var previous := P.language()
	for language in P.languages():
		P.set_language(str(language))
		for unique in ["Inferno","RapidDraw","ChainDraw","Scavenge","GoldenCicada"]:
			var item := {"slot":"Feet" if unique == "GoldenCicada" else "Head","quality":"Red","level":5,"element":"Fire","secondaryTrait":"DrawInterval","uniqueAffix":unique,"statsVersion":"season-equipment-v1"}
			var label := Details.unique_name(item)
			var description := Details.description(item)
			checks[str(language)+" "+unique+" localized complete"]=not label.is_empty() and description.contains(label) and not description.contains("equipment_unique_") and not description.contains("%s")
	P.set_language(previous)
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"Actual versioned client models and eleven locale descriptions; no rendered frame, gameplay balance or red-mint quota claim."}
