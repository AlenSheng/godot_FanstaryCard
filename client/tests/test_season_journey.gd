extends RefCounted

const Model=preload("res://ui/season_journey_model.gd")
const P=preload("res://ui/palette.gd")

class Gateway extends Node:
	signal released
	var session_generation := 41
	var requests: Array=[]
	var replies: Dictionary={}
	func request(path: String,method: int=HTTPClient.METHOD_GET,data: Variant=null,_quiet: Array=[]) -> Dictionary:
		var index := requests.size();requests.append({"path":path,"method":method,"data":data})
		while not replies.has(index): await released
		return replies[index]
	func complete(index: int,response: Dictionary) -> void:
		replies[index]=response;released.emit()

class Host extends "res://ui/main.gd":
	func _render() -> void: pass
	func _schedule_render() -> void: pass
	func _sync_account_session() -> void: pass

static func snapshot(experience: int=7000,state: String="Active",season: String="current") -> Dictionary:
	var levels: Array=[]
	var cumulative := 0
	var level := 0
	var into := experience
	for index in 30:
		var cost := 200+15*index;cumulative+=cost
		var reached := experience>=cumulative
		levels.append({"level":index+1,"requiredExperience":cost,"cumulativeExperience":cumulative,"stage":"Main" if index<20 else "Collection","reached":reached})
		if reached: level+=1;into-=cost
	var contracts: Array=[]
	for week in range(1,7 if state=="Ended" else 4):
		for kind in ["Extracted","Elite","Boss"]:
			var target: int={"Extracted":3,"Elite":5,"Boss":1}[kind]
			contracts.append({"contractId":"weekly-"+kind.to_lower(),"week":week,"completionKind":kind,"target":target,"progress":target if experience==12525 else 0,"experienceReward":300,"experienceCredited":300 if experience==12525 else 0,"opensAt":"2026-11-01T00:00:00+08:00","completedAt":"2026-11-21T00:00:00+08:00" if experience==12525 else null,"state":"Completed" if experience==12525 else "Expired" if state=="Ended" else "Open"})
	var response := {"state":state,"seasonId":season,"configVersion":"season-v1-config-11","startsAt":"2026-11-01T00:00:00+08:00","endsAt":"2026-12-13T00:00:00+08:00","durationDays":42,"day":42 if state=="Ended" else 21,"experience":experience,"level":level,"experienceIntoLevel":into,"experienceToNext":0 if level==30 else int(levels[level].requiredExperience),"maximumExperience":12525,"mainRewardLevels":20,"referenceExperience":6850,"maximumCatchUpMultiplier":2,"catchUpActive":state=="Active" and experience<6850,"version":9007199254740997,"contracts":contracts,"levels":levels,"seasons":[{"seasonId":"current","state":"Active","configVersion":"season-v1-config-11","startsAt":"2026-11-01T00:00:00+08:00","endsAt":"2026-12-13T00:00:00+08:00"},{"seasonId":"old","state":"Ended","configVersion":"season-v1-config-11","startsAt":"2026-09-20T00:00:00+08:00","endsAt":"2026-11-01T00:00:00+08:00"}],"nextOffset":null}
	if season=="old":response.startsAt="2026-09-20T00:00:00+08:00";response.endsAt="2026-11-01T00:00:00+08:00"
	if state=="Upcoming": response.day=0;response.referenceExperience=0;response.catchUpActive=false;response.contracts=[]
	if state in ["None","Unavailable","Disabled"]:
		response.levels=[];response.contracts=[];response.catchUpActive=false
		if state=="None":response.seasonId=null;response.configVersion=null;response.startsAt=null;response.endsAt=null
	return response

