extends RefCounted

const SCHEMA = preload("res://data/realtime_schema.json")
const HTTP_SCHEMA = preload("res://data/http_schema.json")
enum { INT32, INT64, UINT32, BOOL, STRING, BYTES, MESSAGE }
const EMPTY_FIELD: Array = []
const EFFECT_DECIMALS := ["draw_charge", "draw_speed_modifier", "draw_speed_seconds", "stun_seconds", "draw_block_seconds", "conflict_cancel_bonus", "conflict_heal_coefficient"]
static var _realtime_plans: Dictionary = _compile(SCHEMA.data.messages)
static var _http_plans: Dictionary = _compile(HTTP_SCHEMA.data.messages)
var _plans: Dictionary = _realtime_plans
const SCALARS := ["int32", "int64", "uint32", "bool"]
var schema: Dictionary = SCHEMA.data.messages
var max_bytes: int = 16384
var max_string_bytes: int = 16384
var max_elements: int = 4096
var error: String = ""
var _cursor: int = 0

func _init(http: bool = false) -> void:
	if http:
		schema = HTTP_SCHEMA.data.messages
		_plans = _http_plans
		max_bytes = 2 * 1024 * 1024
		max_string_bytes = 128 * 1024

func _child():
	var child = get_script().new()
	child.schema = schema
	child.max_bytes = max_bytes
	child.max_string_bytes = max_string_bytes
	child.max_elements = max_elements
	return child

func encode(message: String, value: Dictionary, depth: int = 0) -> PackedByteArray:
	error = ""
	var output := PackedByteArray()
	if not schema.has(message) or depth > 24:
		error = "Unknown message or depth limit"
		return output
	for number in schema[message]:
		var field: Dictionary = schema[message][number]
		if not value.has(field.name) or value[field.name] == null: continue
		if field.repeated and not value[field.name] is Array:
			error = "Repeated field must be an array"
			break
		var values: Array = value[field.name] if field.repeated else [value[field.name]]
		if values.size() > max_elements:
			error = "Protobuf collection limit"
			break
		var packed := PackedByteArray()
		for item in values:
			var kind: String = field.type
			if kind in SCALARS:
				if (kind == "bool" and not item is bool) or (kind != "bool" and not item is int):
					error = "Invalid scalar type"
					break
				if (kind == "int32" and (item < -2147483648 or item > 2147483647)) or (kind == "uint32" and (item < 0 or item > 4294967295)):
					error = "Scalar out of range"
					break
				if field.repeated: packed.append_array(_varint(int(item)))
				else:
					output.append_array(_varint(int(number) << 3))
					output.append_array(_varint(int(item)))
			else:
				var body: PackedByteArray
				if kind == "string":
					if not item is String:
						error = "Invalid string type"
						break
					body = item.to_utf8_buffer()
					if body.size() > max_string_bytes: error = "Protobuf string limit"
				elif kind == "bytes":
					if not item is PackedByteArray:
						error = "Invalid bytes type"
						break
					body = item
				else:
					if not item is Dictionary:
						error = "Invalid message type"
						break
					var nested = _child()
					body = nested.encode(kind, item, depth + 1)
					error = nested.error
				if not error.is_empty(): break
				output.append_array(_varint((int(number) << 3) | 2))
				output.append_array(_varint(body.size()))
				output.append_array(body)
			if output.size() > max_bytes or packed.size() > max_bytes:
				error = "Protobuf size limit"
				break
		if not packed.is_empty():
			output.append_array(_varint((int(number) << 3) | 2))
			output.append_array(_varint(packed.size()))
			output.append_array(packed)
		if not error.is_empty(): break
	if output.size() > max_bytes: error = "Protobuf size limit"
	return output if error.is_empty() else PackedByteArray()

# Decode immutable compiled descriptors over offsets in the original packet.
# A single cursor and in-place singular-message merge avoid per-child codecs,
# intermediate wire buffers and the second HTTP dictionary traversal.
func decode(message: String, bytes: PackedByteArray, depth: int = 0) -> Dictionary:
	return _decode(message, bytes, depth, false)

func decode_http(message: String, bytes: PackedByteArray) -> Dictionary:
	return _decode(message, bytes, 0, true)

func _decode(message: String, bytes: PackedByteArray, depth: int, presentation: bool) -> Dictionary:
	error = ""
	_cursor = 0
	if bytes.size() > max_bytes or depth > 24 or not _plans.has(message):
		error = "Protobuf size/depth limit or unknown message"
		return {}
	var output := _decode_range(message, bytes, bytes.size(), depth, presentation)
	return output if error.is_empty() else {}

