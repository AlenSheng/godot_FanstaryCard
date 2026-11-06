extends RefCounted

const Model=preload("res://ui/season_theme_model.gd")
const Dialog=preload("res://ui/season_theme_dialog.gd")
const Backdrop=preload("res://ui/layered_backdrop.gd")
const CATALOG=preload("res://data/catalog.json")

func run_test() -> Dictionary:
	var checks := {}
	var current := Model.selected()
	checks["actual published current theme is Fire"]=current.get("theme_id")=="Fire" and CATALOG.data.version=="season-v1-config-12"
	checks["pre-theme archive never falls back to current"]=Model.selected({"version":"old","tables":{}}).is_empty()
	checks["legacy room does not acquire current season theme"]=Model.room_theme({"config_version":"season-v1-config-12"}).is_empty()
	var room := {"room_id":"one","config_version":"season-v1-config-12","season":{"ruleset_id":"season-v1"}}
	checks["current season room uses pinned theme"]=Model.room_theme(room).get("theme_id")=="Fire"
	checks["unknown archive remains explicit"]=Model.room_theme(room,{"version":"unknown","tables":{}}).is_empty()
	var wood := CATALOG.data.duplicate(true);wood.tables.SeasonThemeRules[0].selected_theme="Wood"
	var source := {"version":"old-wood","tables":wood.tables}
	checks["retained alternate source is not current Fire"]=Model.room_theme(room,source).get("theme_id")=="Wood"
	checks["all five named strategies retained"]=CATALOG.data.tables.SeasonThemes.size()==5 and CATALOG.data.tables.SeasonThemes.all(func(row):return not str(row.strategy_id).is_empty())
	checks["fire boss keeps original palette"]=Model.boss_tint(current)==Color.WHITE
	checks["wood boss has a readable themed tint"]=Model.boss_tint(Model.selected(source)).g>Model.boss_tint(Model.selected(source)).r
	var saved_room: Dictionary=Game.room;Game.room=room
	var tree := Engine.get_main_loop() as SceneTree
	var host := Control.new();host.size=Vector2(1920,1080);tree.root.add_child(host)
	var listeners: int=Game.changed.get_connections().size()
	Dialog.show_dialog(host,current)
	checks["native in-canvas info panel created once"]=host.get_node_or_null("SeasonThemeInfo/ThemeInfoPanel/ThemeStrategy")!=null
	Dialog.show_dialog(host,current)
	checks["duplicate opening does not add a second panel"]=host.get_children().filter(func(node):return node.name=="SeasonThemeInfo").size()==1
	checks["info registers exactly one context observer"]=Game.changed.get_connections().size()==listeners+1
	Game.room=room.merged({"room_id":"other"},true);Game.changed.emit();await tree.process_frame;await tree.process_frame
	checks["original info closes when room context changes"]=host.get_node_or_null("SeasonThemeInfo")==null
	checks["closing unregisters context observer"]=Game.changed.get_connections().size()==listeners
	var backdrop := Backdrop.new();host.add_child(backdrop);backdrop.set_mode("exploration");backdrop.set_season_theme("Wood")
	var wood_tint: Color=backdrop.get_node("FarLayer").modulate
	backdrop.set_season_theme("Fire");checks["theme palette changes only scenery layer"]=wood_tint!=backdrop.get_node("FarLayer").modulate
	backdrop.set_mode("hall");backdrop.set_season_theme("");checks["camp scenery returns to its original palette"]=backdrop.get_node("FarLayer").modulate==Color.WHITE
	host.free();Game.room=saved_room
	return {"ok":not checks.values().has(false),"checks":checks}
