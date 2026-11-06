extends RefCounted

const Model=preload("res://ui/season_activity_model.gd")

static func event() -> Dictionary:
	return {"seasonId":"old-season","eventId":"activity-one","configVersion":"season-v1-config-10","state":"Active","startsAt":"2098-01-01T00:00:00Z","endsAt":"2098-01-04T00:00:00Z","earned":12,"spent":0,"available":12,"tokenCap":12,"accountVersion":9007199254740997,"canExchange":true,"options":[{"ruleId":"event-fragments","costTokens":3,"rewardKind":"bound_fragments","rewardCount":10,"eventLimit":4,"used":0},{"ruleId":"event-class","costTokens":3,"rewardKind":"bound_class_soul","rewardCount":2,"eventLimit":4,"used":0},{"ruleId":"event-potion","costTokens":6,"rewardKind":"potion","rewardCount":1,"eventLimit":1,"used":0}],"rewards":[]}

func run_test() -> Dictionary:
	var checks := {}
	var e := event()
	var body := Model.exchange_body(e,e.options[0],"Mage")
	checks["source event and exact int64 account version captured"]=body.seasonId=="old-season" and body.expectedAccountVersion==9007199254740997 and body.quantity==1 and not body.has("rewardAmount")
	checks["class choice captured"]=Model.exchange_body(e,e.options[1],"Priest").heroClass=="Priest"
	checks["unknown class cannot submit"]=Model.exchange_body(e,e.options[1],"Warrior").is_empty()
	checks["late original event can use only its own balance"]=not Model.exchange_body(e.merged({"state":"Ended"},true),e.options[0],"Mage").is_empty()
	checks["upcoming is never redeemable"]=Model.exchange_body(e.merged({"state":"Upcoming"},true),e.options[0],"Mage").is_empty()
	checks["unavailable never redeemable"]=Model.exchange_body(e.merged({"canExchange":false},true),e.options[0],"Mage").is_empty()
	checks["different period has a distinct balance key"]=Model.key(e)!=Model.key(e.merged({"eventId":"activity-two"},true))
	checks["inconsistent shared budget rejected"]=not Model.valid(e.merged({"available":11},true))
	checks["earned cap cannot be widened by client"]=not Model.valid(e.merged({"earned":16,"available":16},true))
	checks["spent balance blocks potion"]=Model.exchange_body(e.merged({"spent":9,"available":3},true),e.options[2],"Mage").is_empty()
	checks["one potion limit shared"]=Model.exchange_body(e,e.options[2].merged({"used":1},true),"Mage").is_empty()
	checks["all class choices share original rule counter"]=Model.exchange_body(e,e.options[1].merged({"used":4},true),"Guardian").is_empty()
	checks["red and gold cannot be injected"]=not Model.option_valid(e.options[0].merged({"rewardKind":"red-material"},true)) and not Model.option_valid(e.options[0].merged({"rewardKind":"gold"},true))
	checks["client may not widen reward amounts"]=not Model.option_valid(e.options[0].merged({"rewardCount":100},true))
	return {"ok":not checks.values().has(false),"checks":checks}
