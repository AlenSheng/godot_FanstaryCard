"""Archive only explicit immutable public evidence snapshots, never an output tree."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
try:
    from pr13_public_evidence import MAX_TOTAL_BYTES, TEXT_SUFFIXES, public_payload, validated_payloads
except ModuleNotFoundError:
    from tools.pr13_public_evidence import MAX_TOTAL_BYTES, TEXT_SUFFIXES, public_payload, validated_payloads

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--register', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = ROOT.resolve()
    register = args.register.resolve()
    if not register.is_relative_to(root):
        raise ValueError('Public register escapes root')
    manifest_path = register / 'manifest.json'
    manifest_payload = public_payload(manifest_path)
    manifest = json.loads(manifest_payload.decode('utf-8-sig'))
    source_sha = manifest.get('source_sha')
    if not isinstance(source_sha, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', source_sha):
        raise ValueError('Exact source SHA required before evidence archive write')
    payloads = dict(validated_payloads(root, manifest['files']))
    if manifest_path in payloads and payloads[manifest_path] != manifest_payload:
        raise ValueError('Public manifest changed while capturing snapshots')
    payloads[manifest_path] = manifest_payload
    for path in sorted(set(register.glob('*.json')) | set(register.glob('*.jsonl')) | set(register.glob('*.md'))):
        path = path.resolve()
        if not path.is_relative_to(root):
            raise ValueError('Public metadata path escapes root')
        if path not in payloads:
            payloads[path] = public_payload(path)
    if any(path.suffix.lower() not in TEXT_SUFFIXES for path in payloads):
        raise ValueError('Uninspected artifact type in public evidence bundle')
    if len(payloads) > 4096 or sum(map(len, payloads.values())) > MAX_TOTAL_BYTES:
        raise ValueError('Public evidence snapshots exceed bounded size')
    if args.output.exists():
        raise ValueError('Use a new evidence bundle name')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, payload in sorted(payloads.items()):
            archive.writestr(path.relative_to(root).as_posix(), payload)
    descriptor = dict(source_sha=source_sha, path=str(args.output), files=len(payloads),
                      bytes=args.output.stat().st_size,
                      sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      scope='Explicit validated immutable snapshots; no source-path reread or private runtime tree.')
    args.output.with_suffix('.json').write_text(json.dumps(descriptor, indent=2), encoding='utf8')
    print(json.dumps(descriptor))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
