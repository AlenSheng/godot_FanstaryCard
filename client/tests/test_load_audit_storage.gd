extends RefCounted

class Probe extends "res://tests/gameplay_load_client.gd":
	func _ready() -> void: set_process(false)
	func _audit_segment_limit_bytes() -> int: return 4096
	func _audit_record_limit_bytes() -> int: return 2048
	func _audit_max_segments() -> int: return 3

class FakeGame extends Node:
	var room := {}

func make_probe(base: String, name: String) -> Node:
	var probe := Probe.new()
	probe.Game = FakeGame.new()
	probe.client_id = name
	probe.run_id = "audit-test"
	probe.process_epoch = name
	probe.report_path = base + "/" + name + ".json"
	probe.stage = "playing"
	return probe

func dispose(probe: Node) -> void:
	var state := {"client_id":probe.client_id,"run_id":probe.run_id,"process_epoch":probe.process_epoch,"event_seq_max":probe.event_seq,
		"audit_lost_count":probe.audit_lost_count,"audit_storage":probe._audit_storage_observation()}
	var file := FileAccess.open(probe.report_path+".writer-state.json",FileAccess.WRITE)
	file.store_string(JSON.stringify(state))
	file.close()
	probe.Game.free()
	probe.free()

func archive_rows(probe: Node) -> Array:
	var rows: Array = []
	for index in range(probe.audit_segment_bytes.size()):
		var text := FileAccess.get_file_as_string(probe._audit_segment_path(index))
		for line in text.split("\n",false):rows.append(JSON.parse_string(line))
	return rows

func run_test() -> Dictionary:
	var base := OS.get_environment("LOAD073_NATIVE_ROOT")
	if base.is_empty():base=ProjectSettings.globalize_path("user://bounded-audit-"+str(Time.get_ticks_usec()))
	DirAccess.make_dir_recursive_absolute(base)
	var checks := {}
	var probe := make_probe(base,"rotation")
	for index in range(12):probe._on_telemetry({"type":"boundary_test","message":"合法80/70与UTF8甲乙丙丁"+str(index)})
	probe._flush_audit()
	var storage: Dictionary=probe._audit_storage_observation()
	var rows: Array=archive_rows(probe)
	checks["rotation preserves every sequence and complete UTF8 records"] = rows.size()==12 and rows.map(func(row):return int(row.event_seq))==range(1,13) and rows.all(func(row):return str(row.message).begins_with("合法80/70"))
	checks["explicit tiny fixture limits produce multiple bounded append-only segments"] = storage.segment_count>=2 and storage.segment_count<=3 and storage.segment_bytes.all(func(size):return size<=4096) and probe.audit_lost_count==0
	var first_before := FileAccess.get_file_as_bytes(probe._audit_segment_path(0))
	probe._on_telemetry({"type":"boundary_test","message":"tail"})
	probe._flush_audit()
	checks["later flush never overwrites an earlier segment"] = FileAccess.get_file_as_bytes(probe._audit_segment_path(0))==first_before and archive_rows(probe).size()==13
	checks["final storage counters reconcile exact file bytes and zero tail buffer"] = probe.audit_bytes_written==probe.audit_segment_bytes.reduce(func(sum,size):return sum+size,0) and probe.audit_events_written==13 and probe.audit_buffer.is_empty() and probe._audit_storage_observation().buffer_serialized_bytes==0
	dispose(probe)
	probe=make_probe(base,"overflow")
	for index in range(100):probe._on_telemetry({"type":"boundary_test","message":"overflow-"+str(index)})
	probe._flush_audit()
	var count: int=archive_rows(probe).size()
	checks["total archive bound refuses extra records without silent wraparound"] = probe.audit_segment_bytes.size()==3 and probe.audit_segment_bytes.all(func(size):return size<=4096) and count<100 and probe.audit_lost_count==100-count and probe.audit_last_error=="archive_size_limit"
	var bytes_before: int=probe.audit_bytes_written
	probe._on_telemetry({"type":"boundary_test","message":"post-cap"})
	probe._flush_audit()
	checks["cap remains latched and accounts every later event as lost"] = probe.audit_bytes_written==bytes_before and probe.audit_lost_count==101-count
	dispose(probe)
	probe=make_probe(base,"oversize")
	probe._on_telemetry({"type":"boundary_test","message":"甲".repeat(1500)})
	checks["UTF8 byte bound applies before retaining oversized ring or buffer row"] = probe.audit_lost_count==1 and probe.audit_last_error=="record_size_limit" and probe.audit_buffer.is_empty() and probe.telemetry.is_empty() and probe.operations.is_empty() and probe.event_seq==1
	probe._on_telemetry({"type":"boundary_test","message":"after-rejected-record"})
	probe._flush_audit()
	checks["normal records remain accountable after rejected oversized record"] = archive_rows(probe).size()==1 and archive_rows(probe)[0].event_seq==2 and probe.audit_lost_count==1
	dispose(probe)
	probe=make_probe(base,"openfailure")
	DirAccess.make_dir_recursive_absolute(probe.report_path+".telemetry.jsonl")
	for index in range(9):probe._on_telemetry({"type":"boundary_test","message":str(index)})
	probe._flush_audit()
	checks["actual FileAccess open failure counts all nine lost and clears buffer"] = probe.audit_lost_count==9 and probe.audit_last_error=="open_failed" and probe.audit_buffer.is_empty()
	DirAccess.remove_absolute(probe.report_path+".telemetry.jsonl")
	probe._on_telemetry({"type":"boundary_test","message":"after-restored-path"})
	probe._flush_audit()
	checks["restored own path resumes but earlier loss is never erased"] = archive_rows(probe).size()==1 and archive_rows(probe)[0].event_seq==10 and probe.audit_lost_count==9
	dispose(probe)
	probe=make_probe(base,"foreignexisting")
	FileAccess.open(probe.report_path+".telemetry.jsonl",FileAccess.WRITE).store_string("existing-original\n")
	probe._on_telemetry({"type":"boundary_test","message":"must-not-overwrite"})
	probe._flush_audit()
	checks["unexpected existing archive bytes remain untouched and evidence loses event"] = FileAccess.get_file_as_string(probe.report_path+".telemetry.jsonl")=="existing-original\n" and probe.audit_lost_count==1 and probe.audit_last_error=="unexpected_existing_bytes"
	dispose(probe)
	return {"ok":not checks.values().has(false),"checks":checks,"archive_root":base,"scope":"OFFLINE actual native FileAccess and UTF8 boundary fixtures with declared small limits; no physical disk exhaustion or gameplay worlds"}
