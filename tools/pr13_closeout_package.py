"""Package the committed source and closed PR13 evidence with per-file hashes."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PARTS = {'postgres', 'runtime', 'bin', 'obj', '.git', '.godot', '.packages', '__pycache__'}
PRIVATE_SUFFIXES = {'.pem', '.key', '.dpapi', '.pfx', '.p12', '.dump'}
SECRET = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}|eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}')


def forbidden(relative):
    path = Path(relative)
    return (bool(set(path.parts) & PRIVATE_PARTS) or path.suffix.lower() in PRIVATE_SUFFIXES
            or (path.name.startswith('.env') and path.name not in {'.env.example', '.env.template', '.env.sample'})
            or 'snapshot-private' in path.name)


def copy_entry(archive, name, stream, records, exclusions):
    tail = b''
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk: break
        if SECRET.search(tail + chunk):
            exclusions.append(dict(path=name, reason='Embedded private credential; retained locally only'))
            return
        tail = chunk[-4096:]
    stream.seek(0)
    digest = hashlib.sha256(); size = 0
    with archive.open(name, 'w', force_zip64=True) as target:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk: break
            digest.update(chunk); size += len(chunk); target.write(chunk)
    records.append(dict(path=name, bytes=size, sha256=digest.hexdigest()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve(); evidence.relative_to(ROOT)
    output = args.output.resolve(); output.relative_to(ROOT)
    if output.exists(): raise ValueError('Use a fresh closeout archive name')
    if subprocess.check_output(['git', 'status', '--porcelain', '-uno'], cwd=ROOT).strip():
        raise ValueError('Commit or restore tracked changes before packaging')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    output.parent.mkdir(parents=True, exist_ok=True)
    source_zip = output.parent / 'source-git.zip'
    subprocess.run(['git', 'archive', '--format=zip', '--output=' + str(source_zip), head], cwd=ROOT, check=True)
    records = []; exclusions = []
    files = sorted(path for path in evidence.rglob('*') if path.is_file())
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        with zipfile.ZipFile(source_zip) as source:
            for item in source.infolist():
                if item.is_dir(): continue
                if forbidden(item.filename) or item.filename.startswith('outputs/'):
                    exclusions.append('source/' + item.filename); continue
                with source.open(item) as stream: copy_entry(archive, 'source/' + item.filename, stream, records, exclusions)
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            if (forbidden(relative) or path.is_relative_to(output.parent)
                    or path.suffix.lower() == '.zip' or path.name.startswith('evidence-bundle-')
                    or path.name.startswith('upload-')):
                exclusions.append(relative); continue
            with path.open('rb') as stream: copy_entry(archive, relative, stream, records, exclusions)
        for name, command in (
            ('CHANGES_FROM_RELEASE.patch', ['git', 'diff', '--binary', '28c6c7e7d3898e4d2abd186f53361477ba380330', head]),
            ('COMMIT_LOG.txt', ['git', 'log', '--format=%H %s', '28c6c7e7d3898e4d2abd186f53361477ba380330..' + head])):
            copy_entry(archive, name, io.BytesIO(subprocess.check_output(command, cwd=ROOT)), records, exclusions)
        manifest = dict(schema_version=1, created_at=time.time(), source_sha=head,
            release_base='28c6c7e7d3898e4d2abd186f53361477ba380330',
            scope='Committed source and all retained non-private PR13 execution artifacts; incomplete and superseded runs remain labelled.',
            candidate_activation=False, all_accepted=False, files=records, excluded=exclusions)
        archive.writestr('PACKAGE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr('README.txt', 'PR13 session closed by user request. Start with source/docs/reports/pr13-execution-20260930/CLOSEOUT.md and TASK_CHECKLIST.md.\n'
            'The 396-case specification is unchanged; unexecuted cases are not accepted.\n'
            'SOURCE_SHA: ' + head + '\n'
            'Runtime caches, local database clusters, credentials and private snapshots are excluded.\n')
    with zipfile.ZipFile(output) as archive:
        corrupt = archive.testzip()
        if corrupt: raise ValueError('ZIP integrity failed: ' + corrupt)
        for entry in records:
            digest = hashlib.sha256()
            with archive.open(entry['path']) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''): digest.update(chunk)
            if digest.hexdigest() != entry['sha256']: raise ValueError('Archived hash mismatch: ' + entry['path'])
    descriptor = dict(source_sha=head, path=str(output), files=len(records), bytes=output.stat().st_size,
        sha256=hashlib.sha256(output.read_bytes()).hexdigest(), zip_integrity='Passed',
        per_file_hash_verification='Passed', excluded_files=len(exclusions), all_accepted=False)
    output.with_suffix('.json').write_text(json.dumps(descriptor, indent=2), encoding='utf8')
    output.with_suffix('.sha256').write_text(descriptor['sha256'] + '  ' + output.name + '\n', encoding='ascii')
    print(json.dumps(descriptor))
    return 0


if __name__ == '__main__': raise SystemExit(main())
