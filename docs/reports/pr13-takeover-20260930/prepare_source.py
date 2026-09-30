"""Prepare a fresh fixed commit archive and remove only its generated caches."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.sha):
        parser.error('--sha requires the complete fixed commit hash')
    repo = args.repo.resolve()
    actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', args.sha + '^{commit}'], text=True).strip()
    assert actual == args.sha
    args.output.mkdir(parents=True, exist_ok=False)
    archive = subprocess.Popen(['git', '-C', str(repo), 'archive', args.sha], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=archive.stdout, mode='r|') as stream:
            stream.extractall(args.output, filter='data')
    finally:
        archive.stdout.close()
    if archive.wait() != 0:
        raise RuntimeError('Fixed-source archive failed; retain partial output for diagnosis')
    removed = []
    for parent, dirs, _ in os.walk(args.output):
        for name in list(dirs):
            if name in {'bin','obj','.godot','__pycache__'}:
                p = Path(parent) / name
                removed.append(str(p.relative_to(args.output)))
                shutil.rmtree(p)
                dirs.remove(name)
    (args.output / 'REPLAY_SOURCE.json').write_text(json.dumps(dict(source_sha=args.sha,
        generated_cache_directories_removed=removed, source_git_dirty=None,
        missing_reasons={'source_git_dirty':'Fixed git archive; no .git; no source/test overlay.'},
        tests_executed=0), indent=2) + '\n')
    print(json.dumps(dict(source_sha=args.sha, output=str(args.output), tests_executed=0)))


if __name__ == '__main__':
    main()
