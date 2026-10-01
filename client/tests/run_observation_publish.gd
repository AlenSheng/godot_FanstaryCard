extends SceneTree

const Observer = preload("res://tests/pr13_load02_timeout_stop.gd")

class HalfWriteProbe:
	extends Observer.Load02Probe
	var final_visible_during_half_write := false
	var partial_was_invalid := false

	func _snapshot(_cutoff: String, _outcome: String = "") -> Dictionary:
		return {"stop_requested": true, "partition": {"started": 1, "failed": 1, "completed": 0}}

	func _open_observation(path: String) -> FileAccess:
		var file := FileAccess.open(path, FileAccess.WRITE)
		file.store_string("{")
		file.flush()
		final_visible_during_half_write = FileAccess.file_exists(report_path + ".stop-observed.json")
		var parser := JSON.new()
		partial_was_invalid = parser.parse(FileAccess.get_file_as_string(path)) != OK
		file.seek(0)
		return file

func _initialize() -> void:
	var probe := HalfWriteProbe.new()
	probe.report_path = "user://observation-" + str(OS.get_process_id())
	probe._write_observation(".stop-observed.json", "controlled_half_write")
	var final_path := probe.report_path + ".stop-observed.json"
	var result = JSON.parse_string(FileAccess.get_file_as_string(final_path))
	var ok: bool = probe.partial_was_invalid and not probe.final_visible_during_half_write and result is Dictionary and result.stop_requested and not FileAccess.file_exists(final_path + ".tmp")
	print(JSON.stringify({"ok": ok, "partial_was_invalid": probe.partial_was_invalid,
		"final_visible_during_half_write": probe.final_visible_during_half_write, "receipt": result}))
	DirAccess.remove_absolute(final_path)
	probe.free()
	quit(0 if ok else 1)
