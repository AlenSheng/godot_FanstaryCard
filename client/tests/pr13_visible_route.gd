extends SceneTree
const Store = preload("res://state/game_store.gd")
const LoadClient = preload("res://tests/gameplay_load_client.gd")
func _initialize() -> void: call_deferred("run")
func run() -> void:
    var store: Node = Store.new()
    var gateway: Node = load("res://network/gateway.gd").new()
    gateway.persist_session = false
    gateway.online = true
    store.gateway = gateway
    store.room = {"room_id":"route-fixture","allowed_actions":["action.extract","room.move"],"player":{"phase":"ActionBar"},"self":{"row":5,"column":0}}
    var probe: Node = LoadClient.new()
    probe.Game = store
    probe.load_profile = "cleared-extraction"
    var before_clear: bool = probe._should_extract({})
    probe.cycle_battles_won = 1
    var after_clear: bool = probe._should_extract({})
    probe.load_profile = "cyclic-gameplay"
    var original_before_move: bool = probe._should_extract({})
    var original_after_move: bool = probe._should_extract({"5:1":true})
    probe.load_profile = "cleared-extraction"
    var moves: Array = [{"row":4,"column":1},{"row":5,"column":1}]
    probe.strategy_rng.seed = 42
    store.room["hidden_future_path"] = [{"row":4,"column":1}]
    var first: Dictionary = probe._choose_move(moves,{})
    store.room.hidden_future_path = [{"row":3,"column":5}]
    store.room["hidden_evacuation_positions"] = [{"row":0,"column":5}]
    probe.strategy_rng.seed = 42
    var second: Dictionary = probe._choose_move(moves,{})
    var empty: Dictionary = probe._choose_move([],{})
    var hidden_safe: bool = first==second and first=={"row":5,"column":1} and first in moves and empty.is_empty()
    var checks := {"new_profile_requires_actual_clear":not before_clear and after_clear,"original_extraction_policy_preserved":not original_before_move and original_after_move,"hidden_paths_ignored":hidden_safe,"no_legal_move_returns_empty":empty.is_empty()}
    var report := {"checks":checks,"cases":[{"case_id":"PR13-B03.2-T03","executed":true,"status":"Passed" if hidden_safe else "Failed","profiles_executed":["OFFLINE"],"actual":{"first":first,"second":second,"legal_moves":moves,"empty_result":empty},"scope":"Actual native robot policy with only public legal coordinates/visited state; altered hidden fixture fields are not read; no sampled experiment claim"}],"new_profile":"clear-then-extract-visible-outer-ring-v1","original_capacity_evidence":false}
    var file:=FileAccess.open(OS.get_environment("PR13_ROUTE_REPORT"),FileAccess.WRITE)
    file.store_string(JSON.stringify(report));file.close()
    store.free();gateway.free();probe.free()
    print(JSON.stringify({"ok":not checks.values().has(false),"checks":checks}))
    quit(0 if not checks.values().has(false) else 1)
