extends "res://tests/pr13_guardian_impact_render.gd"

@export var canonical_case := "PR13-B07.3-T01"
const VECTORS := "res://tests/data/guardian_sequences_native.json"
var native_source := ""
var vector_digest := ""
var rendered_states := 0

func native_state(vector: Dictionary, identity: String) -> Dictionary:
	var original: String = vector.States[identity]
	assert(original.sha256_text() == identity)
	var parsed: Dictionary = JSON.parse_string(original)
	return parsed

func scenario(vector: Dictionary, name: String) -> Dictionary:
	for row in vector.Observations:
		if row.scenario == name: return row.actual
	assert(false, "Missing native scenario: " + name)
	return {}

func close_details() -> void:
	var dialog := guardian_dialog()
	if dialog != null: dialog.queue_free()
	await get_tree().process_frame

func project_state(combat: Dictionary, pvp_room: Dictionary = {}) -> void:
	reset_cards([], "Guardian", int(combat.Hp), int(combat.Shield))
	Game.room.player.weapon_level = int(combat.WeaponLevel)
	Game.room.player.numerical_state = {"guardian_policy":"FractionalRemainder" if int(combat.GuardianPolicy)==2 else "CurrentSteps", "guardian_remainder_tenths":int(combat.GuardianShieldRemainderTenths)}
	for card in combat.Deck.Hand:
		Game.room.player.hand.append({"instance_id":card.InstanceId,"card_id":card.CardId,"level":int(card.Level)})
	if not pvp_room.is_empty():
		var opponent: Dictionary = {}
		for player in pvp_room.Players:
			if int(player.HeroClass)==2: opponent=player
		assert(not opponent.is_empty() and not pvp_room.Duels.is_empty())
		Game.room.player.phase = "Pvp"
		Game.room.duel = {"duel_id":pvp_room.Duels[0].DuelId,"opponent_id":opponent.PlayerId,"opponent_class":"Mage","opponent_name":"Native opponent","opponent":{"hp":int(opponent.Combat.Hp),"maximum_hp":int(opponent.Combat.MaximumHp),"shield":int(opponent.Combat.Shield)}}
	await present()

func displayed_state(combat: Dictionary, pvp: bool) -> Dictionary:
	var root: Control = $UI._reference
	var base_rect := Rect2(370,305,409,40) if pvp else Rect2(126,746,264,40)
	var transform := root.get_global_transform_with_canvas()
	var region := Rect2(transform * base_rect.position, base_rect.size * root.get_global_transform_with_canvas().get_scale())
	var labels: Array = []
	for label in root.find_children("*","Label",true,false):
		if label.is_visible_in_tree() and label.get_global_rect().intersects(region) and not label.text.is_empty(): labels.append(label.text)
	var shield: int = int(combat.Shield)
	var expected: String = P.localized("exploration_shield_amount") % shield
	var shield_matches: bool = labels.has(expected) if shield>0 else labels.is_empty()
	var button: Button = root.get_node_or_null("GuardianRemainder")
	var candidate: bool = int(combat.GuardianPolicy)==2
	var remainder_matches: bool = button!=null and button.is_visible_in_tree() and button.text=="%d / 10" % int(combat.GuardianShieldRemainderTenths) if candidate else button==null
	return {"shield":shield,"remainder":int(combat.GuardianShieldRemainderTenths),"policy":int(combat.GuardianPolicy),"actual_player_shield_labels":labels,"shield_matches_native":shield_matches,"remainder_matches_native":remainder_matches,"pvp_layout":pvp,"passed":shield_matches and remainder_matches}

func observe(vector: Dictionary, identity: String, tag: String, pvp_room: Dictionary = {}) -> Dictionary:
	var combat := native_state(vector, identity)
	await project_state(combat,pvp_room)
	var before: String = JSON.stringify(Game.room)
	var actual := displayed_state(combat,not pvp_room.is_empty())
	actual["source_state_sha256"] = identity
	actual["tag"] = tag
	actual["room_state_unchanged"] = before==JSON.stringify(Game.room)
	actual["passed"] = actual.passed and actual.room_state_unchanged
	rendered_states += 1
	return actual

func observe_room(vector: Dictionary, identity: String, tag: String) -> Dictionary:
	var room := native_state(vector,identity)
	var combat: Dictionary = room.Players[0].Combat
	await project_state(combat)
	var before: String = JSON.stringify(Game.room)
	var actual := displayed_state(combat,false)
	actual["source_state_sha256"] = identity
	actual["tag"] = tag
	actual["room_state_unchanged"] = before==JSON.stringify(Game.room)
	actual["passed"] = actual.passed and actual.room_state_unchanged
	rendered_states += 1
	return actual

func inspect_details(combat: Dictionary) -> Dictionary:
	var before: String = JSON.stringify(Game.room)
	var clicked: bool = await click_named("GuardianRemainder")
	await get_tree().process_frame
	var dialog := guardian_dialog()
	var content: String = dialog_text(dialog) if dialog!=null else ""
	var visible: bool = content.contains(Details.text("weapon") % int(combat.GuardianShieldRemainderTenths))
	var result := {"normal_gui_click":clicked,"authoritative_remainder_in_details":visible,"room_state_unchanged":before==JSON.stringify(Game.room),"passed":clicked and visible and before==JSON.stringify(Game.room)}
	await close_details()
	return result

