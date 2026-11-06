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
            if position >= len(data):
                raise ValueError("Truncated varint")
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
            if position + size > len(data):
                raise ValueError("Truncated field")
            value = data[position:position + size]
            position += size
        else:
            raise ValueError(f"Unsupported wire {wire}")
        result.setdefault(tag >> 3, []).append(value)
    return result


def typed_value(encoded, value_type):
    """Null has explicit tag 5; omitted scalar values retain the column's type."""
    value = fields(encoded)
    if value.get(5, [0])[0]:
        return None
    if value_type == 1:
        return value.get(1, [b""])[0].decode()
    if value_type == 2:
        number = value.get(2, [0])[0]
        return number - 2**64 if number >= 2**63 else number
    if value_type == 3:
        return float(value.get(3, [0.0])[0])
    if value_type == 4:
        return bool(value.get(4, [0])[0])
    raise ValueError(f"Unknown column type {value_type}")


def copy_branch_documents():
    """Retain branch-owned localization and future-season static documents."""
    for name in ("ui_text.json", "season_templates.json", "season_transition_rules.json"):
        source = ROOT / "config" / name
        if source.exists():
            (ROOT / "client/data" / name).write_bytes(source.read_bytes())


def main():
    bundle = fields((ROOT / "server/config/generated/fantasycard.config.bytes").read_bytes())
    output = {"version": bundle[1][0].decode(), "tables": {}}
    for encoded in bundle[3]:
        table = fields(encoded)
        columns = [fields(item) for item in table[2]]
        names = [item[1][0].decode() for item in columns]
        types = [item[2][0] for item in columns]
        permitted = [item.get(4, [0])[0] in (1, 3) for item in columns]
        rows = []
        for encoded_row in table.get(3, []):
            encoded_values = fields(encoded_row).get(1, [])
            if len(encoded_values) != len(columns):
                raise ValueError("Config row width differs from its columns")
            values = [typed_value(value, kind) for value, kind in zip(encoded_values, types)]
            rows.append({name: value for name, value, allowed in zip(names, values, permitted) if allowed})
        if any(permitted):
            output["tables"][table[1][0].decode()] = rows
    target = ROOT / "client/data/catalog.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    # Compatibility output for historical tools. Author descriptions in the
    # same per-language packs used by the runtime.
    locale_root = ROOT / "client/data/locales"
    descriptions = {}
    for code in ("en", "zh-CN"):
        pack = json.loads((locale_root / (code + ".json")).read_text(encoding="utf-8"))
        descriptions["zh" if code == "zh-CN" else code] = pack.get("card_descriptions", {})
    (ROOT / "client/data/card_descriptions.json").write_text(json.dumps(descriptions, ensure_ascii=False), encoding="utf-8")
    copy_branch_documents()
    print({name: len(rows) for name, rows in output["tables"].items()})


if __name__ == "__main__":
    main()
