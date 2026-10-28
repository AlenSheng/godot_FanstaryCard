extends Node

const Details = preload("res://ui/numerical_details.gd")
const Proto = preload("res://network/protobuf.gd")
const PoolView = preload("res://ui/monster_pool_view.gd")
var failures: Array[String] = []

func _ready() -> void:
	Game.set_process(false)
	call_deferred("_run")

func _check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)

func _run() -> void:
	var items: Array = []
	for slot in ["Head", "Chest", "Hands", "Legs", "Feet"]:
		items.append({"instanceId":slot, "slot":slot, "quality":"Purple", "element":"Fire", "level":5, "effectAffix":"Bulwark", "secondaryTrait":"DrawInterval"})
	var guardian: Dictionary = Details.inspect(items, "Guardian")
	var mage: Dictionary = Details.inspect(items, "Mage")
	_check(is_equal_approx(float(guardian.interval_seconds.effective), 1.8), "Draw floor must be 1.8 seconds")
	_check(is_equal_approx(float(guardian.resistance_Fire.effective), 0.60), "Element resistance must cap at 60 percent")
	_check(float(guardian.resistance_Fire.excess) > 0.0, "Resistance excess must be visible")
	_check(float(guardian.bulwark_reduction_percent.effective) > 0.0, "Guardian receives active Bulwark reduction")
	_check(is_zero_approx(float(mage.bulwark_reduction_percent.effective)), "Mage cannot receive Guardian-only reduction")
	var proto := Proto.new()
	var decision := {"candidate_id":"00000000-0000-0000-0000-000000000001", "accept":false}
	var encoded: PackedByteArray = proto.encode("MonsterCardChooseCommand", decision)
	_check(proto.error.is_empty(), "Monster command must encode")
	var decoded: Dictionary = proto.decode("MonsterCardChooseCommand", encoded)
	_check(proto.error.is_empty(), "Monster command must decode")
	_check(decoded.get("candidate_id", "") == decision.candidate_id and not bool(decoded.get("accept", true)), "False decision and identity must survive wire roundtrip")
	var pool := {"capacity":5, "pending":[{"instance_id":decision.candidate_id, "card_id":"M-FIREBAT", "level":0}], "active":[]}
	encoded = proto.encode("RoomMonsterPool", pool)
	decoded = proto.decode("RoomMonsterPool", encoded)
	_check(proto.error.is_empty() and int(decoded.get("capacity", 0)) == 5, "Monster pool must roundtrip")
	Game.room = {"player":{"monster_pool":pool}, "allowed_actions":["monster.choose"]}
	_check(Game._intent_valid("monster.choose", decision), "Current offer should stay valid")
	Game.room.player.monster_pool.pending = []
	_check(not Game._intent_valid("monster.choose", decision), "Stale offer after reconnect must be discarded")
	for language in PoolView.TEXT.keys():
		_check(not str(PoolView.TEXT[language].get("accept", "")).is_empty(), "Missing localized monster action: " + language)
	print(JSON.stringify({"suite":"numerical-integration", "ok":failures.is_empty(), "failures":failures}))
	get_tree().quit(0 if failures.is_empty() else 1)
