"""Archive only the explicit immutable evidence manifest, never the output tree."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
try:
    from pr13_public_evidence import validated_files, inspect_public
except ModuleNotFoundError:
    from tools.pr13_public_evidence import validated_files, inspect_public

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--register',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();manifest=json.loads((args.register/'manifest.json').read_text(encoding='utf8'))
    files=validated_files(ROOT,manifest['files'])
    files+=list(args.register.glob('*.json'))+list(args.register.glob('*.jsonl'))+list(args.register.glob('*.md'))
    files=sorted(set(path.resolve() for path in files));args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists():raise ValueError('Use a new evidence bundle name')
    for path in files: inspect_public(path)
    with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files:archive.write(path,path.relative_to(ROOT).as_posix())
    descriptor=dict(source_sha=manifest['source_sha'],path=str(args.output),files=len(files),bytes=args.output.stat().st_size,
        sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),scope='Explicit manifest only; no DB clusters, credentials, runtime binaries or private snapshot.')
    args.output.with_suffix('.json').write_text(json.dumps(descriptor,indent=2),encoding='utf8');print(json.dumps(descriptor));return 0


if __name__=='__main__':raise SystemExit(main())