func run_test() -> Dictionary:
	var checks := {}
	var current := snapshot()
	checks["complete authoritative level metadata accepted"]=Model.valid(current) and current.level==20
	checks["exact int64 version retained"]=current.version==9007199254740997
	checks["catch-up and completed tracks accepted"]=Model.valid(snapshot(48)) and Model.valid(snapshot(12525))
	checks["upcoming has no opened contracts"]=Model.valid(snapshot(0,"Upcoming"))
	checks["absent original is not current progress"]=Model.valid(snapshot(0,"None")) and snapshot(0,"None").seasonId==null
	checks["unavailable source retains recorded XP without deriving levels"]=Model.valid(snapshot(3200,"Unavailable")) and snapshot(3200,"Unavailable").levels.is_empty()
	checks["inconsistent aggregate rejected"]=not Model.valid(current.merged({"experience":12526},true))
	checks["wrong current-level projection rejected"]=not Model.valid(current.merged({"level":0},true))
	checks["unknown multiplier rejected"]=not Model.valid(current.merged({"maximumCatchUpMultiplier":3},true))
	var wrong := snapshot();wrong.levels[20].stage="Main"
	checks["collection levels cannot masquerade as main levels"]=not Model.valid(wrong)
	wrong=snapshot();wrong.contracts[0].progress=4
	checks["progress may not exceed original target"]=not Model.valid(wrong)
	wrong=snapshot();wrong.contracts.append(wrong.contracts[0].duplicate(true))
	checks["same week and kind cannot duplicate"]=not Model.valid(wrong)
	var language := P.language();P.set_language("ar")
	var lri := String.chr(0x2066);var pdi := String.chr(0x2069)
	checks["Arabic current total fraction remains LTR"]=Model.display_text(P.localized("journey_summary") % [20,7000,12525]).contains(lri+"7000 / 12525"+pdi)
	checks["Arabic current next fraction remains LTR"]=Model.display_text(P.localized("journey_next") % [150,500]).contains(lri+"150 / 500"+pdi)
	checks["Arabic weekly progress target fraction remains LTR"]=Model.display_text(P.localized("journey_contract_progress") % [0,3,300]).contains(lri+"0 / 3"+pdi)
	checks["Arabic season picker keeps complete ISO date together"]=Model.season_label(current.seasons[0]).contains(lri+"2026-11-01"+pdi)
	P.set_language(language)
	var saved_gateway: Variant=Game.gateway;var saved_lobby: Dictionary=Game.lobby;var saved_busy: bool=Game.busy;var muted: bool=Sound.muted
	Sound.muted=true;var gateway := Gateway.new();Game.gateway=gateway;Game.lobby={"wallet":{"gold":777}};Game.busy=false
	var host := Host.new();host.screen="journey";var c=host.journey_controller;c.attach(host);c.reload()
	host._navigate("activities");host._navigate("journey")
	checks["actual Main routes both pages and starts current read"]=gateway.requests.size()==3 and gateway.requests[1].path.begins_with("/api/v1/season-activities?") and gateway.requests[2].path.begins_with("/api/v1/season-journey?")
	gateway.complete(0,{"ok":true,"data":snapshot(12525)})
	checks["actual navigation A B A rejects previous identical source"]=c.state.is_empty() and c.loading
	gateway.complete(1,{"ok":true,"data":{"events":[]}});gateway.complete(2,{"ok":true,"data":snapshot()})
	checks["current response supplies level20 only"]=c.state.experience==7000 and c.state.level==20 and not c.loading
	c.choose(1)
	checks["history selection sends exact original season"]=gateway.requests.size()==4 and gateway.requests[3].path.contains("seasonId=old")
	c.leave();c.reload();gateway.complete(3,{"ok":true,"data":snapshot(12525,"Ended","old")})
	checks["superseded same-old-season read ignored"]=c.state.is_empty() and c.loading
	var old := snapshot(2800,"Ended","old");old.nextOffset=50;gateway.complete(4,{"ok":true,"data":old})
	c.reload(true)
	checks["history cursor retains original selected scope"]=gateway.requests[5].path.contains("offset=50") and gateway.requests[5].path.contains("seasonId=old")
	gateway.session_generation+=1;Game.busy=true;gateway.complete(5,{"ok":true,"data":snapshot(12525,"Ended","old")})
	checks["old account reply cannot replace progress or clear new busy state"]=c.state.experience==2800 and Game.busy
	c.reset();Game.busy=false;c.reload();gateway.complete(6,{"ok":true,"data":snapshot(0,"None")})
	checks["missing original never falls back to previous XP"]=c.state.state=="None" and c.state.experience==0 and c.state.seasonId==null
	c.reload();var invalid := snapshot();invalid.maximumExperience=1;gateway.complete(7,{"ok":true,"data":invalid})
	checks["invalid server projection displays unavailable rather than cached XP"]=c.failed and c.state.is_empty()
	checks["all actions are GET and never optimistically change wallets"]=gateway.requests.all(func(row):return row.method==HTTPClient.METHOD_GET) and Game.lobby.wallet.gold==777
	host.free();gateway.free();Game.gateway=saved_gateway;Game.lobby=saved_lobby;Game.busy=saved_busy;Sound.muted=muted
	return {"ok":not checks.values().has(false),"checks":checks}
