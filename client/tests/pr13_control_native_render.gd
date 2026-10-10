extends "res://tests/pr13_guardian_impact_render.gd"

@export var canonical_case := "PR13-B08.1-T01"
const NATIVE_VECTORS := "res://tests/data/control_contract_native.json"
const STATUS_GOLDEN := {
	"zh-CN":{"battle_status_stun":"眩晕 %s秒","battle_status_draw_block":"禁抽 %s秒","battle_status_draw_speed":"抽速 %s秒","battle_status_double_charge":"充能×2 %s秒"},
	"en":{"battle_status_stun":"Stun %ss","battle_status_draw_block":"Draw blocked %ss","battle_status_draw_speed":"Draw speed %ss","battle_status_double_charge":"Charge ×2 %ss"}
}
var rendered_states := 0
var vector_digest := ""

func milliseconds(value: String) -> int:
	var parts := value.split(":")
	assert(parts.size() == 3)
	var seconds := parts[2].split(".")
	var fraction: int = int(seconds[1].rpad(7,"0")) if seconds.size() == 2 else 0
	return int(parts[0])*3600000 + int(parts[1])*60000 + int(seconds[0])*1000 + int(float(fraction)/10000.0)

func native_room(vector: Dictionary, identity: String) -> Dictionary:
	var original: String = vector.states[identity]
	assert(original.sha256_text() == identity)
	return JSON.parse_string(original)

func project_room(room: Dictionary, vector: Dictionary, target_id: String) -> void:
	var player: Dictionary = room.Players[0]
	var combat: Dictionary = player.Combat
	reset_cards([],vector.hero,int(combat.Hp),int(combat.Shield))
	Game.hero_class = vector.hero
	Game.room.room_id = room.RoomId
	Game.room.room_revision = int(room.Revision)
	Game.room.player.player_id = player.PlayerId
	Game.room.player.weapon_level = int(combat.WeaponLevel)
	Game.room.player.draw_charge = float(combat.Deck.DrawCharge)
	Game.room.player.combat.maximum_hp = int(combat.MaximumHp)
	Game.room.player.stun_remaining_ms = milliseconds(combat.StunRemaining)
	Game.room.player.draw_block_remaining_ms = milliseconds(combat.DrawBlockRemaining)
	Game.room.player.draw_speed_remaining_ms = milliseconds(combat.DrawSpeedRemaining)
	Game.room.player.draw_block_speed_remaining_ms = milliseconds(combat.DrawBlockSpeedRemaining)
	for card in combat.Deck.Hand:
		Game.room.player.hand.append({"instance_id":card.InstanceId,"card_id":card.CardId,"level":int(card.Level)})
	if not room.Duels.is_empty():
		var opponent: Dictionary = room.Players[1]
		Game.room.player.phase = "Pvp"
		Game.room.erase("pve")
		Game.room.duel = {"duel_id":room.Duels[0].DuelId,"opponent_id":opponent.PlayerId,"opponent_class":"Mage","opponent_name":"Native opponent",
			"opponent":{"hp":int(opponent.Combat.Hp),"maximum_hp":int(opponent.Combat.MaximumHp),"shield":int(opponent.Combat.Shield)},
			"opponent_stun_remaining_ms":milliseconds(opponent.Combat.StunRemaining),"opponent_draw_block_remaining_ms":milliseconds(opponent.Combat.DrawBlockRemaining)}
	else:
		Game.room.erase("duel")
		Game.room.pve = {"battle_id":player.Pve.BattleId,"current_target_id":target_id,"monsters":[]}
		for monster in player.Pve.Monsters:
			Game.room.pve.monsters.append({"monster_id":monster.MonsterId,"hp":int(monster.Hp),"maximum_hp":int(monster.MaximumHp),"shield":int(monster.Shield),
				"stun_remaining_ms":milliseconds(monster.StunRemaining),"windup_remaining_ms":milliseconds(monster.WindupRemaining),"intent_kind":"Attack","intent_value":1,"intent_element":"None"})
	# Freeze the UI sampling clock at this authoritative boundary, while using
	# the same update function that normal continuous rendering calls.
	$UI._render()
	await get_tree().process_frame
	$UI._update_battle_status_labels(0)
	await RenderingServer.frame_post_draw

func inspect_label(name: String, remaining: int) -> Dictionary:
	var label: Label = $UI._reference.get_node_or_null(name)
	var expected: String = STATUS_GOLDEN[P.language()]["battle_status_stun"] % ("%.1f" % (float(remaining)/1000.0)) if remaining > 0 else ""
	var matches: bool = label != null and label.text == expected and label.is_visible_in_tree() == (remaining > 0)
	var readable := false
	if label != null:
		var font := label.get_theme_font("font")
		var font_size := label.get_theme_font_size("font_size")
		readable = remaining <= 0 or (font_size >= 18 and label.get_visible_line_count() == label.get_line_count() and font.get_string_size(label.text,HORIZONTAL_ALIGNMENT_LEFT,-1,font_size).x <= label.size.x and get_viewport().get_visible_rect().encloses(label.get_global_rect()))
	return {"name":name,"authoritative_remaining_ms":remaining,"actual_text":label.text if label!=null else "","matches":matches,"readable":readable,"passed":matches and readable}

