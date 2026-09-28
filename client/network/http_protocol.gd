extends RefCounted

const Proto = preload("res://network/protobuf.gd")
const REGISTRY = preload("res://data/http_endpoints.json")
const SCHEMA = preload("res://data/http_schema.json")
const METHODS := {HTTPClient.METHOD_GET: "GET", HTTPClient.METHOD_POST: "POST", HTTPClient.METHOD_PUT: "PUT", HTTPClient.METHOD_DELETE: "DELETE"}
const PERIMETER := ["/", "/health/live", "/health/ready", "/api/v1/client-info"]
const EFFECT_DECIMALS := ["draw_charge", "draw_speed_modifier", "draw_speed_seconds", "stun_seconds", "draw_block_seconds", "conflict_cancel_bonus", "conflict_heal_coefficient"]

static func route(path: String, method: int) -> Dictionary:
	var actual: PackedStringArray = path.get_slice("?", 0).trim_suffix("/").split("/", true)
	for entry in REGISTRY.data.endpoints:
		if entry.method != METHODS.get(method, ""): continue
		var template: PackedStringArray = entry.path.split("/", true)
		if template.size() != actual.size(): continue
		var matches := true
		for index in template.size():
			var segment: String = template[index]
			if segment.begins_with("{") and segment.ends_with("}"):
				if actual[index].is_empty(): matches = false
				if segment.ends_with(":guid}"):
					var guid := RegEx.new()
					guid.compile("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
					if guid.search(actual[index]) == null: matches = false
			elif segment != actual[index]: matches = false
		if matches: return entry
	return {}

static func is_perimeter(path: String, method: int) -> bool:
	var canonical := path.get_slice("?", 0).trim_suffix("/")
	return method == HTTPClient.METHOD_GET and ("/" if canonical.is_empty() else canonical) in PERIMETER

static func to_wire(message: String, data: Dictionary) -> Dictionary:
	var output := {}
	for field in SCHEMA.data.messages[message].values():
		var key: String = field.name.to_camel_case()
		if not data.has(key) or data[key] == null: continue
		var value: Variant = data[key]
		if field.repeated:
			if not value is Array:
				output[field.name] = value # Codec reports the type error.
				continue
			var items := []
			for item in value:
				if field.name == "equipment_ids" and item == null: item = ""
				items.append(to_wire(field.type, item) if SCHEMA.data.messages.has(field.type) and item is Dictionary else item)
			output[field.name] = items
		else:
			output[field.name] = to_wire(field.type, value) if SCHEMA.data.messages.has(field.type) and value is Dictionary else value
	return output

static func from_wire(message: String, data: Dictionary) -> Dictionary:
	var output := {}
	for field in SCHEMA.data.messages[message].values():
		var key: String = field.name.to_camel_case()
		var is_message: bool = SCHEMA.data.messages.has(field.type)
		if not data.has(field.name):
			# Persisted shop payloads were sparse objects; omitted amount/cardId must
			# keep Dictionary.get defaults and has() checks at the presentation boundary.
			if message == "ShopProductPayload" and field.optional: continue
			# Nullable DTO values retain null, including optional scalar absence.
			output[key] = [] if field.repeated else null
			continue
		var value: Variant = data[field.name]
		if field.repeated:
			var items := []
			for item in value:
				if field.name == "equipment_ids" and item == "": items.append(null)
				else: items.append(from_wire(field.type, item) if is_message else item)
			output[key] = items
		elif is_message: output[key] = from_wire(field.type, value)
		elif message == "CardEffectResponse" and field.name in EFFECT_DECIMALS: output[key] = float(value)
		else: output[key] = value
	return output

static func header(headers: PackedStringArray, name: String) -> String:
	for line in headers:
		var colon := line.find(":")
		if colon >= 0 and line.left(colon).strip_edges().to_lower() == name.to_lower(): return line.substr(colon + 1).strip_edges()
	return ""

static func decode_response(contract: Dictionary, status: int, headers: PackedStringArray, bytes: PackedByteArray) -> Dictionary:
	if status == 204:
		return {"ok": bytes.is_empty(), "data": null, "error": "Unexpected body in empty response"}
	var media := header(headers, "Content-Type").get_slice(";", 0).strip_edges().to_lower()
	if media != "application/protobuf": return {"ok": false, "data": null, "error": "服务器返回了不支持的响应格式"}
	var proto := Proto.new(true)
	var success := status >= 200 and status < 300
	var message: String = contract.response if success else "HttpError"
	var decoded: Dictionary = proto.decode_http(message, bytes)
	if not proto.error.is_empty(): return {"ok": false, "data": null, "error": "服务器协议内容损坏: " + proto.error}
	var data: Variant = decoded
	if success and contract.get("unwrap_items", false): data = data.items
	return {"ok": true, "data": data, "error": ""}
