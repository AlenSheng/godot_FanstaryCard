extends RefCounted

const Proto = preload("res://network/protobuf.gd")
const Http = preload("res://network/http_protocol.gd")

func run_test() -> Dictionary:
	var checks := {}
	var route := Http.route("/api/v1/inventory/discard", HTTPClient.METHOD_POST)
	checks["registered write route"] = route.get("request") == "DiscardEquipmentRequest" and route.get("response") == "DiscardEquipmentResponse"
	var proto := Proto.new(true)
	for name in ["active", "legacy"]:
		var body := {"items": [{"equipmentId": "10000000-0000-0000-0000-000000000001", "expectedVersion": 9007199254740993}]}
		if name == "active": body["seasonId"] = "original"
		var actual := FileAccess.get_file_as_bytes("res://tests/discard-wire/" + name + ".request")
		var encoded: PackedByteArray = proto.encode("DiscardEquipmentRequest", Http.to_wire("DiscardEquipmentRequest", body))
		checks[name + " native bytes match actual CSharp request"] = encoded == actual
		var decoded: Dictionary = proto.decode_http("DiscardEquipmentRequest", actual)
		checks[name + " exact expected int64"] = decoded.items.size() == 1 and decoded.items[0].expectedVersion == 9007199254740993
		var raw := FileAccess.get_file_as_bytes("res://tests/discard-wire/" + name + ".response")
		var reply := Http.decode_response(route, 200, PackedStringArray(["Content-Type: application/protobuf"]), raw)
		checks[name + " actual typed receipt decoded"] = reply.ok and reply.data.items.size() == 1
		if reply.ok and reply.data.items.size() == 1:
			var item: Dictionary = reply.data.items[0]
			checks[name + " retained body and exact next version"] = item.instanceId == body.items[0].equipmentId and item.version == 9007199254740994 and item.location == "Recycled" and item.isBound
			checks[name + " original source scope"] = item.get("seasonId") == ("original" if name == "active" else null) and reply.data.get("seasonId") == item.get("seasonId")
	checks["native encoder no error"] = proto.error.is_empty()
	return {"ok": not checks.values().has(false), "checks": checks}
