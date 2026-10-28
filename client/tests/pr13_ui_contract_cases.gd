extends SceneTree

const Store = preload("res://state/game_store.gd")
const Proto = preload("res://network/protobuf.gd")
const P = preload("res://ui/palette.gd")
var cases: Array = []

class FixtureGateway extends "res://network/gateway.gd":
    var sent: Array = []
    func new_id() -> String: return "ui-case-" + str(sent.size())
    func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
        var codec := Proto.new()
        var body := codec.encode(COMMANDS.get(kind, ""), payload) if not COMMANDS.get(kind, "").is_empty() else PackedByteArray()
        sent.append({"kind":kind,"payload":payload.duplicate(true),"request_id":request_id,"wire_payload":body,"codec_error":codec.error})
        return true
    func request(_path: String, _method: int = HTTPClient.METHOD_GET, _data: Variant = null, _quiet: Array = []) -> Dictionary:
        return {"ok":false,"status":0,"data":null}

func fresh(cards: Array, hero: String = "Mage", hp: int = 70, shield: int = 0) -> Array:
    var store: Node = Store.new()
    var gateway: Node = FixtureGateway.new()
    gateway.persist_session = false
    gateway.online = true
    gateway.room_id = "fixture-room"
    gateway.room_revision = 10
    store.gateway = gateway
    gateway.event_received.connect(store._on_event)
    gateway.connection_changed.connect(store._on_connection_changed)
    var hand: Array = []
    for id in cards: hand.append({"instance_id":id,"card_id":id,"level":0})
    store.room = {"room_id":"fixture-room","room_revision":10,"allowed_actions":["battle.play_cards","battle.select_target"],
        "player":{"player_id":"self","hero_class":hero,"phase":"Pve","combat":{"hp":hp,"maximum_hp":100 if hero == "Guardian" else 70,"shield":shield},"hand":hand,"battle_status":{}},
        "pve":{"battle_id":"fixture-battle","current_target_id":"fixture-monster","monsters":[{"monster_id":"fixture-monster","hp":100,"shield":0}]}}
    return [store,gateway]

func close(pair: Array) -> void:
    pair[0].free()
    pair[1].free()

func record(id: String, passed: bool, actual: Variant) -> void:
    cases.append({"case_id":id,"executed":true,"status":"Passed" if passed else "Failed","actual":actual,"profiles_executed":["OFFLINE"],
        "scope":"Production store/codec entry with declared controlled room/gateway fixtures; no server, renderer, capacity or human claim"})

func _initialize() -> void: call_deferred("run_cases")

