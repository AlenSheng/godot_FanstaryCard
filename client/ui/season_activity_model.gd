extends RefCounted

const P=preload("res://ui/palette.gd")
const Gateway=preload("res://network/gateway.gd")
const REWARDS={"bound_fragments":["equipment_fragments",10,3,4],"bound_warrior_soul":["word_warrior_soul",6,3,4],"bound_class_soul":["word_class_soul",2,3,4],"potion":["health_potion",1,6,1]}

static func key(event: Dictionary) -> String:
	return str(event.get("seasonId",""))+"/"+str(event.get("eventId",""))

static func valid(event: Dictionary) -> bool:
	return not str(event.get("seasonId","")).is_empty() and not str(event.get("eventId","")).is_empty() and not str(event.get("configVersion","")).is_empty() and int(event.get("tokenCap",0))==12 and int(event.get("earned",-1)) in range(13) and int(event.get("spent",-1)) in range(int(event.get("earned",-1))+1) and int(event.get("available",-1))==int(event.get("earned",0))-int(event.get("spent",0))

static func option_valid(option: Dictionary) -> bool:
	var rule: Array=REWARDS.get(str(option.get("rewardKind","")),[])
	return rule.size()==4 and int(option.get("rewardCount",0))==rule[1] and int(option.get("costTokens",0))==rule[2] and int(option.get("eventLimit",0))==rule[3] and not str(option.get("ruleId","")).is_empty()

static func exchange_body(event: Dictionary,option: Dictionary,hero: String) -> Dictionary:
	if not valid(event) or not option_valid(option) or not event.get("canExchange",false) or event.get("state") not in ["Active","Ended"]: return {}
	if int(event.available)<int(option.costTokens) or int(option.get("used",0))>=int(option.eventLimit): return {}
	var body := {"seasonId":event.seasonId,"ruleId":option.ruleId,"quantity":1,"expectedAccountVersion":int(event.get("accountVersion",0))}
	if option.rewardKind=="bound_class_soul":
		if hero not in ["Mage","Priest","Guardian"]: return {}
		body["heroClass"]=hero
	return body

static func reward_title(reward: Dictionary) -> String:
	var kind: String=str(reward.get("rewardKind",""))
	var rule: Array=REWARDS.get(kind,[])
	if rule.is_empty(): return P.localized("activity_unavailable")
	var title: String=P.localized(str(rule[0]))
	if kind=="bound_class_soul" and reward.get("heroClass") in ["Mage","Priest","Guardian"]:
		title=P.localized("class_"+str(reward.heroClass).to_lower())+" · "+title
	return title+" ×"+str(reward.get("rewardAmount",reward.get("rewardCount",0)))

static func event_title(event: Dictionary) -> String:
	var index := 1 if event.get("eventId")=="activity-one" else 2
	return P.localized("activity_period") % index+" · "+str(event.get("seasonId",""))

static func date_label(value: String) -> String:
	var timestamp := Gateway.parse_expiry(value)
	if timestamp<=0: return "—"
	return Time.get_datetime_string_from_unix_time(int(timestamp)+8*3600).replace("T"," ").left(16)

static func window_label(event: Dictionary) -> String:
	var value := date_label(str(event.get("startsAt","")))+" → "+date_label(str(event.get("endsAt","")))+" · UTC+8"
	# Keep the complete chronological range together inside an RTL sentence.
	# Isolating each number alone reverses ISO dates and separates their times.
	return String.chr(0x2066)+value+String.chr(0x2069) if P.languages()[P.language()].get("direction")=="rtl" else value
