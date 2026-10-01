extends SceneTree

const Observer = preload("res://tests/pr13_load02_timeout_stop.gd")

class FailureProbe:
	extends Observer.Load02Probe

	func _ready() -> void:
		pass

	func _process(_delta: float) -> void:
		pass

	func _snapshot(_cutoff: String, _outcome: String = "") -> Dictionary:
		return {"stop_requested": true, "partition": {"started": 1, "failed": 0, "completed": 0}}

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var failure_stage := OS.get_environment("PR13_OBSERVATION_FAILURE")
	var outcome := OS.get_environment("PR13_OBSERVATION_FINISH")
	if failure_stage not in ["open", "publish", "prior"] or outcome not in ["completed", "cancelled"]:
		quit(2)
		return
	var probe := FailureProbe.new()
	root.add_child(probe)
	probe.Game = root.get_node("Game")
	probe.report_path = "user://publication-failure-" + str(OS.get_process_id()) + ".json"
	var blocked_path := probe.report_path + ".accounting.json"
	if failure_stage == "open": blocked_path += ".tmp"
	if failure_stage == "prior": blocked_path = probe.report_path + ".stop-observed.json.tmp"
	var setup := DirAccess.make_dir_absolute(blocked_path)
	if setup != OK:
		push_error("Could not create controlled publication failure: " + error_string(setup))
		quit(2)
		return
	print(JSON.stringify({"controlled_publication_failure": true, "stage": failure_stage, "outcome": outcome}))
	if failure_stage == "prior": probe._write_observation(".stop-observed.json", "controlled_prior_failure")
	await probe._finish(outcome == "completed", "controlled publication failure", 0)
	print(JSON.stringify({"original_finish_reached": probe.finished,
		"accounting_is_file": FileAccess.file_exists(probe.report_path + ".accounting.json")}))
