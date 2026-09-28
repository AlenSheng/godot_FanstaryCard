extends RefCounted

const SCHEMA = preload("res://data/realtime_schema.json")
const HTTP_SCHEMA = preload("res://data/http_schema.json")
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

func decode(message: String, bytes: PackedByteArray, depth: int = 0) -> Dictionary:
	error = ""
	_cursor = 0
	if bytes.size() > max_bytes or depth > 24 or not schema.has(message):
		error = "Protobuf size/depth limit or unknown message"
		return {}
	var fields: Dictionary = schema[message]
	var output: Dictionary = {}
	var singular_messages: Dictionary = {}
	for field in fields.values():
		if field.repeated: output[field.name] = []
		elif not field.optional:
			if field.type == "string": output[field.name] = ""
			elif field.type == "bytes": output[field.name] = PackedByteArray()
			elif field.type == "bool": output[field.name] = false
			elif field.type in SCALARS: output[field.name] = 0
	while _cursor < bytes.size() and error.is_empty():
		var tag: int = _read_varint(bytes)
		var number := tag >> 3
		var wire := tag & 7
		if not error.is_empty(): break
		if number <= 0 or number > 536870911:
			error = "Invalid field tag"
			break
		var item: Variant
		match wire:
			0: item = _read_varint(bytes)
			1, 5: _cursor += 8 if wire == 1 else 4
			2:
				var size := _read_varint(bytes)
				if not error.is_empty(): break
				if size < 0 or size > bytes.size() - _cursor:
					error = "Truncated field"
					break
				item = bytes.slice(_cursor, _cursor + size)
				_cursor += size
			_: error = "Unsupported wire type"
		if _cursor > bytes.size(): error = "Truncated fixed field"
		if not error.is_empty(): break
		if not fields.has(str(number)): continue
		var field: Dictionary = fields[str(number)]
		var scalar: bool = field.type in SCALARS
		if scalar and field.repeated and wire == 2:
			var packed = _child()
			while packed._cursor < item.size():
				var scalar_value: int = packed._read_varint(item)
				if not packed.error.is_empty():
					error = packed.error
					break
				output[field.name].append(_scalar(field.type, scalar_value))
				if output[field.name].size() > max_elements:
					error = "Protobuf collection limit"
					break
			continue
		if wire != (0 if scalar else 2):
			error = "Unexpected wire type"
			break
		if field.type == "string":
			if item.size() > max_string_bytes:
				error = "Protobuf string limit"
				break
			var decoded: String = item.get_string_from_utf8()
			if decoded.to_utf8_buffer() != item:
				error = "Invalid UTF-8"
				break
			item = decoded
		elif scalar: item = _scalar(field.type, item)
		elif field.type != "bytes":
			if not field.repeated:
				# Protobuf merges multiple occurrences of a singular message.
				var merged: PackedByteArray = singular_messages.get(field.name, PackedByteArray())
				merged.append_array(item)
				singular_messages[field.name] = merged
				continue
			var nested = _child()
			item = nested.decode(field.type, item, depth + 1)
			if not nested.error.is_empty():
				error = nested.error
				break
		if field.repeated:
			output[field.name].append(item)
			if output[field.name].size() > max_elements: error = "Protobuf collection limit"
		else: output[field.name] = item
	if error.is_empty():
		for field in fields.values():
			if not singular_messages.has(field.name): continue
			var nested = _child()
			output[field.name] = nested.decode(field.type, singular_messages[field.name], depth + 1)
			if not nested.error.is_empty():
				error = nested.error
				break
	return output if error.is_empty() else {}

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

func _read_varint(bytes: PackedByteArray) -> int:
	var value: int = 0
	for index in range(10):
		if _cursor >= bytes.size():
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
