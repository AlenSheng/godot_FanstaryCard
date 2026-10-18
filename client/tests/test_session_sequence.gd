extends RefCounted

class RecordingGateway extends "res://network/gateway.gd":
	var sent: Array = []
	func send(kind: String, payload: Dictionary = {}, _request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload})
		return true

func run_test() -> Dictionary:
	var Gateway = load("res://network/gateway.gd")
	var Proto = load("res://network/protobuf.gd")
	var gateway = Gateway.new()
	gateway.persist_session = false
	var proto = Proto.new()
	var delivered: Array = []
	gateway.event_received.connect(func(kind, _payload): delivered.append(kind))
	gateway.last_sequence = 10
	var packet: PackedByteArray = proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "pong", "sequence": 11})
	gateway._receive(packet)
	gateway._receive(packet)
	var ok: bool = delivered.size() == 1 and gateway.last_sequence == 11
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "pong", "sequence": 15}))
	ok = ok and gateway.recovering and gateway.last_sequence == 11
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "room.snapshot", "sequence": 16, "payload": proto.encode("RoomSnapshotEvent", {"room_id": "room", "room_revision": 7})}))
	ok = ok and not gateway.recovering and gateway.last_sequence == 16 and gateway.room_revision == 7
	gateway.free()
	var restored := RecordingGateway.new()
	restored.persist_session = false
	restored.room_id = "cached-room"
	restored.last_sequence = 0
	restored._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "session.connected", "sequence": 71}))
	ok = ok and restored.sent.size() == 1 and restored.sent[0].kind == "room.snapshot.read"
	# A restarted event stream is received on a new peer.
	restored._schedule_reconnect()
	restored.last_sequence = 9000
	restored.sent.clear()
	restored._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "session.connected", "sequence": 1}))
	restored._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "room.snapshot", "sequence": 2, "payload": proto.encode("RoomSnapshotEvent", {"room_id": "cached-room", "room_revision": 9})}))
	ok = ok and restored.last_sequence == 2 and restored.room_revision == 9 and not restored.recovering
	restored._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "error.command_rejected", "sequence": 3, "payload": proto.encode("CommandRejectedEvent", {"code": "NOT_IN_ROOM"})}))
	# A packet without a command origin cannot revoke a valid route.
	ok = ok and restored.room_id == "cached-room" and restored.room_revision == 9
	restored.current_match_id = "cached-match"
	restored.room_context_epoch = 7
	restored.telemetry_context = {"phase": "new-load-phase"}
	ok = ok and restored.capture_context().get("room_context_epoch", -1) == 7
	restored._pending_request_started["snapshot-current"] = {"context": restored.capture_context()}
	restored._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "error.command_rejected", "sequence": 4, "request_id": "snapshot-current", "payload": proto.encode("CommandRejectedEvent", {"code": "NOT_IN_ROOM"})}))
	ok = ok and restored.room_id.is_empty() and restored.room_revision == 0
	restored.free()
	var diagnostics: Dictionary = _match_lifecycle_guard_checks(proto)
	return {"ok": ok and not diagnostics.values().has(false), "checks":diagnostics, "legacy_sequence_checks_passed":ok, "message": "Duplicate event ignored; sequence gap locks commands until authoritative snapshot; lifecycle rejection reasons remain trace-only"}

func _match_lifecycle_guard_checks(proto: RefCounted) -> Dictionary:
	var Gateway = load("res://network/gateway.gd")
	var gateway = Gateway.new()
	gateway.persist_session = false
	gateway.room_id = "room-current"
	gateway.current_match_id = "match-current"
	gateway.room_revision = 10
	gateway.room_context_epoch = 7
	gateway.last_sequence = 4
	gateway.recovering = true
	var trace: Array = []
	var delivered: Array = []
	gateway.telemetry.connect(func(sample): trace.append(sample.duplicate(true)))
	gateway.event_received.connect(func(kind, _payload): delivered.append(kind))
	var old: PackedByteArray = proto.encode("RoomStartedEvent", {"room_id":"room-old", "match_id":"match-old", "snapshot":{"room_id":"room-old", "match_id":"match-old"}})
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version":1, "type":"room.started", "sequence":4, "payload":old}))
	var checks := {}
	checks["duplicate_control_reason_trace_without_state_change"] = trace.size() == 1 and trace[0].reason == "stale_or_duplicate_sequence" and trace[0].trace_only and gateway.last_sequence == 4 and gateway.room_id == "room-current" and gateway.current_match_id == "match-current" and gateway.recovering and delivered.is_empty()
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version":1, "type":"room.started", "sequence":5, "payload":old}))
	checks["foreign_started_reason_preserves_route_and_recovery"] = trace.size() == 2 and trace[1].reason == "prior_room_context" and trace[1].expected_match_id == "match-current" and trace[1].received_match_id == "match-old" and gateway.last_sequence == 5 and gateway.room_id == "room-current" and gateway.current_match_id == "match-current" and gateway.room_revision == 10 and gateway.recovering and delivered.is_empty()
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version":1, "type":"combat.hit", "sequence":5, "payload":proto.encode("CombatHitEvent", {})}))
	checks["ordinary_duplicate_does_not_add_control_trace_volume"] = trace.size() == 2 and gateway.last_sequence == 5 and delivered.is_empty()
	var current: PackedByteArray = proto.encode("RoomStartedEvent", {"room_id":"room-current", "match_id":"match-current", "snapshot":{"room_id":"room-current", "match_id":"match-current"}})
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version":1, "type":"room.started", "sequence":6, "payload":current}))
	checks["same_context_positive_control_still_delivered"] = delivered == ["room.started"] and trace.size() == 2 and gateway.last_sequence == 6 and gateway.room_id == "room-current" and gateway.current_match_id == "match-current"
	checks["guard_trace_has_no_auth_or_packet_payload"] = trace.all(func(sample): return not sample.has("Authorization") and not sample.has("access_token") and not sample.has("payload") and not sample.has("packet"))
	gateway.free()
	return checks
