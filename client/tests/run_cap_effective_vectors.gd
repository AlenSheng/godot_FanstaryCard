extends SceneTree

var failures: Array = []
var rows := 0
var cases := {}

func _initialize() -> void:
	call_deferred("_run")

func check(ok: bool, field: String, row: Dictionary) -> void:
	if not ok and failures.size() < 80:
		failures.append({"case_id":row.get("case_id"), "hero":row.get("actual", {}).get("hero"), "seed":row.get("actual", {}).get("seed"), "field":field})

func _run() -> void:
	root.get_node("Game").set_process(false)
	var details = load("res://ui/numerical_details.gd")
	var palette = load("res://ui/palette.gd")
	var file := FileAccess.open(OS.get_environment("PR13_CAP_VECTORS"), FileAccess.READ)
	if file == null:
		quit(2)
		return
	while not file.eof_reached():
		var line := file.get_line()
		if line.is_empty(): continue
		var row: Dictionary = JSON.parse_string(line)
		var actual: Dictionary = row.actual
		check(str(row.source_sha) == OS.get_environment("PR13_CAP_SOURCE"), "exact native source", row)
		if str(row.case_id).ends_with("T01"):
			var before: Dictionary = details.inspect(actual.before, actual.hero)
			var after: Dictionary = details.inspect(actual.after, actual.hero)
			var key := "resistance_" + str(actual.element)
			for pair in [[before[key], "before"], [after[key], "after"]]:
				for field in ["raw", "effective"]:
					check(is_equal_approx(float(pair[0][field]), float(actual[field + "_" + pair[1]])), str(pair[1]) + " resistance " + field, row)
				check(is_equal_approx(float(pair[0].excess), float(actual["capped_" + pair[1]])), str(pair[1]) + " actual cap excess", row)
			check(is_equal_approx(float(after[key].effective) - float(before[key].effective), float(actual.marginal_effective)), "marginal effective resistance", row)
		elif str(row.case_id).ends_with("T02"):
			var view: Dictionary = details.inspect(actual.items, actual.hero)
			check(is_equal_approx(float(view.interval_seconds.raw), float(actual.equipment_raw)), "equipment raw interval", row)
			check(is_equal_approx(float(view.interval_seconds.effective), float(actual.equipment_interval)), "equipment clamp", row)
			check(bool(actual.post_clamp_conversion) and is_equal_approx(float(actual.converted_interval) * 2, float(actual.card_interval)), "conversion after clamp", row)
			check(is_equal_approx(float(actual.restored_interval), float(actual.equipment_interval)), "expired conversion restores equipment interval", row)
		else:
			var active: Dictionary = details.inspect(actual.items, actual.hero)
			var inactive: Dictionary = details.inspect(actual.inactive_items, actual.hero)
			var reduction: Dictionary = active.bulwark_reduction_percent
			if bool(actual.bulwark_class_applicable):
				check(str(reduction.status) == "Active" and is_equal_approx(float(reduction.effective), float(actual.bulwark_profile_effective)), "applicable actual reduction", row)
				check(str(inactive.bulwark_reduction_percent.status) == "Inactive" and is_zero_approx(float(inactive.bulwark_reduction_percent.excess)), "inactive has no capped excess", row)
			else:
				check(str(reduction.status) == "NotApplicable" and is_zero_approx(float(reduction.effective)) and is_zero_approx(float(reduction.excess)), "class inapplicable is not capped", row)
				check(is_equal_approx(float(reduction.not_applicable_amount), float(reduction.raw)), "inapplicable amount remains separate", row)
			check(int(actual.requested_shield) == int(actual.effective_shield) + int(actual.shield_overflow), "actual shield requested/effective/overflow ledger", row)
			check(int(actual.shield_after) <= int(actual.shield_cap) and not bool(actual.candidate_activation), "current shield cap and candidates off", row)
		cases[row.case_id] = int(cases.get(row.case_id, 0)) + 1
		rows += 1
	file.close()
	var localized := {}
	for language in ["zh-CN", "en"]:
		palette.set_language(language)
		localized[language] = {}
		for key in ["not_applicable", "inactive_affix", "resistance_stage", "draw_stage", "shield_stage"]:
			var words: String = details.text(key)
			check(not words.is_empty() and words != key, "localized " + language + " " + key, {})
			localized[language][key] = words
	check(rows == 864, "all native original witnesses", {})
	var result := {"ok":failures.is_empty(), "source_sha":OS.get_environment("PR13_CAP_SOURCE"), "native_rows":rows, "case_counts":cases, "localized_explanations":localized, "failures":failures, "whole_task_accepted":false}
	var output := FileAccess.open(OS.get_environment("PR13_CAP_RESULT"), FileAccess.WRITE)
	output.store_string(JSON.stringify(result))
	print(JSON.stringify(result))
	quit(0 if failures.is_empty() else 1)
