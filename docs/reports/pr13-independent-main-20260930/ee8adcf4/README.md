# LOAD-01 independent MAIN OFFLINE evidence at ee8adcf4

This small S6 evidence packet preserves the independent review performed against
`ee8adcf40be9aebb1330156a3524910c08225ebc`. It contains the review/report,
recorded commands and exits, original 12-case observations, full 119-test log,
old five-case red/green observations, and three minimal synthetic schema
counterexamples with actual inputs, tracebacks and owned-child cleanup evidence.
It does not include the original 255-file local evidence archive.

The parent MAIN explicitly adopted these results after the review:

| Task | Parent adjudication at the fixed SHA |
| --- | --- |
| LOAD-01.1 | Failed; the three new schema exceptions require owner repair and independent replay. |
| LOAD-01.2 | Original OFFLINE contract satisfied; Accepted/NoChangeWithEvidence. |
| LOAD-01.3 | Original OFFLINE contract satisfied; Accepted/NoChangeWithEvidence. |
| LOAD-01.4 | Original OFFLINE contract satisfied; Accepted/NoChangeWithEvidence. |

[PARENT_DECISION_NOTE.json](PARENT_DECISION_NOTE.json) records the supplied parent
statement. It is an evidence note, not a change to the original task register.
The decision applies only to these four contracts at the tested SHA. It does not
extend to later source versions, complete coordinator schema safety, or other tasks.

[REVIEW.md](REVIEW.md) and [REPORT.json](REPORT.json) are byte-identical snapshots
created before the parent decision. Their pending-parent flags, original local
paths and local-only-delivery statements are historical. The original local
manifest covered 255 files; [MANIFEST.json](MANIFEST.json) here covers only this
published subset. [PUBLICATION.json](PUBLICATION.json) preserves the original
snapshot hashes, full-local-manifest hash, and the publication boundary.

## Results and reproducibility

- Original canonical cases: 12/12 passed, zero skips.
- Original Python suite: 119/119 passed, zero skips, exit0.
- Old five schema cases: five actual exceptions before the repair; zero after,
  with five explicit invalid-evidence classifications of exit3.
- New finite-overflow, archive-match-list and archive-type-list probes: each
  independently exited1 with an uncaught production helper-path exception.
- Nineteen dedicated owned children were reaped; normal finite/archive controls
  completed without exceptions. No test server was contacted.

[COMMANDS.json](COMMANDS.json) records exact argv, source SHA, cwd, Python/platform,
exit codes and log hashes. A schema harness exit0 means it recorded observations;
it does not mean load acceptance passed. The new probe exit1 is the actual
independent probe-process result, not a claim that the full network CLI ran.

The three minimal inputs and tracebacks are under
[counterexamples/](counterexamples/). [probe_schema.py](probe_schema.py) invokes
the unmodified production reader, event reducer, aggregator and reconciliation
functions after a real owned child writes those files. It does not patch the
implementation or change the original tests/assertions.

To reproduce with Python 3.12, first create a new detached worktree at the exact
tested SHA. Let `source_checkout` below be that worktree's absolute path, and
`review_packet` this packet's absolute path. The output directory for every run
must be new. These commands are instructions, not newly executed tests during
publication:

```bash
git worktree add --detach /tmp/pr13-ee8adcf4-replay ee8adcf40be9aebb1330156a3524910c08225ebc
source_checkout=/tmp/pr13-ee8adcf4-replay
review_packet="$PWD/docs/reports/pr13-independent-main-20260930/ee8adcf4"
PYTHONDONTWRITEBYTECODE=1 python3 "$review_packet/probe_schema.py" --source "$source_checkout" --fixture finite-overflow --output /tmp/pr13-finite-mean-replay
PYTHONDONTWRITEBYTECODE=1 python3 "$review_packet/probe_schema.py" --source "$source_checkout" --fixture archive-match-list --output /tmp/pr13-archive-match-replay
PYTHONDONTWRITEBYTECODE=1 python3 "$review_packet/probe_schema.py" --source "$source_checkout" --fixture archive-type-list --output /tmp/pr13-archive-type-replay
```

All three probes reproduce exceptions at this fixed SHA. Their finally blocks
reap the synthetic status writers and preserve `receipt.json`; stderr gives the
full traceback. Owner repairs must classify malformed fields or aggregate finite
inputs safely, retaining known failure denominators. Swallowing probe exceptions
is not a repair.

The original canonical and old five-case harnesses are already preserved in the
base receipt commit `d9f957cbd5ae4a1145ebc4d701baddfe8211708c` at
`docs/reports/pr13-takeover-20260930/schema-safety-ee8adcf4/`. Obtain those two
scripts from that immutable commit and follow its README against the exact tested
SHA. The old receipt was
`3c9aaa96fdef4a0a0c0fc1b5e99c4faaefcdeb84`; [STATIC_CHECK.json](STATIC_CHECK.json)
records verified 67 old manifest entries, ten source hashes, twelve final raw
files, 75 new manifest entries, and complete report/stage metadata.

## Publication boundary and integrity

Only this new report directory is added to the independent review branch based
on the immutable receipt commit. The original PR13, tested source, assertions,
and Accepted register are unchanged. This publication runs no tests, creates no
PR, dispatches no workflow, uploads nothing to Library, and contains only
synthetic local inputs and non-sensitive review text. No account credentials or
private test-server data are included.

The six workflow trigger definitions in the base commit have no matching push
branch for `review/pr13-load01-main-offline-ee8adcf4-20260930`; the documentation
commit also carries `[skip ci]`.

To verify the small packet's file sizes and SHA256 hashes:

```bash
python3 - "$review_packet" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
manifest = json.loads((root / 'MANIFEST.json').read_text())
for row in manifest['files']:
    data = (root / row['path']).read_bytes()
    assert len(data) == row['bytes'], row['path']
    assert hashlib.sha256(data).hexdigest() == row['sha256'], row['path']
print('verified', len(manifest['files']), 'files')
PY
```
