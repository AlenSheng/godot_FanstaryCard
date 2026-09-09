"""Read the published config bundle; export only Both/Client columns."""
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def fields(data):
    position = 0

    def varint():
        nonlocal position
        value = 0
        for shift in range(0, 70, 7):
            byte = data[position]
            position += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError("Invalid varint")

    result = {}
    while position < len(data):
        tag = varint()
        wire = tag & 7
        if wire == 0:
            value = varint()
        elif wire == 1:
            value = struct.unpack_from("<d", data, position)[0]
            position += 8
        elif wire == 2:
            size = varint()
            value = data[position:position + size]
            position += size
        else:
            raise ValueError(f"Unsupported wire {wire}")
        result.setdefault(tag >> 3, []).append(value)
    return result


bundle = fields((ROOT / "server/config/generated/fantasycard.config.bytes").read_bytes())
output = {"version": bundle[1][0].decode(), "tables": {}}
for encoded in bundle[3]:
    table = fields(encoded)
    columns = [fields(item) for item in table[2]]
    names = [item[1][0].decode() for item in columns]
    permitted = [item.get(4, [0])[0] in (1, 3) for item in columns]
    rows = []
    for encoded_row in table.get(3, []):
        values = []
        for encoded_value in fields(encoded_row).get(1, []):
            value = fields(encoded_value)
            if 1 in value: parsed = value[1][0].decode()
            elif 2 in value:
                parsed = value[2][0]
                if parsed >= 2**63: parsed -= 2**64
            elif 3 in value: parsed = value[3][0]
            elif 4 in value: parsed = bool(value[4][0])
            else: parsed = None
            values.append(parsed)
        rows.append({name: value for name, value, allowed in zip(names, values, permitted) if allowed})
    if any(permitted): output["tables"][table[1][0].decode()] = rows
target = ROOT / "client/data/catalog.json"
target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
descriptions = json.loads((ROOT / "config/card_descriptions.json").read_text(encoding="utf-8"))
(ROOT / "client/data/card_descriptions.json").write_text(json.dumps(descriptions, ensure_ascii=False), encoding="utf-8")
print({name: len(rows) for name, rows in output["tables"].items()})
