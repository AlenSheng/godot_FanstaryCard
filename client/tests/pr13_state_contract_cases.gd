extends SceneTree

const Store = preload("res://state/game_store.gd")
const Proto = preload("res://network/protobuf.gd")
const LoadClient = preload("res://tests/gameplay_load_client.gd")
var cases: Array = []

class FixtureGateway extends "res://network/gateway.gd":
    var requests: Array = []
    var sent: Array = []
    var response: Dictionary = {"ok":false,"status":409}
    func request(path: String, method: int = HTTPClient.METHOD_GET, _data: Variant = null, _quiet: Array = []) -> Dictionary:
        requests.append({"path":path,"method":method})
        return response.duplicate(true)
    func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
        sent.append({"kind":kind,"payload":payload.duplicate(true),"request_id":request_id})
        return true

func fresh() -> Array:
    var store: Node = Store.new()
    var gateway: Node = FixtureGateway.new()
    gateway.persist_session = false
    gateway.online = true
    gateway.session_generation = 1
    gateway.room_id = "room-current"
    gateway.current_match_id = "match-current"
    gateway.authenticated_user_id = "self"
    store.gateway = gateway
    gateway.event_received.connect(store._on_event)
    store.room = {"room_id":"room-current","match_id":"match-current","room_revision":10,"config_version":store.CATALOG.data.version,
        "allowed_actions":["battle.play_cards","battle.select_target"],
        "player":{"player_id":"self","hero_class":"Mage","phase":"Pve","combat":{"hp":70,"maximum_hp":70,"shield":0},
            "hand":[{"instance_id":"c1","card_id":"C01","level":0},{"instance_id":"c2","card_id":"C02","level":0},{"instance_id":"c3","card_id":"C11","level":0}]},
        "pve":{"battle_id":"battle-current","current_target_id":"monster","monsters":[{"monster_id":"monster","hp":100,"shield":0}]}}
    var probe: Node = LoadClient.new()
    probe.Game = store
    probe.client_id = "component"
    probe.run_id = "state-contract"
    probe.process_epoch = "owned-component"
    probe.own_user_id = "self"
    probe.active_match_id = "match-current"
    probe.verified_ready_match_id = "match-current"
    return [store,gateway,probe]

func close(pair: Array) -> void:
    for node in pair: node.free()

func record(id: String, passed: bool, actual: Variant) -> void:
    cases.append({"case_id":id,"executed":true,"status":"Passed" if passed else "Failed","actual":actual,"profiles_executed":["OFFLINE"],
        "scope":"Actual native production store/load/codec entries; declared controlled room and gateway responses; no database, live, renderer or human claim"})

func checked(id: String, suite: Dictionary, names: Array) -> void:
    var results: Dictionary = {}
    for name in names: results[name] = suite.get("checks",{}).get(name,false)
    record(id,not results.values().has(false),results)

func _initialize() -> void: call_deferred("run_cases")