func run_cases() -> void:
    var orders: Array = []
    for order in [["C09","C06"],["C06","C09"]]:
        var pair := fresh(["C09","C06"])
        var store: Node = pair[0]
        for id in order: store.toggle_card(id)
        var core: String = store.combat_preview.get("core_element", "")
        store.play_cards()
        var plays: Array = pair[1].sent.filter(func(row): return row.kind == "battle.play_cards")
        var wire := Proto.new()
        var actual: Dictionary = wire.decode("BattlePlayCardsCommand",plays[0].wire_payload) if not plays.is_empty() else {}
        orders.append({"requested":order,"decoded":actual.get("card_instance_ids",[]),"core":core,"codec_error":wire.error})
        close(pair)
    record("PR13-B10.1-T01",orders[0].decoded==orders[0].requested and orders[1].decoded==orders[1].requested and orders[0].core=="Earth" and orders[1].core=="Water",orders)
    var pair := fresh(["C11"])
    var store: Node = pair[0]
    store.toggle_card("C11")
    var initial_request: Dictionary = store._preview_request.duplicate(true)
    var initial_preview: Dictionary = store.combat_preview.duplicate(true)
    var request_deadline := Time.get_ticks_msec() + 1000
    while Time.get_ticks_msec() < int(initial_request.get("due", 0)) and Time.get_ticks_msec() < request_deadline:
        await process_frame
    store._process(0)
    var previews: Array = pair[1].sent.filter(func(row): return row.kind=="combat.preview")
    var request_id: String = previews[0].request_id if not previews.is_empty() else "missing"
    store._on_event("combat.previewed",{"_request_id":request_id,"_room_revision":9,"battle_id":"fixture-battle","target_id":"fixture-monster","card_instance_ids":["C11"],"damage":99})
    record("PR13-B10.1-T02",not previews.is_empty() and not store.combat_preview.get("authoritative",false),{"actual_request_count":previews.size(),"initial_request":initial_request,"initial_preview":initial_preview,"remaining_request":store._preview_request,"request_revision":10,"reply_revision":9,"accepted_authority":store.combat_preview.get("authoritative",false)})
    pair[1]._schedule_reconnect()
    var snapshot_pair := fresh(["C06"])
    var snapshot: Dictionary = snapshot_pair[0].room.duplicate(true)
    close(snapshot_pair)
    # The reusable fixture snapshot is supplied through the real event entry.
    snapshot.room_id="new-fixture-room"
    store._on_event("room.snapshot",snapshot)
    record("PR13-B10.1-T03",store.selected_cards.all(func(id): return id == "C06"),{"selection_after_snapshot":store.selected_cards.duplicate(),"current_hand":["C06"],"preview_cleared":store.combat_preview.is_empty()})
    close(pair)
    pair=fresh(["C15"]);store=pair[0]
    var heal: Dictionary = store._calculate_combat_preview(["C15"])
    record("PR13-B10.2-T01",int(heal.get("heal",-1))==0 and int(heal.get("heal_overflow",0))>0,{"effective_heal":heal.get("heal"),"overflow":heal.get("heal_overflow"),"hp":70,"maximum_hp":70})
    close(pair)
    pair=fresh(["GUA-06"],"Guardian",100,49);store=pair[0]
    var shield: Dictionary = store._calculate_combat_preview(["GUA-06"])
    record("PR13-B10.2-T02",int(shield.get("shield_gain",-1))==1 and int(shield.get("shield_overflow",0))>0,{"effective_shield":shield.get("shield_gain"),"overflow":shield.get("shield_overflow"),"shield_before":49,"cap":50})
    close(pair)
    var original := P.language()
    var locale_results: Array = []
    for language in P.languages():
        P.set_language(language)
        var missing: Array = []
        for key in ["battle_preview_estimate","battle_preview_heal","battle_preview_shield","battle_preview_overflow","battle_preview_applied_estimate","battle_wait_confirming"]:
            if P.localized(key).is_empty() or P.localized(key)==key: missing.append(key)
        locale_results.append({"language":language,"selected_language":P.language(),"missing":missing})
    P.set_language(original)
    record("PR13-B10.2-T03",locale_results.all(func(row):return row.language==row.selected_language and row.missing.is_empty()),locale_results)
    pair=fresh(["C11"]);store=pair[0];store.toggle_card("C11")
    var before: Dictionary = store.room.duplicate(true)
    var sounds: Array = []
    store.sound_requested.connect(func(cue):sounds.append(cue))
    store.play_cards();store.play_cards()
    var plays: Array = pair[1].sent.filter(func(row):return row.kind=="battle.play_cards")
    record("PR13-B10.3-T01",plays.size()==1,{"legal_play_commands":plays.size(),"pending":store.has_pending_commands()})
    record("PR13-B10.3-T02",store.room==before and not sounds.has("card_play") and store.has_pending_commands(),{"room_unchanged":store.room==before,"success_sound_before_ack":sounds.has("card_play"),"pending":store.has_pending_commands()})
    pair[1]._schedule_reconnect()
    for i in range(20):store.play_cards()
    record("PR13-B10.3-T03",pair[1].sent.filter(func(row):return row.kind=="battle.play_cards").size()==1 and store._queued_command.size()<=1,{"play_commands":pair[1].sent.filter(func(row):return row.kind=="battle.play_cards").size(),"queued_contexts":0 if store._queued_command.is_empty() else 1})
    close(pair)
    var retry: Dictionary = load("res://tests/test_play_retry.gd").new().run_test()
    record("PR13-B10.4-T01",retry.get("checks",{}).get("dead",false),{"native_entry_fixture":"dead target during pending revision retry","result":retry,"interpretation":"stale play cannot silently resend at another target; authoritative GDD death fallback remains unchanged"})
    var feedback: Dictionary = load("res://tests/test_combat_feedback_scope.gd").new().run_test()
    record("PR13-B10.4-T03",feedback.get("ok",false),feedback)
    var file:=FileAccess.open(OS.get_environment("PR13_UI_CASE_REPORT"),FileAccess.WRITE)
    file.store_string(JSON.stringify({"cases":cases,"passed":cases.all(func(row):return row.status=="Passed")},"  "))
    file.close()
    print(JSON.stringify({"executed":cases.size(),"passed":cases.filter(func(row):return row.status=="Passed").size()}))
    quit(0 if cases.all(func(row):return row.status=="Passed") else 1)
