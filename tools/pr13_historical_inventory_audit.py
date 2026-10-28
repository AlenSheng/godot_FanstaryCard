"""Classify every declared historical file without repairing or rewriting originals."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def inventory(manifest, root):
    require(manifest.is_file() and not manifest.is_symlink(), 'Original manifest missing or linked')
    before = sha(manifest)
    data = json.loads(manifest.read_bytes())
    rows = data['files']
    require(isinstance(rows, list) and rows, 'Original manifest is empty')
    result = []
    seen = set()
    root = root.absolute()
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get('path'), str) and row['path'],
                'Historical member has no valid path')
        name = row['path']
        p = PurePosixPath(name)
        require(isinstance(name, str) and name and not p.is_absolute()
                and '..' not in p.parts and '\\' not in name and ':' not in name
                and p.as_posix() == name and name not in seen, 'Unsafe or duplicate historical member')
        seen.add(name)
        target = root.joinpath(*p.parts)
        require(type(row['bytes']) is int and row['bytes'] >= 0
                and isinstance(row['sha256'], str) and re.fullmatch('[0-9a-f]{64}', row['sha256']),
                'Original member has invalid size or hash')
        value = {'path': name, 'expected_bytes': row['bytes'], 'expected_sha256': row['sha256']}
        parent_link = any(parent.is_symlink() for parent in (target, *target.parents)
                          if parent == root or parent.is_relative_to(root))
        if parent_link:
            value.update(state='UnsafeTypeQuarantined', raw_read=False)
        elif not target.exists():
            value.update(state='Missing', raw_read=False)
        elif not target.is_file():
            value.update(state='UnsafeTypeQuarantined', raw_read=False)
        else:
            require(target.resolve(strict=True).is_relative_to(root.resolve(strict=True)),
                    'Historical member escaped declared root')
            stat = target.stat()
            actual = sha(target)
            after = target.stat()
            require((stat.st_size, stat.st_mtime_ns, stat.st_ino) == (after.st_size, after.st_mtime_ns, after.st_ino),
                    'Original changed during inventory')
            value.update(actual_bytes=stat.st_size, actual_sha256=actual, raw_read=True,
                         state='Matched' if stat.st_size == row['bytes'] and actual == row['sha256']
                         else 'HashOrSizeMismatchQuarantined')
        result.append(value)
    require(sha(manifest) == before, 'Original manifest changed')
    counts = dict(Counter(row['state'] for row in result))
    return {'schema_version': 1, 'manifest_sha256': before, 'declared_root': str(root),
            'declared_members': len(rows), 'counts': counts, 'files': result,
            'all_declared_members_classified': len(result) == len(rows),
            'all_raw_available_and_matching': counts.get('Matched', 0) == len(rows),
            'original_manifest_and_raw_not_modified': True,
            'historical_totals_reconciled': False,
            'missing_raw_cannot_be_replaced_by_newer_results': True,
            'MAIN_accepted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Preserve previous inventory output')
    value = inventory(args.manifest, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'all_members_classified': True, 'members': value['declared_members'],
                      'counts': value['counts'], 'historical_totals_reconciled': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
