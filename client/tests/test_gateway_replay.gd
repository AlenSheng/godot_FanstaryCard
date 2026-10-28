extends RefCounted

const Proto = preload("res://network/protobuf.gd")

class RecordingGateway extends "res://network/gateway.gd":
	var sent: Array = []
	func send(kind: String, payload: Dictionary = {}, _request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload.duplicate(true)})
		return true

var checks: Array = []

func check(name: String, passed: bool, actual: Variant) -> void:
	checks.append({"name": name, "passed": passed, "actual": actual})

func packet(kind: String, sequence: int, payload: Dictionary = {}) -> PackedByteArray:
	var proto := Proto.new()
	var envelope := {"protocol_version": 1, "type": kind, "sequence": sequence}
	if not payload.is_empty():
		envelope.payload = proto.encode("RoomSnapshotEvent", payload)
	return proto.encode("ServerEnvelope", envelope)

func run_test() -> Dictionary:
	var gateway := RecordingGateway.new()
	gateway.persist_session = false
	gateway.last_sequence = 5
	var connections: Array = []
	gateway.connection_changed.connect(func(value): connections.append(value))
	var marker := packet("session.connected", 8)
	gateway._receive(marker)
	check("first actual gap requests one resume", gateway.sent.size() == 1 and gateway.sent[0].kind == "session.resume" and gateway.recovering and gateway.last_sequence == 5, gateway.sent.duplicate(true))
	gateway._last_ping = 1
	for index in range(40):
		gateway._receive(marker)
	check("40 identical replay markers do not amplify resume", gateway.sent.size() == 1, gateway.sent.size())
	check("replay markers do not reset heartbeat clock", gateway._last_ping == 1, gateway._last_ping)
	check("replay markers emit connected once", connections.size() == 1, connections.size())
	gateway._receive(packet("session.connected", 4))
	check("older connection markers cannot rewind current marker", gateway._connected_sequence == 8 and gateway.recovering and gateway.last_sequence == 5, {"marker": gateway._connected_sequence, "cursor": gateway.last_sequence, "recovering": gateway.recovering})
	gateway._receive(packet("pong", 6))
	gateway._receive(packet("pong", 7))
	check("contiguous missing events finish recovery", not gateway.recovering and gateway.last_sequence == 8, {"cursor": gateway.last_sequence, "recovering": gateway.recovering})
	var before := gateway.sent.size()
	gateway._receive(marker)
	check("completed recovery stays complete on marker replay", not gateway.recovering and gateway.last_sequence == 8 and gateway.sent.size() == before, {"cursor": gateway.last_sequence, "sent": gateway.sent.size()})
	gateway._schedule_reconnect()
	gateway.last_sequence = 9000
	gateway._receive(packet("session.connected", 1))
	check("new peer accepts a restarted sequence stream", gateway.online and not gateway.recovering and gateway.last_sequence == 1 and gateway._connected_sequence == 1, {"online": gateway.online, "cursor": gateway.last_sequence, "marker": gateway._connected_sequence})
	gateway.free()

	var room_gateway := RecordingGateway.new()
	room_gateway.persist_session = false
	room_gateway.room_id = "cached-room"
	room_gateway._receive(packet("session.connected", 71))
	for index in range(40):
		room_gateway._receive(packet("session.connected", 71))
	check("cached room snapshot requested once per peer", room_gateway.sent.size() == 1 and room_gateway.sent[0].kind == "room.snapshot.read", room_gateway.sent.size())
	room_gateway._schedule_reconnect()
	room_gateway._receive(packet("session.connected", 71))
	check("same numeric marker on a new peer is accepted", room_gateway.online and room_gateway.sent.size() == 2, {"online": room_gateway.online, "sent": room_gateway.sent.size()})
	room_gateway._receive(packet("room.snapshot", 72, {"room_id": "cached-room", "room_revision": 9}))
	check("authoritative snapshot remains applicable", room_gateway.last_sequence == 72 and room_gateway.room_revision == 9 and not room_gateway.recovering, {"cursor": room_gateway.last_sequence, "revision": room_gateway.room_revision})
	room_gateway.free()

	var ok := true
	for row in checks:
		ok = ok and row.passed
	return {"ok": ok, "checks": checks, "scope": "real Godot gateway codec and receive path; controlled sends; no LIVE or capacity claim"}
