extends "res://tests/pr13_control_native_render.gd"

@export var marginal_case := "PR13-B08.2-T01"
const ELEMENT_NATIVE_VECTORS := "res://tests/data/element_marginal_boundaries_native.json"
var marginal_states := 0

func visible_text(expected: String) -> bool:
	for node in $UI._reference.find_children("*", "Label", true, false):
		if node.text == expected and node.is_visible_in_tree() and node.get_visible_line_count() == node.get_line_count() and get_viewport().get_visible_rect().encloses(node.get_global_rect()): return true
	return false

func observe_marginal(vector: Dictionary, identity: String, tag: String) -> Dictionary:
	var room := native_room(vector, identity)
	var player: Dictionary = room.Players[0]
	var combat: Dictionary = player.Combat
	var target_id: String = player.Pve.Monsters[0].MonsterId
	await project_room(room, vector, target_id)
	Game.room.player.hero_class = vector.hero
	Game.room.player.library_count = combat.Deck.Library.size()
	Game.room.player.discard_count = combat.Deck.Discard.size()
	$UI._render()
	await get_tree().process_frame
	$UI._update_battle_status_labels(0)
	await RenderingServer.frame_post_draw
	var before: String = JSON.stringify(Game.room)
	var expected_hand: Array = combat.Deck.Hand.map(func(card):return card.CardId)
	var actual_hand: Array = []
	var cards_visible := true
	for node in $UI._reference.find_children("Card_*", "Button", true, false):
		actual_hand.append(node.name.trim_prefix("Card_"))
		cards_visible = cards_visible and node.is_visible_in_tree() and get_viewport().get_visible_rect().encloses(node.get_global_rect())
	var slots_match := actual_hand == expected_hand and actual_hand.size() <= 5
	for index in range(5):
		var empty: Control = $UI._reference.get_node_or_null("EmptyHandSlot_%d" % index)
		slots_match = slots_match and ((empty != null and empty.is_visible_in_tree()) if index >= actual_hand.size() else empty == null)
	var health_matches := visible_text("%s / %s" % [int(combat.Hp), int(combat.MaximumHp)])
	var shield_matches := visible_text(P.localized("exploration_shield_amount") % int(combat.Shield)) if int(combat.Shield) > 0 else true
	var pool_matches := visible_text(P.localized("exploration_library_discard") % [combat.Deck.Library.size(), combat.Deck.Discard.size()])
	var control := inspect_label("MonsterStatus_0", milliseconds(player.Pve.Monsters[0].StunRemaining))
	var unchanged: bool = before == JSON.stringify(Game.room)
	marginal_states += 1
	return {"source_room_sha256":identity,"tag":tag,"expected_hand":expected_hand,"actual_visible_hand":actual_hand,"hand_slots_match":slots_match,"cards_visible":cards_visible,"hp":combat.Hp,"maximum_hp":combat.MaximumHp,"shield":combat.Shield,"health_visible_and_exact":health_matches,"shield_visible_and_exact":shield_matches,"pool_counts_visible_and_exact":pool_matches,"control":control,"sample_elapsed_ms":0,"room_state_unchanged":unchanged,"passed":slots_match and cards_visible and health_matches and shield_matches and pool_matches and control.passed and unchanged}

func run_marginal_vector(vector: Dictionary) -> Dictionary:
	var states: Array = []
	var ledger: Array = []
	for arm in vector.arms:
		for event in arm.events:
			states.append(await observe_marginal(vector, event.before_state_sha256, arm.profile + "-before-%d" % event.cast))
			states.append(await observe_marginal(vector, event.after_state_sha256, arm.profile + "-after-%d" % event.cast))
			var accounted: bool = event.requested_draw == event.actual_draw + event.immediate_overflow and event.requested_heal == event.effective_heal + event.heal_overflow and event.requested_shield == event.effective_shield + event.shield_overflow
			ledger.append({"profile":arm.profile,"cast":event.cast,"requested_draw":event.requested_draw,"actual_draw":event.actual_draw,"immediate_overflow":event.immediate_overflow,"requested_heal":event.requested_heal,"effective_heal":event.effective_heal,"heal_overflow":event.heal_overflow,"requested_shield":event.requested_shield,"effective_shield":event.effective_shield,"shield_overflow":event.shield_overflow,"admitted_control_ticks":event.admitted_control_ticks,"added_control_union_ticks":event.added_control_union_ticks,"target_control_union_ticks":event.target_control_union_ticks,"accounted":accounted})
	return {"hero":vector.hero,"source_seed":vector.seed,"replacement":vector.replacement,"actual_native_events":ledger,"native_state_checks":states,"passed":states.all(func(row):return row.passed) and ledger.all(func(row):return row.accounted)}

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	var raw := FileAccess.get_file_as_string(ELEMENT_NATIVE_VECTORS)
	var data: Dictionary = JSON.parse_string(raw)
	assert(data.source_sha == "e371315d283f581819d7090b606dc529f61d26fa" and data.schema == "actual_element_marginal_boundaries_v1" and data.rows.size() == 9 and data.passed)
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
	var vectors: Array = data.rows.filter(func(row):return row.case_id == marginal_case)
	assert(vectors.size() == 3)
	# Retain all classes; use Mage last for the canonical water-cap screenshot.
	vectors.sort_custom(func(a,b):return (1 if a.hero == "Mage" else 0) < (1 if b.hero == "Mage" else 0))
	for language in ["zh-CN", "en"]:
		P.set_language(language)
		for resolution in [Vector2i(1920,1080), Vector2i(1280,720), Vector2i(960,540)]:
			get_window().size = resolution
			for fps in [30,60,144]:
				Engine.max_fps = fps
				var variants: Array = []
				for vector in vectors: variants.append(await run_marginal_vector(vector))
				await capture_case(marginal_case, variants.all(func(row):return row.passed), {"native_source_sha":data.source_sha,"native_vectors_sha256":raw.sha256_text(),"three_class_variants":variants,"fixture_scope":data.scope}, language, resolution, fps)
	P.set_language(old_language)
	Game.hero_class = old_hero
	Engine.max_fps = old_fps
	Game.gateway = old_gateway
	gateway.free()
	var passed: bool = case_verdicts.get(marginal_case, false)
	var cases := [{"case_id":marginal_case,"executed":true,"status":"Passed" if passed else "Failed","profiles_executed":["OFFLINE","RENDER"],"actual":{"matrix_rows":18,"native_variants_per_row":3,"rendered_state_checks":marginal_states},"scope":"Actual client UI displays original Room.PlayCards boundary snapshots; all budget-matched arms and classes retained at frozen sample time. No LIVE, hardware FPS or full experiment claim."}]
	var result := {"ok":passed and observations.size() == 18 and DisplayServer.get_name() != "headless","cases":cases,"observations":observations,"rendered_state_checks":marginal_states,"native_source_sha":data.source_sha,"native_vectors_sha256":raw.sha256_text(),"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name()}
	FileAccess.open(output + "/native-result.json", FileAccess.WRITE).store_string(JSON.stringify(result))
	get_tree().quit(0 if result.ok else 1)
