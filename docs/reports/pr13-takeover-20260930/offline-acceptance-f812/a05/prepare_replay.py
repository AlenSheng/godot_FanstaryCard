"""Materialize declared test overlay in a fresh isolated f812 source directory.

No server is started and no tests are counted by this preparation helper.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

SOURCE = 'f812879e4518fd09bf22656451cb563d62940298'
CAUSAL = {
    'client/tests/pr13_a05_ack_poll_causal.gd',
    'server/tests/FantasyCard.Server.Tests/EndToEnd/ProcessLifecycleA05AckPollCausalTests.cs',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--causal', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    packet = Path(__file__).resolve().parent
    proof = json.loads((packet / 'source-final.json').read_text())
    for entry in proof['harness_files']:
        data = (packet / 'harness' / entry['path']).read_bytes()
        assert len(data) == entry['bytes']
        assert hashlib.sha256(data).hexdigest() == entry['sha256'], entry['path']
    archive = subprocess.Popen(['git', '-C', str(args.repo.resolve()), 'archive', SOURCE], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=archive.stdout, mode='r|') as stream:
            stream.extractall(args.output, filter='data')
    finally:
        archive.stdout.close()
    if archive.wait() != 0:
        raise RuntimeError('Fixed-source archive failed; retain the partial directory for diagnosis.')
    # Only the newly materialized private copy is cleaned. Original source/raw is untouched.
    for parent, dirs, _ in os.walk(args.output):
        for name in list(dirs):
            if name in {'bin', 'obj', '.godot', '__pycache__'}:
                shutil.rmtree(Path(parent) / name)
                dirs.remove(name)
    included = []
    for entry in proof['harness_files']:
        if not args.causal and entry['path'] in CAUSAL:
            continue
        dst = args.output / entry['path']
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(packet / 'harness' / entry['path'], dst)
        included.append(entry)
    record = dict(production_sha=SOURCE, harness_files=included,
                  intentionally_red_causal_test_included=args.causal,
                  source_git_dirty=None,
                  missing_reasons={'source_git_dirty': 'Git archive plus declared isolated harness overlay; no .git.'},
                  tests_executed=0, production_patch_applied=False)
    (args.output / 'A05_REPLAY_SOURCE.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(dict(source_sha=SOURCE, harness_files=len(included), output=str(args.output), tests_executed=0)))


if __name__ == '__main__':
    main()
