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
	restored.last_sequence = 9000
	restored.sent.clear()
	restored._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "session.connected", "sequence": 1}))
	restored._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "room.snapshot", "sequence": 2, "payload": proto.encode("RoomSnapshotEvent", {"room_id": "cached-room", "room_revision": 9})}))
	ok = ok and restored.last_sequence == 2 and restored.room_revision == 9 and not restored.recovering
	restored._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "error.command_rejected", "sequence": 3, "payload": proto.encode("CommandRejectedEvent", {"code": "NOT_IN_ROOM"})}))
	ok = ok and restored.room_id.is_empty() and restored.room_revision == 0
	restored.free()
	return {"ok": ok, "message": "Duplicate event ignored; sequence gap locks commands until authoritative snapshot"}
