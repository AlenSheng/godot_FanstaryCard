extends SceneTree
const Proto = preload("res://network/protobuf.gd")
func _initialize() -> void:
	var encoder := Proto.new(true)
	var bootstrap := {"server_time": "2026-09-30T00:00:00Z", "config_version": "owned-loopback-fixture", "player": {"user_id": "00000000-0000-0000-0000-000000000001"}, "wallet": {}, "materials": {}}
	var b: PackedByteArray = encoder.encode("BootstrapResponse", bootstrap)
	if not encoder.error.is_empty(): quit(2); return
	FileAccess.open("res://bootstrap.pb", FileAccess.WRITE).store_buffer(b)
	var s: PackedByteArray = encoder.encode("SettlementResponse", {"settlement_id":"00000000-0000-0000-0000-000000000002", "match_id":"00000000-0000-0000-0000-000000000003", "player_id":"00000000-0000-0000-0000-000000000001", "result":"Extracted", "created_at":"2026-09-30T00:00:00Z"})
	if not encoder.error.is_empty(): quit(3); return
	FileAccess.open("res://settlement.pb", FileAccess.WRITE).store_buffer(s)
	quit(0)
