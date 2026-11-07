extends RefCounted

const MAX_BYTES := 2 * 1024 * 1024
const MAX_CELLS := 50000
var error := ""
var _cells := 0

class Reader:
	var data: PackedByteArray
	var position := 0
	var error := ""
	func _init(bytes: PackedByteArray) -> void:
		data = bytes
	func varint() -> int:
		var result := 0
		for index in 10:
			if position >= data.size():
				error = "Truncated config varint"
				return 0
			var value: int = data[position]
			position += 1
			if index == 9 and value > 1:
				error = "Config varint overflow"
				return 0
			result |= (value & 127) << (index * 7)
			if value < 128: return result
		error = "Invalid config varint"
		return 0
	func next() -> Dictionary:
		var start := position
		var tag := varint()
		var number := tag >> 3
		var wire := tag & 7
		var value: Variant
		if not error.is_empty() or number <= 0 or number > 536870911:
			error = "Invalid config field"
			return {}
		match wire:
			0: value = varint()
			1, 5:
				var size := 8 if wire == 1 else 4
				if size > data.size() - position:
					error = "Truncated config fixed field"
					return {}
				value = data.slice(position, position + size)
				position += size
			2:
				var size := varint()
				if not error.is_empty() or size < 0 or size > data.size() - position:
					error = "Truncated config message"
					return {}
				value = data.slice(position, position + size)
				position += size
			_:
				error = "Unsupported config wire type"
				return {}
		return {"number": number, "wire": wire, "value": value, "raw": data.slice(start, position)} if error.is_empty() else {}

func decode(bytes: PackedByteArray, expected_version: String, expected_hash: String) -> Dictionary:
	error = ""
	_cells = 0
	if bytes.is_empty() or bytes.size() > MAX_BYTES or expected_version.is_empty() or expected_hash.length() != 64:
		return _fail("Invalid config envelope")
	var reader := Reader.new(bytes)
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	var version := ""
	var embedded_hash := PackedByteArray()
	var tables := {}
	var seen_tables := {}
	while reader.position < bytes.size() and error.is_empty():
		var field := reader.next()
		if not reader.error.is_empty(): return _fail(reader.error)
		if field.number == 2:
			if field.wire != 2 or not embedded_hash.is_empty() or field.value.size() != 32: return _fail("Invalid config hash field")
			embedded_hash = field.value
		else:
			hash.update(field.raw)
			if field.number == 1:
				if not version.is_empty(): return _fail("Repeated config version")
				version = _text(field)
			elif field.number == 3:
				if field.wire != 2: return _fail("Invalid config table field")
				var table := _table(field.value)
				if not error.is_empty(): return {}
				if seen_tables.has(table.name): return _fail("Repeated config table")
				seen_tables[table.name] = true
				if table.published: tables[table.name] = table.rows
	if not error.is_empty(): return {}
	var digest := hash.finish()
	if version != expected_version or embedded_hash != digest or digest.hex_encode() != expected_hash.to_lower():
		return _fail("Config identity or content hash mismatch")
	for name in ["Cards", "CardLevels", "EquipmentQuality", "Backpacks", "LootRules", "Items"]:
		if not tables.has(name) or tables[name].is_empty(): return _fail("Missing required client config table")
	return {"version": version, "content_hash": digest.hex_encode(), "tables": tables}

