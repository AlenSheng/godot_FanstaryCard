extends SceneTree

const Store = preload("res://state/game_store.gd")
class Observer extends "res://tests/gameplay_load_client.gd":
	func _ready() -> void: set_process(false)

var stores: Array = []
var cases: Array = []
var snapshots: Array = []
var combo_counts: Dictionary = {}
var late_result: Dictionary = {}
var held_telemetry: Dictionary = {}
var held_telemetry_sha := ""
var held_telemetry_at_ms := 0
var observer: Node
var output_path: String
var endpoint: String
var failed := false

func _initialize() -> void: call_deferred("run_cases")

func pause(seconds: float) -> void:
	await create_timer(seconds).timeout

func until(predicate: Callable, seconds: float = 20.0) -> bool:
	var deadline: int = Time.get_ticks_msec()+int(seconds*1000)
	while Time.get_ticks_msec()<deadline:
		if predicate.call(): return true
		await pause(0.02)
	return false

func require(value: bool, step: String) -> bool:
	if value: return true
	failed = true
	write_result({"ok":false,"setup_failed":step,"cases":cases,"private_values_not_reported":true})
	quit(1)
	return false

func record(cid: String, passed: bool, actual: Dictionary) -> void:
	cases.append({"case_id":cid,"executed":true,"status":"Passed" if passed else "Failed",
		"profiles_executed":["EXPERIMENT"],"actual":actual,
		"scope":"Real current GameStore/Gateway, complete Program and disposablePG; two actual four-human rooms and real resolved play. Controlled request/response faults only; no natural-cycle,performance or numerical-candidate benefit claim."})
	failed = failed or not passed

func write_result(value: Dictionary) -> void:
	var file := FileAccess.open(output_path,FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(value,"\t"))
		file.close()

func on_packet(kind: String, payload: Dictionary, index: int) -> void:
	if kind=="battle.combo_resolved":
		combo_counts[index]=int(combo_counts.get(index,0))+1

func on_observer_telemetry(sample: Dictionary) -> void:
	if sample.get("type")=="http" and str(sample.get("path","")).contains("controlled=late-event"):
		held_telemetry=sample.duplicate(true)
		held_telemetry_sha=JSON.stringify(held_telemetry).sha256_text()
		held_telemetry_at_ms=Time.get_ticks_msec()
		return
	observer._on_telemetry(sample)

func get_late(gateway: Node) -> void:
	late_result = await gateway.request("/api/v1/bootstrap?controlled=late-event",HTTPClient.METHOD_GET)

func begin_group() -> Dictionary:
	var preps: Array = []
	var tickets: Array = []
	for index in stores.size():
		var store: Node = stores[index]
		await store.prepare("Free",1 if index==0 else 0)
		if not require(not store.preparation.is_empty(),"real free preparation"): return {}
		preps.append(str(store.preparation.preparationId))
		await store.enqueue()
		if not require(not store.ticket.is_empty(),"real enqueue"): return {}
		tickets.append(str(store.ticket.ticketId))
	var attempts: Dictionary = {}
	var times: Dictionary = {}
	var deadline: int = Time.get_ticks_msec()+25_000
	while Time.get_ticks_msec()<deadline:
		var ready := true
		for index in stores.size():
			var store: Node = stores[index]
			if store.room.is_empty():
				ready=false
				if not store.ready_prompt.is_empty() and store.gateway._prelaunch_valid() and Time.get_ticks_msec()>=int(times.get(index,0)) and int(attempts.get(index,0))<3:
					if store.gateway.send("room.ready"):
						attempts[index]=int(attempts.get(index,0))+1
					times[index]=Time.get_ticks_msec()+1000
		if ready: break
		await pause(0.02)
	if not require(stores.all(func(store):return not store.room.is_empty()),"all actual room starts"): return {}
	var match_id: String = str(stores[0].room.get("match_id",""))
	if not require(not match_id.is_empty() and stores.all(func(store):return str(store.room.get("match_id",""))==match_id),"same four-human match"): return {}
	var primary: Node = stores[0]
	var ready_to_play: bool = await until(func():return primary.allowed("battle.play_cards") and not primary.room.get("player",{}).get("hand",[]).is_empty())
	if not require(ready_to_play,"authoritative playable hand"): return {}
	var before: int = int(combo_counts.get(0,0))
	var hand: Array = primary.room.player.hand
	primary.selected_cards.clear()
	primary.toggle_card(str(hand[0].instance_id))
	primary.play_cards()
	if not require(await until(func():return int(combo_counts.get(0,0))>before),"real production resolved combo"): return {}
	return {"match_id":match_id,"room_id":str(primary.room.room_id),"preparations":preps,"tickets":tickets,
		"actual_resolved_combo_count":int(combo_counts.get(0,0)),"observed_at_ms":Time.get_ticks_msec(),"actual_policy":primary.room.get("player",{}).get("numerical_state",{})}