func run_cases() -> void:
    var ack: Dictionary = load("res://tests/test_settlement_return.gd").new().run_test()
    checked("LOAD-05.1-T01",ack,["hall shown before failed response","result reflects server acknowledgement false","failed response handled","lost ack response resolved by authoritative state false"])
    checked("LOAD-05.2-T02",ack,["failed response handled","ready prompt follows acknowledgement false","preparation follows acknowledgement false","failed acknowledgement can be retried"])
    checked("PR13-A03.3-T02",ack,["lost ack response resolved by authoritative state false","ack verification does not repeat the mutation false","failed acknowledgement can be retried"])
    var polling: Dictionary = load("res://tests/test_settlement_polling.gd").new().run_test()
    checked("LOAD-05.1-T03",polling,["another match is ignored","lost room rejects unrelated receipt"])
    checked("PR13-A03.4-T02",polling,["pending assets are not treated as received","lost room keeps polling original match","lost room recovers ready receipt"])
    checked("LOAD-08.4-T03",polling,["pending assets are not treated as received","boss receipt replaces pending screen","ready receipt stops polling"])

    var pair := fresh()
    var store: Node = pair[0]
    var gateway: Node = pair[1]
    var probe: Node = pair[2]
    store.settlement = {"settlementId":"receipt","matchId":"match-current"}
    store.busy = true
    var busy_ack: bool = store.acknowledge_settlement()
    record("LOAD-05.1-T02",not busy_ack and gateway.requests.is_empty() and not store.settlement.is_empty(),{"confirmed":busy_ack,"requests":gateway.requests.size(),"receipt_retained":not store.settlement.is_empty()})
    record("PR13-A03.3-T03",not busy_ack and gateway.requests.is_empty() and polling.checks["another match is ignored"],{"busy_ack":busy_ack,"requests":gateway.requests.size(),"old_receipt_rejected":polling.checks["another match is ignored"]})
    store.busy = false
    store.settlement = {}
    gateway.response = {"ok":true,"data":{"settlementId":"receipt","matchId":"match-current"}}
    store._load_settlement("receipt")
    record("LOAD-08.4-T01",store.settlement.get("settlementId","")=="receipt" and gateway.requests==[{"path":"/api/v1/settlements/receipt","method":HTTPClient.METHOD_GET}],gateway.requests)
    record("PR13-B11.3-T01",store.settlement.get("settlementId","")=="receipt" and gateway.requests.size()==1 and not str(gateway.requests[0].path).contains("bootstrap"),gateway.requests)
    close(pair)

    pair = fresh(); store = pair[0]; gateway = pair[1]; probe = pair[2]
    probe.stage = "matchmaking"
    store.room = {}
    store.ready_prompt = {"match_id":"match-current"}
    probe._on_event("match.found",{"match_id":"match-current"})
    record("LOAD-04.1-T01",store.room.is_empty() and not probe.ready_accepted and probe.active_match_id=="match-current",{"room_empty":store.room.is_empty(),"accepted":probe.ready_accepted,"active_match":probe.active_match_id})
    probe._on_event("room.ready_accepted",{"match_id":"match-current"})
    probe._on_event("room.ready_required",{"match_id":"match-current","deadline_unix_ms":1})
    record("LOAD-04.2-T02",probe.ready_accepted and not probe.ready_required and gateway.sent.is_empty(),{"accepted":probe.ready_accepted,"required":probe.ready_required,"sends":gateway.sent.size()})
    record("PR13-A04.2-T02",probe.ready_accepted and gateway.sent.is_empty(),{"accepted":probe.ready_accepted,"sends":gateway.sent.size()})
    var codec := Proto.new()
    var ready_body: PackedByteArray = codec.encode("RoomReadyCommand",{})
    record("LOAD-04.1-T03",ready_body.is_empty() and codec.error.is_empty(),{"payload_bytes":ready_body.size(),"codec_error":codec.error})
    close(pair)

    pair = fresh(); store = pair[0]; gateway = pair[1]; probe = pair[2]
    var old_started := {"match_id":"old-match","room_id":"old-room","snapshot":store.room.duplicate(true)}
    old_started.snapshot.match_id = "old-match"
    old_started.snapshot.room_id = "old-room"
    gateway._receive(codec.encode("ServerEnvelope",{"protocol_version":1,"type":"room.started","sequence":1,"payload":codec.encode("RoomStartedEvent",old_started)}))
    var old_rejected: bool = store.room.get("match_id","")=="match-current" and gateway.current_match_id=="match-current" and gateway.room_id=="room-current"
    record("LOAD-04.1-T02",old_rejected,{"store_match":store.room.get("match_id"),"gateway_match":gateway.current_match_id,"gateway_room":gateway.room_id})
    record("PR13-A04.2-T03",old_rejected,{"old_started_ignored":old_rejected,"sequence":gateway.last_sequence})
    record("LOAD-05.2-T01",old_rejected,{"old_started_ignored":old_rejected})
    gateway.recovering = true
    gateway._pending_request_started["old-snapshot"] = {"context":{"match_id":"old-match","room_id":"old-room","session_generation":1}}
    var old_snapshot: Dictionary = old_started.snapshot
    gateway._receive(codec.encode("ServerEnvelope",{"protocol_version":1,"type":"room.snapshot","sequence":2,"request_id":"old-snapshot","payload":codec.encode("RoomSnapshotEvent",old_snapshot)}))
    var old_snapshot_ignored: bool = store.room.get("match_id","")=="match-current" and gateway.current_match_id=="match-current" and gateway.recovering
    gateway._receive(codec.encode("ServerEnvelope",{"protocol_version":1,"type":"room.snapshot","sequence":3,"payload":codec.encode("RoomSnapshotEvent",store.room)}))
    record("LOAD-04.3-T03",old_snapshot_ignored and not gateway.recovering,{"old_correlated_read_ignored":old_snapshot_ignored,"current_snapshot_restored":not gateway.recovering,"last_sequence":gateway.last_sequence})
    close(pair)

    pair = fresh(); store = pair[0]; gateway = pair[1]; probe = pair[2]
    var sequence_rows: Array = []
    for cycle in range(1,4):
        gateway.room_id = "" # Legal acknowledged prior cycle, same authenticated session.
        var snapshot: Dictionary = store.room.duplicate(true)
        snapshot.match_id = "cycle-"+str(cycle)
        snapshot.room_id = "room-"+str(cycle)
        gateway._receive(codec.encode("ServerEnvelope",{"protocol_version":1,"type":"room.started","sequence":cycle,"payload":codec.encode("RoomStartedEvent",{"match_id":snapshot.match_id,"room_id":snapshot.room_id,"snapshot":snapshot})}))
        sequence_rows.append(gateway.last_sequence)
    record("LOAD-05.2-T03",sequence_rows==[1,2,3] and gateway.session_generation==1,{"sequences":sequence_rows,"session_generation":gateway.session_generation})
    var command_order: Array = ["c3","c1","c2"]
    var decoded: Dictionary = codec.decode("BattlePlayCardsCommand",codec.encode("BattlePlayCardsCommand",{"card_instance_ids":command_order}))
    record("PR13-B02.3-T02",decoded.get("card_instance_ids",[])==command_order,{"requested":command_order,"decoded":decoded.get("card_instance_ids")})
    close(pair)

    pair = fresh(); store = pair[0]; gateway = pair[1]; probe = pair[2]
    probe.last_progress_ms = 123
    probe.last_effective_ms = 123
    probe._on_event("pong",{})
    probe._on_event("room.snapshot",store.room.duplicate(true))
    var no_progress: bool = probe.last_progress_ms==123 and probe.last_effective_ms==123
    record("LOAD-06.2-T01",no_progress,{"progress_clock":probe.last_progress_ms,"effective_clock":probe.last_effective_ms})
    record("PR13-B01.2-T01",no_progress,{"progress_clock":probe.last_progress_ms,"effective_clock":probe.last_effective_ms})
    probe._observe_battle()
    store.room.player.hand.append({"instance_id":"new-draw","card_id":"C04"})
    probe._observe_battle()
    record("LOAD-06.2-T02",probe.battle_metrics.observed_cards_drawn==1 and probe.last_effective_ms!=123,{"cards_drawn":probe.battle_metrics.observed_cards_drawn,"reason":probe.telemetry.back().waiting})
    probe._on_event("error.command_rejected",{"code":"REVISION_CONFLICT"})
    record("LOAD-06.2-T03",probe.errors.size()==1 and probe.battle_metrics.actions==0,{"errors":probe.errors.size(),"successful_actions":probe.battle_metrics.actions})
    probe._on_telemetry({"type":"realtime","_origin_context":{"cycle_id":"previous-cycle","phase":"playing","match_id":"previous-match"}})
    var late: Dictionary = probe.telemetry.back()
    record("PR13-B01.1-T01",late.cycle_id=="previous-cycle" and late.match_id=="previous-match",{"cycle":late.cycle_id,"match":late.match_id,"phase":late.phase})
    close(pair)

    pair = fresh(); store = pair[0]; gateway = pair[1]; probe = pair[2]
    var reasons: Array = []
    store.room.player.hand = []
    reasons.append(store.combat_wait_state().reason)
    store.room.player.stun_remaining_ms = 1500
    reasons.append(store.combat_wait_state().reason)
    record("PR13-B04.3-T02",store.combat_wait_state().remaining_ms==1500,store.combat_wait_state())
    store.room.player.stun_remaining_ms = 0
    store._pending_commands = {"pending":{"action":"battle.play_cards"}}
    reasons.append(store.combat_wait_state().reason)
    record("PR13-B01.2-T03",reasons==["drawing","stunned","confirming"],reasons)
    store._pending_commands = {}
    store.room.player.hand = []
    for number in range(5): store.room.player.hand.append({"instance_id":str(number),"card_id":"C01"})
    record("PR13-B04.3-T01",store.combat_wait_state().reason=="full_hand" and store.combat_wait_state().legal_opportunity,store.combat_wait_state())
    store.room.player.hand = []
    store.room.player.draw_charge = 0
    probe._observe_battle()
    var observation: Dictionary = probe.telemetry.back()
    record("PR13-B04.3-T03",observation.waiting.reason=="drawing" and not observation.has("estimated_wait_seconds"),{"waiting":observation.waiting,"estimated_seconds":observation.get("estimated_wait_seconds"),"observed_elapsed_ms":observation.elapsed_ms})
    close(pair)

    for policy in ["baseline_all_hand","basic","build"]:
        pair = fresh(); store = pair[0]; gateway = pair[1]; probe = pair[2]
        probe.strategy = policy
        var hand: Array = store.room.player.hand.duplicate(true)
        var before: Array = probe._select_cards(hand)
        var again: Array = probe._select_cards(hand)
        store.room.player["hidden_future_library"] = ["C05","C20"]
        store.room["hidden_future_loot"] = "first"
        var hidden_before: Array = probe._select_cards(hand)
        store.room.player.hidden_future_library.reverse()
        store.room.hidden_future_loot = "changed"
        var hidden_after: Array = probe._select_cards(hand)
        cases.append({"policy_result":policy,"repeat":before==again,"hidden_independent":hidden_before==hidden_after})
        close(pair)
    var policies: Array = cases.filter(func(row): return row.has("policy_result"))
    cases = cases.filter(func(row): return not row.has("policy_result"))
    record("PR13-B03.1-T01",policies.all(func(row): return row.repeat),policies)
    record("PR13-B03.1-T02",policies.all(func(row): return row.hidden_independent),policies)
    var proto_suite: Dictionary = preload("res://tests/test_protobuf.gd").new().run_test()
    record("LOAD-10.1-T01",proto_suite.ok,proto_suite)
    var loadout: Array = []
    for slot in ["Head","Chest","Hands","Legs","Feet"]:
        loadout.append({"instanceId":slot,"slot":slot,"quality":"Purple","element":"Fire","level":5,"effectAffix":"Bulwark","secondaryTrait":"DrawInterval"})
    var gains: Dictionary = load("res://ui/numerical_details.gd").inspect(loadout,"Guardian")
    var overflow_loadout: Array = loadout.duplicate(true)
    overflow_loadout[0].quality="Orange"
    var overflow_gains: Dictionary = load("res://ui/numerical_details.gd").inspect(overflow_loadout,"Guardian")
    record("PR13-B08.4-T01",is_equal_approx(float(gains.resistance_Fire.effective),.6) and float(gains.resistance_Fire.excess)>0 and is_equal_approx(float(overflow_gains.resistance_Fire.effective)-float(gains.resistance_Fire.effective),0),{"current":gains.resistance_Fire,"added_raw_above_cap":overflow_gains.resistance_Fire,"effective_delta":float(overflow_gains.resistance_Fire.effective)-float(gains.resistance_Fire.effective)})
    record("PR13-B08.4-T02",is_equal_approx(float(gains.interval_seconds.effective),1.8) and float(gains.interval_seconds.raw)<1.8,{"equipment_stage":gains.interval_seconds,"combat_draw_block_speed_stage":"tested separately by authoritative PVE rules; not merged into equipment-only preview"})

    pair = fresh(); store = pair[0]; gateway = pair[1]; probe = pair[2]
    store.room.player.numerical_state = {"fenxian_policy":"CurrentRhythm","guardian_policy":"CurrentSteps","guardian_remainder_tenths":0}
    probe._update_context()
    var context: Dictionary = gateway.telemetry_context.duplicate(true)
    probe._on_telemetry({"type":"battle_observation","event_type":"unknown_seed"})
    record("PR13-B01.1-T02",context.battle_seed==null and context.battle_seed_unavailable_reason=="not_published_by_authoritative_protocol" and context.strategy_seed==20260930 and probe.telemetry.back().battle_seed==null,{"initiating_context":context,"event_battle_seed":probe.telemetry.back().battle_seed})
    record("PR13-B12.1-T03",context.effective_room_policy.fenxian_policy=="CurrentRhythm" and context.effective_room_policy.guardian_policy=="CurrentSteps",{"controlled_experiment_label":"candidate-on","actual_recorded_room_policy":context.effective_room_policy,"label_does_not_override_authority":true})
    probe._observe_battle()
    probe._on_event("battle.combo_resolved",{"battle_id":"battle-current","attacker_id":"self","heal":0,"shield_gain":0,"hp_damage":0,"shield_damage":0,"card_instance_ids":["healing-card"]})
    record("PR13-B01.2-T02",probe.battle_metrics.heal==0 and probe.battle_metrics.cards_spent==1 and probe.battle_metrics.effective_actions==0 and probe.battle_metrics.zero_effective_actions==1 and probe.battle_metrics.heal_overflow==null,{"full_hp":store.room.player.combat,"metrics":probe.battle_metrics.duplicate(true),"requested_heal_unpublished":true})
    close(pair)

    pair = fresh(); store = pair[0]; probe = pair[2]
    store.room.player.hand = [{"instance_id":"single","card_id":"C01","level":0}]
    probe.strategy="baseline_all_hand"
    var baseline_wait: Dictionary=probe._strategy_wait_state()
    var baseline_cards: Array=probe._select_cards(store.room.player.hand)
    probe.strategy="build"
    var build_wait: Dictionary=probe._strategy_wait_state()
    store.room.player.hand=[]
    var empty_wait: Dictionary=probe._strategy_wait_state()
    record("PR13-B04.1-T02",baseline_cards==["single"] and baseline_wait.reason=="available" and build_wait.reason=="strategy_wait" and empty_wait.reason=="drawing",
        {"all_hand":baseline_wait,"build_intentional_hold":build_wait,"actual_empty_hand":empty_wait})
    close(pair)

    pair=fresh();store=pair[0];gateway=pair[1]
    var confirmed_acks:=0
    var old_events_safe:=true
    var repeated_not_in_room:=0
    for cycle in range(1,4):
        var match_id: String="controlled-cycle-%d" % cycle
        var room_id: String="controlled-room-%d" % cycle
        store.room={"match_id":match_id,"room_id":room_id,"config_version":store.CATALOG.data.version,
            "player":{"player_id":"self","hero_class":"Mage","phase":"Dead","hand":[],"combat":{"hp":0,"maximum_hp":70,"shield":0}}}
        store._adopt_room_context(store.room)
        gateway.current_match_id=match_id;gateway.room_id=room_id
        var receipt={"settlementId":"controlled-receipt-%d" % cycle,"matchId":match_id,"playerId":"self"}
        gateway.response={"ok":true,"status":200,"data":{"configVersion":store.CATALOG.data.version,
            "player":{"userId":"self","selectedClass":"Mage"},"wallet":{},"materials":{},"mail":{},"shop":{},"market":[],"inventory":{},
            "activePreparation":null,"unfinishedMatch":null,"unfinishedSettlement":receipt}}
        if cycle==2:
            var current_room: Dictionary=store.room.duplicate(true)
            await store._on_event("room.started",{"match_id":"controlled-cycle-1","room_id":"controlled-room-1","snapshot":current_room})
            old_events_safe=old_events_safe and store.room==current_room
            var origin={"match_id":match_id,"room_id":room_id,"session_generation":gateway.session_generation,"room_context_epoch":store._room_context_epoch}
            for duplicate in range(2):
                await store._on_event("error.command_rejected",{"code":"NOT_IN_ROOM","_origin_context":origin})
                repeated_not_in_room+=1
        store.settlement=receipt
        gateway.response={"ok":true,"status":200,"data":{}}
        if await store.acknowledge_settlement(): confirmed_acks+=1
        old_events_safe=old_events_safe and store.settlement.is_empty() and not await store.acknowledge_settlement()
    record("PR13-A03.4-T03",confirmed_acks==3 and repeated_not_in_room==2,{"actual_store_successful_acks":confirmed_acks,"second_cycle_repeated_rejections":repeated_not_in_room,"duplicate_ack_suppressed":true,"natural_cycle_completions_claimed":0,"setup":"Controlled authoritative HTTP responses, actual production store entries"})
    record("PR13-A09.2-T01",old_events_safe and confirmed_acks==3,{"second_cycle_old_started_ignored":old_events_safe,"three_distinct_match_contexts":3,"successful_acks":confirmed_acks,"full_natural_exploration_claimed":false})
    close(pair)

    var file := FileAccess.open(OS.get_environment("PR13_STATE_REPORT"),FileAccess.WRITE)
    if file == null: quit(1); return
    file.store_string(JSON.stringify({"cases":cases})); file.close()
    print(JSON.stringify({"executed":cases.size(),"failed":cases.filter(func(row): return row.status!="Passed").map(func(row): return row.case_id)}))
    quit(0 if cases.all(func(row): return row.status=="Passed") else 1)