func run_vector(vector: Dictionary) -> Dictionary:
	var checks: Array = []
	if canonical_case=="PR13-B07.3-T01":
		var a := scenario(vector,"preview-and-rejections")
		checks.append(await observe_room(vector,a.before,"before-preview"))
		for identity in a.preview_state_sha256:
			assert(identity==a.before)
			checks.append(await observe_room(vector,identity,"uncommitted-preview"))
		for rejected in a.rejects:
			assert(rejected.rejected and rejected.state_sha256==a.before)
			checks.append(await observe_room(vector,rejected.state_sha256,"rejected-"+str(rejected.fault)))
		checks.append(await observe_room(vector,a.after,"one-successful-commit"))
		assert(a.spent_instance_rejected)
		checks.append(await observe_room(vector,a.after,"spent-instance-rejected"))
	elif canonical_case=="PR13-B07.3-T02":
		checks.append(await observe(vector,vector.NamedStates["five-start"],"five-start"))
		var a := scenario(vector,"five-successful-plays")
		for step in a.steps: checks.append(await observe(vector,step.state,"successful-play-"+str(step.play)))
		for name in ["already-full","zero-empty","zero-full","exact-fill","overflow"]:
			var boundary := scenario(vector,name)
			checks.append(await observe(vector,boundary.before,name+"-before"))
			checks.append(await observe(vector,boundary.after,name+"-after"))
	elif canonical_case=="PR13-B07.3-T03":
		var a := scenario(vector,"json-pvp-restoration")
		assert(a.saved_room_json==a.restored_room_json and a.frozen==a.after and a.frozenPve==a.after_pve_battle)
		checks.append(await observe(vector,a.frozen,"frozen-pve"))
		checks.append(await observe(vector,a.during,"actual-pvp-work-copy",JSON.parse_string(a.pvp_room_json)))
		checks.append(await observe(vector,a.after,"json-restored-pve-return"))
		var movement := scenario(vector,"legal-map-leave")
		checks.append(await observe(vector,movement.beforeMove,"before-legal-leave"))
		checks.append(await observe(vector,movement.after,"after-legal-leave"))
	else: assert(false,"Unexpected original case")
	var details := {"passed":true,"legacy_candidate_entry_hidden":true}
	if vector.candidate:
		# The last already-rendered state supplies the exact backend remainder.
		var name: String = "room-after-commit" if canonical_case.ends_with("01") else "overflow-after" if canonical_case.ends_with("02") else "leave-after"
		var state := native_state(vector,vector.NamedStates[name])
		var combat: Dictionary = state.Players[0].Combat if state.has("Players") else state
		details = await inspect_details(combat)
	return {"weapon_level":vector.level,"candidate":vector.candidate,"source_seed":vector.seed,"native_state_checks":checks,"details":details,"passed":checks.all(func(row):return row.passed) and details.passed}

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	var original: String = FileAccess.get_file_as_string(VECTORS)
	vector_digest = original.sha256_text()
	var data: Dictionary = JSON.parse_string(original)
	native_source = data.source_sha
	assert(native_source=="edfb67651354fabe67072c213c742f2039eafb03" and data.fixture_only and data.vectors.size()==12)
	Game.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := CodecGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	var original_language: String = P.language()
	var original_hero: String = Game.hero_class
	var original_fps: int = Engine.max_fps
	Game.hero_class = "Guardian"
	get_window().mode = Window.MODE_WINDOWED
	get_viewport().gui_embed_subwindows = true
	for language in ["zh-CN","en"]:
		P.set_language(language)
		assert(P.language()==language)
		for resolution in [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]:
			get_window().size=resolution
			for fps in [30,60,144]:
				Engine.max_fps=fps
				var variants: Array = []
				for vector in data.vectors:
					assert(vector.Passed and int(vector.seed)==200001)
					variants.append(await run_vector(vector))
				await capture_case(canonical_case,variants.all(func(row):return row.passed),{"native_source_sha":native_source,"native_vectors_sha256":vector_digest,"all_twelve_native_variants":variants,"variant_count":variants.size()},language,resolution,fps)
	P.set_language(original_language)
	Game.hero_class=original_hero
	Engine.max_fps=original_fps
	Game.gateway=old_gateway
	gateway.free()
	var passed: bool = case_verdicts.get(canonical_case,false)
	var cases := [{"case_id":canonical_case,"executed":true,"status":"Passed" if passed else "Failed","profiles_executed":["OFFLINE","RENDER"],"actual":{"matrix_rows":18,"native_variants_per_row":12,"rendered_state_checks":rendered_states},"scope":"Actual UI reads immutable authoritative boundary states; backend commands were executed separately, no LIVE or hardware performance claim."}]
	var result := {"ok":passed and observations.size()==18 and DisplayServer.get_name()!="headless","cases":cases,"observations":observations,"rendered_state_checks":rendered_states,"native_source_sha":native_source,"native_vectors_sha256":vector_digest,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name()}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	get_tree().quit(0 if result.ok else 1)
