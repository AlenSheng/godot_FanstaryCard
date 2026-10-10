extends SceneTree

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	root.get_node("Game").set_process(false)
	var details = load("res://ui/numerical_details.gd")
	var items: Array = []
	for slot in ["Head", "Chest", "Hands", "Legs", "Feet"]:
		items.append({"instanceId":slot, "slot":slot, "quality":"Purple", "element":"Fire", "level":5, "effectAffix":"Bulwark", "secondaryTrait":"DrawInterval"})
	var guardian: Dictionary = details.inspect(items, "Guardian")
	var mage: Dictionary = details.inspect(items, "Mage")
	var inactive: Dictionary = details.inspect([items[0]], "Guardian")
	var result := {
		"kind":"cap_effective_before_fix_probe",
		"guardian_reduction":guardian.bulwark_reduction_percent,
		"mage_reduction":mage.bulwark_reduction_percent,
		"inactive_reduction":inactive.bulwark_reduction_percent,
		"resistance":guardian.resistance_Fire,
		"equipment_interval":guardian.interval_seconds,
		"observed_non_guardian_mislabeled_as_excess":is_zero_approx(float(mage.bulwark_reduction_percent.effective)) and float(mage.bulwark_reduction_percent.excess)>0,
		"observed_inactive_mislabeled_as_excess":not bool(inactive.bulwark_reduction_percent.active) and float(inactive.bulwark_reduction_percent.excess)>0,
		"whole_task_accepted":false
	}
	var path := OS.get_environment("PR13_CAP_PROBE_RESULT")
	if not path.is_empty():
		var file := FileAccess.open(path, FileAccess.WRITE)
		file.store_string(JSON.stringify(result))
	print(JSON.stringify(result))
	quit(0)