func _decode_range(message: String, bytes: PackedByteArray, end: int, depth: int, presentation: bool, existing: Variant = null) -> Dictionary:
	if depth > 24:
		error = "Protobuf depth limit"
		return {}
	var plan: Array = _plans[message]
	var fields: Dictionary = plan[0]
	var defaults: Dictionary = plan[2] if presentation else plan[1]
	var output: Dictionary = existing if existing is Dictionary else defaults.duplicate(true)
	while _cursor < end and error.is_empty():
		# Most field tags occupy one byte. Keep the common case out of a call/loop.
		var tag: int = bytes[_cursor]
		_cursor += 1
		if tag >= 128:
			_cursor -= 1
			tag = _read_varint(bytes, end)
		var number := tag >> 3
		var wire := tag & 7
		if not error.is_empty(): break
		if number <= 0 or number > 536870911:
			error = "Invalid field tag"
			break
		var field: Array = fields.get(number, EMPTY_FIELD)
		var length_end := _cursor
		var item: Variant
		match wire:
			0: item = _read_varint(bytes, end)
			1, 5: _cursor += 8 if wire == 1 else 4
			2:
				var size := _read_varint(bytes, end)
				if not error.is_empty(): break
				if size < 0 or size > end - _cursor:
					error = "Truncated field"
					break
				length_end = _cursor + size
			_: error = "Unsupported wire type"
		if _cursor > end: error = "Truncated fixed field"
		if not error.is_empty(): break
		if field.is_empty():
			if wire == 2: _cursor = length_end
			continue
		var kind: int = field[2]
		var repeated: bool = field[3]
		var key: String = field[1] if presentation else field[0]
		if kind <= BOOL and repeated and wire == 2:
			var values: Array = output[key]
			while _cursor < length_end and error.is_empty():
				var scalar_value := _read_varint(bytes, length_end)
				if not error.is_empty(): break
				values.append(_scalar_code(kind, scalar_value))
				if values.size() > max_elements: error = "Protobuf collection limit"
			continue
		if wire != (0 if kind <= BOOL else 2):
			error = "Unexpected wire type"
			break
		if kind == STRING:
			if length_end - _cursor > max_string_bytes:
				error = "Protobuf string limit"
				break
			var text_bytes := bytes.slice(_cursor, length_end)
			var decoded := text_bytes.get_string_from_utf8()
			if decoded.to_utf8_buffer() != text_bytes:
				error = "Invalid UTF-8"
				break
			item = float(decoded) if presentation and field[6] else decoded
			if presentation and field[7] and decoded.is_empty(): item = null
			_cursor = length_end
		elif kind <= BOOL: item = _scalar_code(kind, item)
		elif kind == BYTES:
			item = bytes.slice(_cursor, length_end)
			_cursor = length_end
		else:
			# Existing values merge according to protobuf presence rules; absent
			# scalars in a later occurrence must not overwrite an earlier value.
			item = _decode_range(field[5], bytes, length_end, depth + 1, presentation, null if repeated else output.get(key))
			if not error.is_empty(): break
		if repeated:
			var values: Array = output[key]
			values.append(item)
			if values.size() > max_elements: error = "Protobuf collection limit"
		else: output[key] = item
	return output

func _scalar_code(kind: int, value: int) -> Variant:
	if kind == BOOL: return value != 0
	if kind == UINT32: return value & 0xffffffff
	if kind == INT32:
		var low := value & 0xffffffff
		return low - 4294967296 if low >= 2147483648 else low
	return value

func _scalar(kind: String, value: int) -> Variant:
	if kind == "bool": return value != 0
	if kind == "uint32": return value & 0xffffffff
	if kind == "int32":
		var low := value & 0xffffffff
		return low - 4294967296 if low >= 2147483648 else low
	return value

func _varint(value: int) -> PackedByteArray:
	var bytes := PackedByteArray()
	for index in range(10):
		if value >= 0 and value < 128:
			bytes.append(value)
			return bytes
		bytes.append((value & 127) | 128)
		value = (value >> 7) & 0x01ffffffffffffff
	return bytes

func _read_varint(bytes: PackedByteArray, end: int = -1) -> int:
	if end < 0: end = bytes.size()
	if _cursor >= end:
		error = "Truncated varint"
		return 0
	var first: int = bytes[_cursor]
	_cursor += 1
	if first < 128: return first
	var value: int = first & 127
	for index in range(1, 10):
		if _cursor >= end:
			error = "Truncated varint"
			return 0
		var byte: int = bytes[_cursor]
		_cursor += 1
		if index == 9 and byte > 1:
			error = "Varint overflow"
			return 0
		value |= (byte & 127) << (index * 7)
		if byte < 128: return value
	error = "Invalid varint"
	return 0

static func _compile(messages: Dictionary) -> Dictionary:
	var plans := {}
	var kinds := {"int32":INT32,"int64":INT64,"uint32":UINT32,"bool":BOOL,"string":STRING,"bytes":BYTES}
	for message in messages:
		var fields := {}
		var raw_defaults := {}
		var ui_defaults := {}
		for number in messages[message]:
			var field: Dictionary = messages[message][number]
			var name: String = field.name
			var camel := name.to_camel_case()
			var kind: int = kinds.get(field.type,MESSAGE)
			var decimal: bool = message == "CardEffectResponse" and name in EFFECT_DECIMALS
			var descriptor: Array = [name,camel,kind,bool(field.repeated),bool(field.optional),str(field.type),decimal,name == "equipment_ids"]
			descriptor.make_read_only()
			fields[int(number)]=descriptor
			if field.repeated:
				raw_defaults[name]=[]
				ui_defaults[camel]=[]
			elif field.optional or kind == MESSAGE:
				if message != "ShopProductPayload": ui_defaults[camel]=null
			else:
				var default: Variant = "" if kind == STRING else PackedByteArray() if kind == BYTES else false if kind == BOOL else 0
				raw_defaults[name]=default
				ui_defaults[camel]=0.0 if decimal else default
		fields.make_read_only()
		raw_defaults.make_read_only()
		ui_defaults.make_read_only()
		var plan: Array=[fields,raw_defaults,ui_defaults]
		plan.make_read_only()
		plans[message]=plan
	plans.make_read_only()
	return plans
