extends RefCounted

const SCHEMA = preload("res://data/realtime_schema.json")
var error: String = ""
var _cursor: int = 0

func encode(message: String, value: Dictionary) -> PackedByteArray:
	var output := PackedByteArray()
	for number in SCHEMA.data.messages.get(message, {}):
		var field: Dictionary = SCHEMA.data.messages[message][number]
		if not value.has(field.name):
			continue
		var values: Array = value[field.name] if field.repeated else [value[field.name]]
		for item in values:
			var kind: String = field.type
			if kind in ["int32", "int64", "uint32", "bool"]:
				output.append_array(_varint(int(number) << 3))
				output.append_array(_varint(int(item)))
			else:
				var body: PackedByteArray
				if kind == "string":
					body = str(item).to_utf8_buffer()
				elif kind == "bytes":
					body = item
				else:
					body = encode(kind, item)
				output.append_array(_varint((int(number) << 3) | 2))
				output.append_array(_varint(body.size()))
				output.append_array(body)
	return output

func decode(message: String, bytes: PackedByteArray, depth: int = 0) -> Dictionary:
	error = ""
	_cursor = 0
	if bytes.size() > 16384 or depth > 24:
		error = "Protobuf size/depth limit"
		return {}
	var fields: Dictionary = SCHEMA.data.messages.get(message, {})
	var output: Dictionary = {}
	for field in fields.values():
		if field.repeated:
			output[field.name] = []
		elif not field.optional:
			if field.type == "string": output[field.name] = ""
			elif field.type == "bytes": output[field.name] = PackedByteArray()
			elif field.type == "bool": output[field.name] = false
			elif field.type in ["int32", "int64", "uint32"]: output[field.name] = 0
	while _cursor < bytes.size() and error.is_empty():
		var tag: int = _read_varint(bytes)
		var number := tag >> 3
		var wire := tag & 7
		if number <= 0:
			error = "Invalid field tag"
			break
		var item: Variant
		match wire:
			0: item = _read_varint(bytes)
			1, 5:
				_cursor += 8 if wire == 1 else 4
			2:
				var size := _read_varint(bytes)
				if size < 0 or size > bytes.size() - _cursor:
					error = "Truncated field"
					break
				item = bytes.slice(_cursor, _cursor + size)
				_cursor += size
			_:
				error = "Unsupported wire type"
		if _cursor > bytes.size(): error = "Truncated fixed field"
		if not error.is_empty(): break
		if not fields.has(str(number)): continue
		var field: Dictionary = fields[str(number)]
		var scalar: bool = field.type in ["int32", "int64", "uint32", "bool"]
		if wire != (0 if scalar else 2):
			error = "Unexpected wire type"
			break
		if field.type == "string": item = item.get_string_from_utf8()
		elif field.type == "bool": item = item != 0
		elif not scalar and field.type != "bytes":
			var nested = get_script().new()
			item = nested.decode(field.type, item, depth + 1)
			if not nested.error.is_empty():
				error = nested.error
				break
		if field.repeated: output[field.name].append(item)
		else: output[field.name] = item
	return output if error.is_empty() else {}

func _varint(value: int) -> PackedByteArray:
	var bytes := PackedByteArray()
	# Negative int64 uses the standard ten-byte two's-complement representation.
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
