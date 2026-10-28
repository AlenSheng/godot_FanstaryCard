extends SceneTree
const Store = preload("res://state/game_store.gd")
const LoadClient = preload("res://tests/gameplay_load_client.gd")
class RecordingGateway extends "res://network/gateway.gd":
    var sent: Array = []
    func send(kind: String,_payload: Dictionary = {},_request_id: String = "") -> bool:
        sent.append(kind)
        return true
func _initialize() -> void: call_deferred("run")
func run() -> void:
    var store: Node = Store.new()
    var gateway: Node = RecordingGateway.new()
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
    store.room.allowed_actions = ["battle.play_cards"]
    store.room.player = {"phase":"Pve","player_id":"self","hand":[{"instance_id":"card","card_id":"C01"}],"combat":{"hp":70,"maximum_hp":70}}
    store.room.pve = {"battle_id":"dead-target","current_target_id":"dead","monsters":[{"monster_id":"dead","hp":0}]}
    store.selected_cards = ["card"]
    store.play_cards()
    var waiting: Dictionary = store.combat_wait_state()
    var invalid_target_safe: bool = gateway.sent.is_empty() and store._pending_commands.is_empty() and waiting.reason=="target" and not waiting.legal_opportunity and probe._select_cards([]).is_empty()
    var checks := {"new_profile_requires_actual_clear":not before_clear and after_clear,"original_extraction_policy_preserved":not original_before_move and original_after_move,"hidden_paths_ignored":hidden_safe,"no_legal_move_returns_empty":empty.is_empty(),"no_invalid_target_command":invalid_target_safe}
    var report := {"checks":checks,"cases":[{"case_id":"PR13-B03.2-T03","executed":true,"status":"Passed" if hidden_safe else "Failed","profiles_executed":["OFFLINE"],"actual":{"first":first,"second":second,"legal_moves":moves,"empty_result":empty},"scope":"Actual native robot policy with only public legal coordinates/visited state; altered hidden fixture fields are not read; no sampled experiment claim"}],"new_profile":"clear-then-extract-visible-outer-ring-v1","original_capacity_evidence":false}
    report.cases.append({"case_id":"PR13-B03.1-T03","executed":true,"status":"Passed" if invalid_target_safe else "Failed","profiles_executed":["OFFLINE"],"actual":{"waiting":waiting,"command_dispatches":gateway.sent.size(),"pending_commands":store._pending_commands.size(),"no_legal_move":empty},"scope":"Actual production store command/target validation; controlled native gateway dispatch recorder; no sampled experiment layer"})
    var file:=FileAccess.open(OS.get_environment("PR13_ROUTE_REPORT"),FileAccess.WRITE)
    file.store_string(JSON.stringify(report));file.close()
    store.free();gateway.free();probe.free()
    print(JSON.stringify({"ok":not checks.values().has(false),"checks":checks}))
    quit(0 if not checks.values().has(false) else 1)
