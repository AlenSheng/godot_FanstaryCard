# LOAD01 schema correction and independent replay

Fixed runtime/validation SHA: `ee8adcf40be9aebb1330156a3524910c08225ebc`. Business, client, protocol and UI remain byte-identical to f812879e. This packet supersedes the original LOAD01 proposal; LOAD01.1 is a fix proposal, not NoChange.

Actual f812 status-file reader -> new_events -> aggregate_window/workload_snapshot: two TypeError and three OverflowError. All five children reaped. Same path at clean fixed SHA: five explicit invalid-evidence exit3 decisions, no unhandled exception. Original12 cases and full Python119 pass, zero skips. No Accepted signature.

Use a clean checkout of the fixed SHA and Python3.12. Obtain the two scripts from this receipt commit (for example `git show <receipt-commit>:docs/reports/pr13-takeover-20260930/schema-safety-ee8adcf4/reproduce.py > /tmp/pr13-schema.py`).

```bash
python -m unittest discover -s tools/tests -p test_gameplay_load_validation.py -v
PYTHONDONTWRITEBYTECODE=1 python /tmp/pr13-schema.py --source "$PWD" --output /tmp/pr13-schema-independent-new
PR13_SOURCE_ROOT="$PWD" PYTHONDONTWRITEBYTECODE=1 python /tmp/pr13-load01.py --output /tmp/pr13-load01-independent-new
```

The second LOAD01 script is `run_load01_acceptance.py` in this packet. Output directories must be new. Schema harness process exit0 means the probe recorded results; inspect REPORT.json for `unhandled_exceptions=0`, `invalid_failures=5`, `all_reaped=true` and each decision exit3. It is not a load Passed flag. The LOAD01 script itself exits0 only for12/12. No public endpoint, credentials, database, CI or LIVE prerequisite.

Equivalent numeric guard in final archived event reconciliation and sampling integrity is included; real owned huge-event-time JSONL reproduces the extra OverflowError before and explicit invalid exit3 after.
