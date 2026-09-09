"""Generate data-only Godot wire metadata from the checked-in proto3 contract."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "protocol/realtime/v1/realtime.proto"
raw = source.read_text(encoding="utf-8")
text = re.sub(r"//[^\n]*", "", raw)
messages = {}
for name, body in re.findall(r"message\s+(\w+)\s*\{([^}]*?)\}", text, re.S):
    fields = {}
    for mode, kind, field, number in re.findall(
        r"\b(?:(repeated|optional)\s+)?(\w+)\s+(\w+)\s*=\s*(\d+)\s*;", body
    ):
        fields[number] = {"name": field, "type": kind, "repeated": mode == "repeated", "optional": mode == "optional"}
    messages[name] = fields
assert len(messages) >= 50
target = ROOT / "client/data/realtime_schema.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({"sha256": hashlib.sha256(raw.encode()).hexdigest(), "messages": messages}, indent=2), encoding="utf-8")
print(f"Generated {len(messages)} messages: {target}")
