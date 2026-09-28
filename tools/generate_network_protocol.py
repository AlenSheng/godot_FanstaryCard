"""Reproducible Godot schemas and HTTP route registry. No external Python packages.
The .proto files are authoritative; C# uses pinned protoc via Grpc.Tools.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCALARS = {'string', 'bytes', 'int32', 'int64', 'uint32', 'bool'}

def schema(path):
    raw = path.read_text(encoding='utf-8')
    text = re.sub(r'//[^\n]*', '', raw)
    messages = {}
    for name, body in re.findall(r'message\s+(\w+)\s*\{([^}]*?)\}', text, re.S):
        fields = {}
        matches = list(re.finditer(r'\b(?:(repeated|optional)\s+)?(\w+)\s+(\w+)\s*=\s*(\d+)\s*;', body))
        remainder = body
        for m in reversed(matches): remainder = remainder[:m.start()] + remainder[m.end():]
        if remainder.strip(): raise ValueError(f'Unsupported proto syntax: {name}: {remainder}')
        for m in matches:
            mode, kind, field, number = m.groups()
            if number in fields: raise ValueError(f'Duplicate tag {name}.{number}')
            fields[number] = {'name': field, 'type': kind, 'repeated': mode == 'repeated', 'optional': mode == 'optional'}
        messages[name] = fields
    for name, fields in messages.items():
        for field in fields.values():
            if field['type'] not in SCALARS and field['type'] not in messages: raise ValueError(f'Unknown type {name}.{field}')
    return {'sha256': hashlib.sha256(raw.encode()).hexdigest(), 'messages': messages}

def generate(check=False):
    realtime = schema(ROOT / 'protocol/realtime/v1/realtime.proto')
    http = schema(ROOT / 'protocol/http/v1/game.proto')
    registry = json.loads((ROOT / 'protocol/http/v1/endpoints.json').read_text())
    seen = set()
    for route in registry['endpoints']:
        key = (route['method'],route['path'])
        assert key not in seen, key
        seen.add(key)
        assert route['request'] in http['messages'], route
        assert route['response'] in http['messages'], route
    outputs = {'client/data/realtime_schema.json':realtime, 'client/data/http_schema.json':http, 'client/data/http_endpoints.json':registry}
    failed = []
    for name, value in outputs.items():
        path = ROOT / name
        content = json.dumps(value, indent=2) + '\n'
        if check:
            if not path.exists() or path.read_text(encoding='utf-8') != content: failed.append(name)
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content,encoding='utf-8')
    if failed: raise SystemExit('Stale generated files: '+', '.join(failed))
    print(f'{"Checked" if check else "Generated"} {len(realtime["messages"])} realtime + {len(http["messages"])} HTTP messages; {len(seen)} routes')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true')
    generate(parser.parse_args().check)