func observe(vector: Dictionary, identity: String, target_id: String, tag: String) -> Dictionary:
	var room := native_room(vector,identity)
	await project_room(room,vector,target_id)
	var before: String = JSON.stringify(Game.room)
	var labels: Array = [inspect_label("PlayerStatus",milliseconds(room.Players[0].Combat.StunRemaining))]
	if room.Duels.is_empty():
		for index in range(room.Players[0].Pve.Monsters.size()): labels.append(inspect_label("MonsterStatus_%d" % index,milliseconds(room.Players[0].Pve.Monsters[index].StunRemaining)))
	else: labels.append(inspect_label("OpponentStatus",milliseconds(room.Players[1].Combat.StunRemaining)))
	var unchanged: bool = before == JSON.stringify(Game.room)
	rendered_states += 1
	return {"source_room_sha256":identity,"tag":tag,"target_id":target_id,"pvp_layout":not room.Duels.is_empty(),"labels":labels,"sample_elapsed_ms":0,"room_state_unchanged":unchanged,"passed":unchanged and labels.all(func(label):return label.passed)}

func development_status_checks() -> Array:
	var result: Array = []
	var before: String = JSON.stringify(Game.room)
	for elapsed in [0,2000,5000]:
		$UI._set_battle_status_label("PlayerStatus",1500,2500,3500,4500,elapsed)
		await get_tree().process_frame
		await RenderingServer.frame_post_draw
		var label: Label = $UI._reference.get_node("PlayerStatus")
		var expected: Array[String] = []
		for pair in [[1500,"battle_status_stun"],[2500,"battle_status_draw_block"],[3500,"battle_status_draw_speed"],[4500,"battle_status_double_charge"]]:
			if pair[0] > elapsed: expected.append(STATUS_GOLDEN[P.language()][pair[1]] % ("%.1f" % (float(pair[0]-elapsed)/1000.0)))
		var values_present: bool = expected.all(func(value):return label.text.contains(value)) and label.is_visible_in_tree() == (not expected.is_empty())
		var readable: bool = expected.is_empty() or (label.get_theme_font_size("font_size") >= 18 and label.get_visible_line_count() == label.get_line_count() and get_viewport().get_visible_rect().encloses(label.get_global_rect()))
		result.append({"fixture_only":true,"elapsed_ms":elapsed,"actual_text":label.text,"all_expected_values_present":values_present,"readable":readable,"room_state_unchanged":before==JSON.stringify(Game.room),"passed":values_present and readable and before==JSON.stringify(Game.room)})
	$UI._update_battle_status_labels(0)
	await RenderingServer.frame_post_draw
	return result

func run_vector(vector: Dictionary) -> Dictionary:
	var checks: Array = []
	for event in vector.events:
		if event.CaseId == canonical_case:
			checks.append(await observe(vector,event.RoomStateSha256,event.TargetId,event.Tag))
	if canonical_case == "PR13-B08.1-T03":
		var assertion: Dictionary = vector.assertions[2]
		assert(assertion.passed and assertion.frozen_player_sha256 == assertion.returned_player_sha256 and assertion.frozen_pve_sha256 == assertion.returned_pve_sha256)
		checks.append(await observe(vector,assertion.returned_room_state_sha256,"target-a","actual-pve-return"))
	return {"hero":vector.hero,"weapon_level":vector.weapon_level,"source_seed":vector.seed,"native_state_checks":checks,"passed":checks.all(func(row):return row.passed)}

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	var raw: String = FileAccess.get_file_as_string(NATIVE_VECTORS)
	vector_digest = raw.sha256_text()
	var data: Dictionary = JSON.parse_string(raw)
	assert(data.source_sha == "90713f2fc032178fdcb2cc26b479070bb822ccaa" and data.fixture_only and data.vectors.size() == 18)
	Game.set_process(false)
	$UI.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := CodecGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	var old_language: String = P.language()
	var old_hero: String = Game.hero_class
	var old_fps: int = Engine.max_fps
	get_window().mode = Window.MODE_WINDOWED
	for language in ["zh-CN","en"]:
		P.set_language(language)
		for resolution in [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]:
			get_window().size = resolution
			for fps in [30,60,144]:
				Engine.max_fps = fps
				var variants: Array = []
				for vector in data.vectors:
					assert(int(vector.seed) == 300001)
					variants.append(await run_vector(vector))
				var dev: Array = await development_status_checks() if canonical_case.ends_with("03") else []
				await capture_case(canonical_case,variants.all(func(v):return v.passed) and dev.all(func(d):return d.passed),{"all_eighteen_native_variants":variants,"native_source_sha":data.source_sha,"native_vectors_sha256":vector_digest,"development_combined_status_checks":dev},language,resolution,fps)
	P.set_language(old_language)
	Game.hero_class = old_hero
	Engine.max_fps = old_fps
	Game.gateway = old_gateway
	gateway.free()
	var passed: bool = case_verdicts.get(canonical_case,false)
	var cases := [{"case_id":canonical_case,"executed":true,"status":"Passed" if passed else "Failed","profiles_executed":["OFFLINE","RENDER"],"actual":{"matrix_rows":18,"native_variants_per_row":18,"rendered_state_checks":rendered_states},"scope":"Actual UI reads original authoritative room states at frozen sample time; native commands executed separately, no LIVE or hardware performance claim."}]
	var result := {"ok":passed and observations.size()==18 and DisplayServer.get_name()!="headless","cases":cases,"observations":observations,"rendered_state_checks":rendered_states,"native_source_sha":data.source_sha,"native_vectors_sha256":vector_digest,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name()}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	get_tree().quit(0 if result.ok else 1)
