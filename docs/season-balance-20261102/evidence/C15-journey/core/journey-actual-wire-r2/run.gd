extends SceneTree
const Proto=preload("res://network/protobuf.gd")
const Model=preload("res://ui/season_journey_model.gd")
func _initialize() -> void:
	create_timer(30).timeout.connect(func():quit(1));call_deferred("run")
func run() -> void:
	var game=get_root().get_node("Game")
	game.set_process(false);game.gateway.set_process(false);game.gateway.persist_session=false;game.gateway.reconnect_enabled=false;game.gateway.socket.close()
	var sound=get_root().get_node("Sound");sound.persist_settings=false;sound.stop_all();sound.set_process(false)
	var folder := OS.get_environment("FANTASYCARD_ART_EVIDENCE")
	var checks := {}
	var proto := Proto.new(true)
	var journey: Dictionary=proto.decode_http("SeasonJourneyResponse",FileAccess.get_file_as_bytes(folder.path_join("journey.bin")))
	checks["real authenticated progress passes client model"]=proto.error.is_empty() and Model.valid(journey)
	checks["real original scope and frozen config"]=journey.seasonId=="journey-api" and journey.configVersion=="season-v1-config-11" and journey.state=="Active"
	checks["real two clears and single300contract"]=journey.experience==510 and journey.version==2
	checks["real level2 exact residual"]=journey.level==2 and journey.experienceIntoLevel==95 and journey.experienceToNext==230
	checks["real full track and main20"]=journey.levels.size()==30 and journey.mainRewardLevels==20 and journey.maximumExperience==12525
	checks["real milestone20 threshold"]=journey.levels[19].cumulativeExperience==6850 and journey.levels[19].stage=="Main"
	checks["real post20 collection metadata"]=journey.levels[20].stage=="Collection" and journey.levels[29].cumulativeExperience==12525
	var bosses: Array=journey.contracts.filter(func(row):return row.completionKind=="Boss")
	checks["real one boss does not fill all opened weeks"]=bosses.filter(func(row):return row.state=="Completed").size()==1 and bosses[0].week==1 and bosses[0].experienceCredited==300
	checks["real catchup maximum and reference"]=journey.maximumCatchUpMultiplier==2 and journey.referenceExperience==6850 and journey.catchUpActive
	var scoped: Dictionary=proto.decode_http("SeasonJourneyResponse",FileAccess.get_file_as_bytes(folder.path_join("scoped.bin")))
	checks["real explicit original ignores client experience parameter"]=proto.error.is_empty() and Model.valid(scoped) and scoped.seasonId==journey.seasonId and scoped.experience==510
	var missing: Dictionary=proto.decode_http("SeasonJourneyResponse",FileAccess.get_file_as_bytes(folder.path_join("missing.bin")))
	checks["real missing source never falls back to current"]=proto.error.is_empty() and Model.valid(missing) and missing.state=="None" and missing.seasonId==null and missing.experience==0
	var updated: Dictionary=proto.decode_http("SeasonJourneyResponse",FileAccess.get_file_as_bytes(folder.path_join("updated.bin")))
	checks["real fresh view after three extractions"]=proto.error.is_empty() and Model.valid(updated) and updated.experience==1020 and updated.version==5
	checks["real extraction contract adds only another300"]=updated.contracts.filter(func(row):return row.state=="Completed").size()==2 and updated.contracts.filter(func(row):return row.completionKind=="Extracted" and row.state=="Completed")[0].experienceCredited==300
	checks["real level4 exact residual"]=updated.level==4 and updated.experienceIntoLevel==130 and updated.experienceToNext==260
	var ok: bool=not checks.values().has(false)
	FileAccess.open(folder.path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"ok":ok,"checks":checks},"  "))
	print(JSON.stringify({"ok":ok,"checks":checks.size()}));quit(0 if ok else 1)
