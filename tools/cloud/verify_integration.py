"""Verify the candidate is exactly two frozen inputs plus review-only additions."""
import argparse
import json
from pathlib import Path
import subprocess

SOURCE = 'cc6da2e7b8a2c7ba46d867af74ce28a58ccfeac3'
CONTROLLER = '262390134e98f169899d076e6fa21926d44ba1aa'
BASE = '28c6c7e7d3898e4d2abd186f53361477ba380330'
ADDITIONS = {'.github/workflows/integration-image-check.yml',
             'tools/cloud/verify_integration.py'}
REVIEW = 'docs/reports/cloud-frozen-cc6da2e-20260930/'


def git(*args):
    return subprocess.check_output(['git', *args])


def tree(ref):
    result = {}
    for entry in git('ls-tree', '-rz', '--full-tree', ref).split(b'\0'):
        if entry:
            metadata, path = entry.split(b'\t', 1)
            result[path.decode('utf-8')] = metadata.decode('ascii')
    return result


def verify(ref):
    if git('merge-base', SOURCE, CONTROLLER).decode().strip() != BASE:
        raise ValueError('Frozen inputs no longer share the recorded base')
    base, controller, expected, actual = map(tree, (BASE, CONTROLLER, SOURCE, ref))
    delta = {p for p in set(base) | set(controller) if base.get(p) != controller.get(p)}
    if len(delta) != 25 or any(p in base or p in expected for p in delta):
        raise ValueError('Expected the exact 25 non-overlapping PR14 additions')
    expected.update({p: controller[p] for p in delta})
    unexpected = [p for p in set(expected) | set(actual)
                  if p not in ADDITIONS and not p.startswith(REVIEW)
                  and expected.get(p) != actual.get(p)]
    if unexpected:
        raise ValueError('Candidate differs from frozen composition: ' + ', '.join(sorted(unexpected)))
    if not all(p in actual for p in ADDITIONS):
        raise ValueError('Independent verification entry missing')
    return {'ok': True, 'candidate': git('rev-parse', ref).decode().strip(),
            'source_pr13_sha': SOURCE, 'controller_pr14_sha': CONTROLLER,
            'common_base_sha': BASE, 'controller_delta_paths': sorted(delta),
            'source_and_controller_blobs_and_modes_exact': True,
            'review_only_additions': sorted(set(actual) - set(expected))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tree', default='HEAD')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    proof = verify(args.tree)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof, indent=2))