func end_group() -> bool:
	for store in stores:
		if not store.room.is_empty() and store.settlement.is_empty() and store.allowed("battle.abandon"):
			store.command("battle.abandon")
	var terminal: bool = await until(func():return stores.all(func(store):return not store.settlement.is_empty() or store.room.is_empty()))
	if not require(terminal,"actual controlled abandon settlement"): return false
	for store in stores:
		if not store.settlement.is_empty():
			if not require(await store.acknowledge_settlement(),"actual settlement ACK"): return false
	return require(stores.all(func(store):return store.room.is_empty() and store.settlement.is_empty()),"actual all routes clear")

func run_cases() -> void:
	output_path=OS.get_environment("PR13_EXPERIMENT_REPORT")
	endpoint=OS.get_environment("FANTASYCARD_SERVER_URL")
	for index in 4:
		var store: Node = root.get_node("Game") if index==0 else Store.new()
		if index>0:
			store.name="OwnedPeer"+str(index)
			root.add_child(store)
		stores.append(store)
		store.gateway.event_received.connect(on_packet.bind(index))
		await store.login(endpoint,"test_mctx"+str(index))
		if not require(await until(func():return not store.lobby.is_empty() and store.gateway.online,30.0),"actual local login and WS"): return
		store.select_class("Priest")
		if not require(await until(func():return not store._class_switch_request_active),"real class switch"): return
		if not require(store.hero_class=="Priest" and str(store.lobby.player.get("selectedClass",""))=="Priest","actual selected Priest confirmed"): return
	var primary_store: Node = stores[0]
	var mail: Dictionary = await primary_store.gateway.request("/api/v1/mail")
	if not require(mail.get("ok",false) and mail.get("data") is Dictionary,"actual test mail read"): return
	var gold_mail: Array = mail.data.items.filter(func(item):return item.attachments.any(func(a):return a.kind=="Gold" and int(a.amount)==100000))
	if not require(gold_mail.size()==1,"actual generated test gold mail"): return
	var claim: Dictionary = await primary_store.gateway.request("/api/v1/mail/"+str(gold_mail[0].id)+"/claim",HTTPClient.METHOD_POST,{})
	if not require(claim.get("ok",false),"actual mail claim through production API"): return
	var purchase: Dictionary = await primary_store.gateway.request("/api/v1/shop/purchases",HTTPClient.METHOD_POST,{"productId":"health_potion","quantity":2})
	if not require(purchase.get("ok",false),"actual two potion purchase"): return
	var first: Dictionary = await begin_group()
	if first.is_empty(): return
	var primary: Node = stores[0]
	var first_replay: Dictionary = await primary.gateway.request("/api/v1/matches/enqueue?controlled=replay-old",HTTPClient.METHOD_POST,{"preparationId":first.preparations[0]},[409])
	var conflict: Dictionary = await primary.gateway.request("/api/v1/matches/enqueue?controlled=conflict-old",HTTPClient.METHOD_POST,{"preparationId":first.preparations[1]},[409])
	var conflict_data: Dictionary = conflict.get("data",{}) if conflict.get("data") is Dictionary else {}
	record("LOAD-09.1-T03",int(conflict.get("status",0))==409 and str(conflict_data.get("title","")).to_lower()=="idempotency conflict",
		{"status":conflict.get("status"),"title":conflict_data.get("title"),"changed_preparation_is_actual_peer_preparation":true,"ticket_counts_verified_separately_in_SQL":true})
	observer=Observer.new()
	observer.Game=primary
	observer.run_id=OS.get_environment("FANTASYCARD_LOAD_RUN_ID")
	observer.client_id="primary"
	observer.process_epoch=primary.gateway.new_id()
	observer.hero_profile="Priest"
	observer.stage="playing"
	observer.active_match_id=first.match_id
	observer.own_user_id=str(primary.lobby.player.userId)
	observer.strategy_seed=20260930
	observer.report_path=output_path.get_base_dir()+"/observer.original.json"
	observer.started_at_ms=Time.get_ticks_msec()
	root.add_child(observer)
	primary.network_telemetry.connect(on_observer_telemetry)
	observer._update_context()
	observer._observe_battle()
	observer._update_context()
	var context: Dictionary = primary.gateway.capture_context()
	record("PR13-B01.1-T02",context.get("battle_seed")==null and context.get("battle_seed_unavailable_reason")=="not_published_by_authoritative_protocol" and not primary.room.get("pve",{}).has("battle_seed"),
		{"battle_seed":context.get("battle_seed"),"missing_reason":context.get("battle_seed_unavailable_reason"),"strategy_seed":context.get("strategy_seed"),"actual_battle_id":observer.current_battle_id,"real_resolved_combo":first.actual_resolved_combo_count})
	get_late(primary.gateway)
	if not require(await until(func():return not late_result.is_empty() and not held_telemetry.is_empty(),15.0) and late_result.get("ok",false),"actual original first-room HTTP completed and producer event captured"): return
	observer._close_battle_metrics("ControlledAbandonRequested")
	if not await end_group(): return
	var second: Dictionary = await begin_group()
	if second.is_empty(): return
	observer.cycles_completed=1
	observer.active_match_id=second.match_id
	observer._update_context()
	observer._observe_battle()
	observer._update_context()
	var delivered_at_ms: int=Time.get_ticks_msec()
	var original_event_unchanged: bool=JSON.stringify(held_telemetry).sha256_text()==held_telemetry_sha
	if not require(original_event_unchanged,"original producer event unchanged during delay"): return
	observer._on_telemetry(held_telemetry)
	var event_file:=FileAccess.open(output_path.get_base_dir()+"/event-delivery.original.json",FileAccess.WRITE)
	event_file.store_string(JSON.stringify({"original_event":held_telemetry,"original_event_sha256":held_telemetry_sha,"captured_at_ms":held_telemetry_at_ms,"delivered_at_ms":delivered_at_ms,"actual_second_room_observed_at_ms":second.observed_at_ms,"actual_HTTP_status":late_result.get("status"),"HTTP_deadlines_changed":false},"\t"));event_file.close()
	var late: Array = observer.telemetry.filter(func(row):return row.get("type")=="http" and str(row.get("path","")).contains("controlled=late-event"))
	var old: Dictionary = late[0] if late.size()==1 else {}
	var all_original_fields_preserved: bool=late.size()==1
	for key in held_telemetry: all_original_fields_preserved=all_original_fields_preserved and old.get(key)==held_telemetry[key]
	record("PR13-B01.1-T01",all_original_fields_preserved and original_event_unchanged and delivered_at_ms>=int(second.observed_at_ms) and old.get("cycle_id")=="primary:1" and old.get("match_id")==first.match_id and str(primary.room.get("match_id",""))==second.match_id and first.match_id!=second.match_id,
		{"late_event_context":{"cycle_id":old.get("cycle_id"),"match_id":old.get("match_id"),"phase":old.get("phase")},"current_actual_match":second.match_id,"original_actual_match":first.match_id,"current_declared_cycle":primary.gateway.telemetry_context.get("cycle_id"),"physical_second_room_started_before_release":delivered_at_ms>=int(second.observed_at_ms),"all_original_producer_fields_preserved":all_original_fields_preserved,"producer_event_sha256":held_telemetry_sha,"actual_HTTP_was_successful_before_first_room_ended":late_result.get("ok",false)})
	var second_replay: Dictionary = await primary.gateway.request("/api/v1/matches/enqueue?controlled=replay-old",HTTPClient.METHOD_POST,{"preparationId":first.preparations[0]},[409])
	var first_value: Dictionary = first_replay.get("data",{}) if first_replay.get("data") is Dictionary else {}
	var second_value: Dictionary = second_replay.get("data",{}) if second_replay.get("data") is Dictionary else {}
	var preserved: bool = first_replay.get("ok",false) and second_replay.get("ok",false) and str(first_value.get("ticketId",""))==first.tickets[0] and str(second_value.get("ticketId",""))==first.tickets[0] and str(first_value.get("preparationId",""))==first.preparations[0] and str(second_value.get("preparationId",""))==first.preparations[0] and str(first_value.get("matchId",""))==first.match_id and str(second_value.get("matchId",""))==first.match_id
	record("LOAD-09.1-T01",preserved,{"old_preparation":first.preparations[0],"old_ticket":first.tickets[0],"old_match":first.match_id,"replay_before_next_room":first_value,"replay_after_next_room":second_value})
	record("LOAD-09.1-T02",first.preparations[0]!=second.preparations[0] and first.tickets[0]!=second.tickets[0] and first.match_id!=second.match_id and preserved,
		{"actual_first_room":first,"actual_second_room":second,"no_old_match_for_new_preparation":first.match_id!=second.match_id,"old_replay_remains_bound_to_old_preparation":preserved})
	observer._close_battle_metrics("ControlledAbandonRequested")
	if not await end_group(): return
	var identities: Array = stores.map(func(store):return str(store.lobby.player.userId))
	observer._flush_audit()
	for store in stores:
		store.gateway.end_session("",false)
		store.gateway.set_process(false)
	await process_frame
	write_result({"ok":not failed,"cases":cases,"owned_player_ids":identities,"primary_player_id":identities[0],"actual_rooms":[first,second],"intentional_abandon_not_natural_cycles":true,"normal_cycles_claimed":0,"secrets_not_in_evidence":true})
	print(JSON.stringify({"native_cases":cases.size(),"failed_cases":cases.filter(func(row):return row.status=="Failed").size(),"actual_rooms":2}))
	quit(0 if not failed else 1)
