extends SceneTree

func _initialize() -> void:
	var path := OS.get_environment("FANTASYCARD_PREVIEW_VECTORS")
	var input: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not input is Dictionary or input.get("vectors", []).size() < 1000:
		push_error("At least 1000 authoritative vectors are required")
		quit(1)
		return
	var store = load("res://state/game_store.gd").new()
	var gateway = load("res://network/gateway.gd").new()
	gateway.persist_session = false
	gateway.online = true
	store.gateway = gateway
	var failures: Array = []
	for vector in input.vectors:
		store.room = vector.room
		var before := JSON.stringify(store.room)
		var actual: Dictionary = store._calculate_combat_preview(vector.ids)
		if before != JSON.stringify(store.room): failures.append({"index": vector.index, "field": "state_mutation"})
		for key in vector.expected:
			if key == "damage_segments":
				var left := {}
				var right := {}
				for segment in actual.get(key, []): left[segment.kind] = int(segment.amount)
				for segment in vector.expected[key]: right[segment.kind] = int(segment.amount)
				if left != right: failures.append({"index": vector.index, "field": key, "actual": left, "expected": right})
			elif key == "core_element":
				if actual.get(key, "") != vector.expected[key]: failures.append({"index": vector.index, "field": key})
			elif absf(float(actual.get(key, -1000)) - float(vector.expected[key])) > .000001:
				failures.append({"index": vector.index, "field": key, "actual": actual.get(key), "expected": vector.expected[key]})
	var result := {"ok": failures.is_empty(), "vectors": input.vectors.size(), "failures": failures}
	var destination := OS.get_environment("FANTASYCARD_PREVIEW_RESULT")
	if not destination.is_empty():
		var file := FileAccess.open(destination, FileAccess.WRITE)
		file.store_string(JSON.stringify(result, "  "))
	print(JSON.stringify({"ok": result.ok, "vectors": result.vectors, "failure_count": failures.size(), "first_failures": failures.slice(0, 15)}))
	store.free()
	gateway.free()
	quit(0 if result.ok else 1)
