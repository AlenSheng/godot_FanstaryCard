extends RefCounted

const P=preload("res://ui/palette.gd")
const Dates=preload("res://ui/season_activity_model.gd")

static func available(state: Dictionary) -> bool:
	return state.get("state") in ["Active","Upcoming","Ended"]

static func valid(state: Dictionary) -> bool:
	if state.get("state") not in ["None","Disabled","Unavailable","Active","Upcoming","Ended"]: return false
	if int(state.get("experience",-1))<0 or int(state.get("version",-1))<0: return false
	if not state.get("seasons",[]) is Array: return false
	if not available(state): return state.get("levels",[]).is_empty() and state.get("contracts",[]).is_empty()
	if str(state.get("seasonId","")).is_empty() or str(state.get("configVersion","")).is_empty(): return false
	if int(state.get("durationDays",0)) not in range(30,61) or int(state.get("day",-1)) not in range(int(state.durationDays)+1): return false
	if int(state.get("mainRewardLevels",0))!=20 or int(state.get("maximumCatchUpMultiplier",0))!=2: return false
	var levels: Array=state.get("levels",[])
	if levels.size()!=30: return false
	var cumulative := 0
	var reached := 0
	var into := int(state.experience)
	for index in 30:
		var row: Dictionary=levels[index]
		if int(row.get("level",0))!=index+1 or int(row.get("requiredExperience",0))<1: return false
		cumulative+=int(row.requiredExperience)
		if int(row.get("cumulativeExperience",0))!=cumulative or row.get("stage")!=("Main" if index<20 else "Collection"): return false
		var completed: bool=int(state.experience)>=cumulative
		if bool(row.get("reached",false))!=completed: return false
		if completed: reached+=1;into-=int(row.requiredExperience)
	if int(state.get("maximumExperience",0))!=cumulative or int(state.experience)>cumulative or int(state.get("level",-1))!=reached: return false
	if int(state.get("experienceIntoLevel",-1))!=into or int(state.get("experienceToNext",-1))!=(0 if reached==30 else int(levels[reached].requiredExperience)): return false
	var reference := int(state.get("referenceExperience",-1))
	if reference<0 or reference>int(levels[19].cumulativeExperience): return false
	if bool(state.get("catchUpActive",false))!=(state.state=="Active" and int(state.experience)<reference): return false
	var seen := {}
	for row in state.get("contracts",[]):
		var key := str(row.get("week",0))+"/"+str(row.get("completionKind",""))
		if seen.has(key) or str(row.get("contractId","")).is_empty() or row.get("completionKind") not in ["Extracted","Elite","Boss"]: return false
		seen[key]=true
		if int(row.get("week",0)) not in range(1,10) or int(row.get("target",0)) not in range(1,101): return false
		if int(row.get("progress",-1)) not in range(int(row.target)+1) or int(row.get("experienceReward",0))!=300 or int(row.get("experienceCredited",-1)) not in range(301): return false
		if row.get("state") not in ["Open","Completed","Expired"]: return false
		if (row.state=="Completed")!=(int(row.progress)==int(row.target)): return false
		if row.state!="Completed" and int(row.experienceCredited)!=0: return false
	return true

static func season_label(season: Dictionary) -> String:
	var day: String=Dates.date_label(str(season.get("startsAt",""))).left(10)
	if P.languages()[P.language()].get("direction")=="rtl": day=String.chr(0x2066)+day+String.chr(0x2069)
	return day+" · "+P.localized(state_key(str(season.get("state","Unavailable"))))

static func display_text(value: String) -> String:
	return P.system_display_text(value)

static func state_key(value: String) -> String:
	return {"Active":"activity_active","Upcoming":"activity_upcoming","Ended":"activity_ended","None":"journey_none","Disabled":"journey_disabled"}.get(value,"journey_unavailable")

static func contract_title(kind: String) -> String:
	return P.localized({"Extracted":"journey_extraction","Elite":"journey_elite","Boss":"journey_boss"}.get(kind,"journey_unavailable"))