func _table(bytes: PackedByteArray) -> Dictionary:
	var reader := Reader.new(bytes)
	var name := ""
	var columns: Array = []
	var encoded_rows: Array = []
	while reader.position < bytes.size() and error.is_empty():
		var field := reader.next()
		if not reader.error.is_empty(): return _fail(reader.error)
		match int(field.number):
			1:
				if not name.is_empty(): return _fail("Repeated table name")
				name = _text(field)
			2:
				if field.wire != 2 or columns.size() >= 128: return _fail("Config column limit or wire type")
				columns.append(_column(field.value))
			3:
				if field.wire != 2 or encoded_rows.size() >= 10000: return _fail("Config row limit or wire type")
				encoded_rows.append(field.value)
	if not error.is_empty(): return {}
	if name.is_empty() or columns.is_empty(): return _fail("Missing config table metadata")
	var names := {}
	var published := false
	for column in columns:
		if names.has(column.name): return _fail("Repeated config column")
		names[column.name] = true
		published = published or column.scope in [1, 3]
	var rows: Array = []
	var keys := {}
	for encoded in encoded_rows:
		var row_reader := Reader.new(encoded)
		var values: Array = []
		while row_reader.position < encoded.size() and error.is_empty():
			var field := row_reader.next()
			if not row_reader.error.is_empty(): return _fail(row_reader.error)
			if field.number != 1: continue
			if field.wire != 2 or values.size() >= columns.size(): return _fail("Invalid config row width")
			_cells += 1
			if _cells > MAX_CELLS: return _fail("Config cell limit")
			values.append(_value(field.value, columns[values.size()]))
		if not error.is_empty(): return {}
		if values.size() != columns.size() or values[0] == null or str(values[0]).is_empty(): return _fail("Missing config row key or value")
		var key := str(values[0])
		if keys.has(key): return _fail("Repeated config row key")
		keys[key] = true
		if not published: continue
		var row := {}
		for index in columns.size():
			# Older immutable bundles marked this visible gameplay price as Server.
			# Read its exact signed value; all other Server fields keep their scope.
			if columns[index].scope in [1, 3] or (name == "LootRules" and columns[index].name == "refresh_gold"):
				row[columns[index].name] = values[index]
		rows.append(row)
	return {"name": name, "published": published, "rows": rows}

func _column(bytes: PackedByteArray) -> Dictionary:
	var reader := Reader.new(bytes)
	var result := {"name": "", "type": 0, "required": false, "scope": 0}
	var seen := {}
	while reader.position < bytes.size() and error.is_empty():
		var field := reader.next()
		if not reader.error.is_empty(): return _fail(reader.error)
		if field.number not in [1, 2, 3, 4]: continue
		if seen.has(field.number): return _fail("Repeated column metadata")
		seen[field.number] = true
		if field.number == 1: result.name = _text(field)
		else:
			if field.wire != 0: return _fail("Invalid column metadata wire type")
			match int(field.number):
				2: result.type = int(field.value)
				3:
					if field.value not in [0, 1]: return _fail("Invalid required flag")
					result.required = bool(field.value)
				4: result.scope = int(field.value)
	if result.name.is_empty() or result.type not in [1, 2, 3, 4] or result.scope not in [1, 2, 3]: return _fail("Invalid column definition")
	return result

func _value(bytes: PackedByteArray, column: Dictionary) -> Variant:
	var defaults := {1: "", 2: 0, 3: 0.0, 4: false}
	var result: Variant = defaults[column.type]
	var seen := false
	var reader := Reader.new(bytes)
	while reader.position < bytes.size() and error.is_empty():
		var field := reader.next()
		if not reader.error.is_empty():
			_fail(reader.error)
			return null
		if field.number not in [1, 2, 3, 4, 5]: continue
		if seen:
			_fail("Repeated config value")
			return null
		seen = true
		if field.number == 5:
			if field.wire != 0 or field.value != 1:
				_fail("Invalid null config value")
			result = null
		elif field.number != column.type:
			_fail("Config value type mismatch")
		elif column.type == 1: result = _text(field)
		elif column.type == 3:
			if field.wire != 1:
				_fail("Invalid double config value")
				return null
			result = field.value.decode_double(0)
			if not is_finite(result): _fail("Nonfinite config value")
		else:
			if field.wire != 0 or column.type == 4 and field.value not in [0, 1]:
				_fail("Invalid scalar config value")
				return null
			result = bool(field.value) if column.type == 4 else int(field.value)
	if column.required and result == null: _fail("Required config value is missing")
	return result

func _text(field: Dictionary) -> String:
	if field.wire != 2:
		_fail("Invalid config text wire type")
		return ""
	var result: String = field.value.get_string_from_utf8()
	if result.to_utf8_buffer() != field.value: _fail("Invalid config UTF-8")
	return result

func _fail(reason: String) -> Dictionary:
	error = reason
	return {}
