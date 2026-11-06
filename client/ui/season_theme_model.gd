extends RefCounted

const P=preload("res://ui/palette.gd")
const CATALOG=preload("res://data/catalog.json")

static func selected(index: Dictionary={}) -> Dictionary:
	var tables: Dictionary=index.get("tables",{}) if not index.is_empty() else CATALOG.data.tables
	var rules: Array=tables.get("SeasonThemeRules",[])
	if rules.size()!=1 or not rules[0].get("enabled",false): return {}
	for theme in tables.get("SeasonThemes",[]):
		if theme.get("theme_id")==rules[0].get("selected_theme"): return theme
	return {}

static func room_theme(room: Dictionary,index: Dictionary={}) -> Dictionary:
	if not room.get("season") is Dictionary or room.season.get("ruleset_id",room.season.get("rulesetId",""))!="season-v1": return {}
	return selected(index)

static func title(theme: Dictionary) -> String:
	return P.localized(str(theme.get("name_key","chaos_realm")))

static func phases(theme: Dictionary,phase: int) -> String:
	return P.localized("season_theme_phase") % [phase,P.word(theme.get("phase%d_primary" % phase,"")),P.word(theme.get("phase%d_secondary" % phase,""))]

static func boss_tint(theme: Dictionary) -> Color:
	return {"Wood":Color(0.45,1.0,0.58),"Earth":Color(0.87,0.76,0.52),"Metal":Color(0.72,0.87,1.0),"Water":Color(0.40,0.85,1.0)}.get(str(theme.get("element","")),Color.WHITE)
