extends RefCounted

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
	return {"ok": ok, "message": "Duplicate event ignored; sequence gap locks commands until authoritative snapshot"}
