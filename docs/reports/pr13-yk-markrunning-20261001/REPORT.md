# YK local MarkRunning fault-proxy correction — 2026-10-01

## Preserved first failure

Source `397673a93156430aff9d81479f5101cb0aaaf52f`, Numerical full acceptance [36877052760](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36877052760), attempt 1: Server **301 passed / 1 failed / 0 skipped**. `MarkRunning_commit_response_loss_retries_same_room_and_restart_restores_it` failed at the original line 75: expected `Running`, actual `Launching`. The later same-room retry and restart assertions were not reached. Three other workflows succeeded; they do not cover this failure.

The assertion failed at 14:42:17 UTC, before the separate 25-minute job cancellation. Job duration was 25m01s; checkout took about 7m34s (fetch about 7m18s), and the recorded Server suite took 15m19s. The raw archive was successfully uploaded despite cancellation: artifact `11171736048`, **3,573,309 bytes**, SHA256 `e3d79efbed74032ecfb02521586fdbeb45fe76d2a47fd5d24e3f8b31c61268f2`. It remains archived locally with the original TRX and annotations. No rerun replaces attempt 1.

## Controlled red, then green

The old proxy armed when it saw target Parse/Query, before forwarding that frame, and treated the next idle ReadyForQuery as proof of target commit. It neither correlated request/response cycles nor checked CommandComplete.

A real PostgreSQL counterexample holds the target Parse while sending a real `SELECT 1` probe. The original pooled connection already has a queued reset. The old proxy trace is exactly:

```json
["target-seen-not-forwarded","prior-idle-probe-Q-forwarded","C:DISCARD ALL","first-Z:I"]
```

It falsely reports committed response loss without forwarding the target. The original database assertion fails at `Launching`: **1 passed / 1 failed / 0 skipped**. This controlled red uses base `397673a` plus the archived test seam, not a clean commit. Red source SHA256: `72538528fc164b5451a6462af315ff044f5e93070fccb4b502494f6530c41117`; test assembly SHA256: `4e6d4923928821b7b580244c2d3eb42ef2fab615b12d999c45a252ec6e7be56f`.

The correction associates startup, simple Query, and extended Query/Sync cycles in FIFO order. It forwards preceding reset responses normally. It buffers only the selected target cycle and drops it only after that cycle has exactly `UPDATE 1` (or the selected settlement `COMMIT`), no ErrorResponse, and idle ReadyForQuery. Unexpected database results remain visible rather than being called committed. A per-connection cancellation token also releases the controlled probe gate when a connection closes.

The original natural case remains, with one added controlled prior-idle case. Every original Running, same-room retry, restart, inventory and terminal-match assertion remains. Both **Unix 9/0/0** and **TCP 9/0/0** lifecycle recovery suites passed, including settlement COMMIT-loss recovery. Traces identify connection/cycle, CommandComplete tag, target/probe and idle completion; they contain no SQL parameters or authentication frames.

[Npgsql's pooled reset documentation](https://www.npgsql.org/doc/performance.html#pooled-connection-reset) describes reset commands being buffered together with the first reused user command. [PostgreSQL's protocol documentation](https://www.postgresql.org/docs/18/protocol-flow.html) defines Query/Sync cycle completion. The controlled red proves the old proxy defect; the old CI did not save protocol frames, so its exact historical interleaving cannot be reconstructed from that TRX alone.

## Separate job-timeout correction

Only Numerical full acceptance checkout omits historical evidence and tracked build/package caches. All runtime sources, Godot assets/fonts, configuration and protocol inputs remain; NuGet restores packages from the existing official source. Independent sparse-copy verification compares every retained normalized Git blob ID against the complete local source manifest and records physical SHA256 separately, since fresh Windows Git text filters can change LF/CRLF bytes. The first physical-hash verification failure is retained. This does not change the full local checkout or its resource delivery.

The verified sparse copy retains **2,397 files / 622,501,625 baseline physical bytes** and omits **7,685 files / 1,801,420,921 baseline physical bytes**. Every retained Git blob matches. Both initial verifier failures (LF/CRLF physical comparison and an incorrectly named required path) remain recorded; the corrected required path is the actual tracked `client/network/gateway.gd`.

The **25-minute workflow timeout and all 10/30-second business budgets remain unchanged**. No test is excluded, no assertion is weakened, and first-failure artifacts remain available. Final fixed-SHA full local/CI outcomes are recorded separately after this change; the targeted green results alone are not a complete regression signoff.

## Follow-up at source 636306c

The clean fixed-SHA local solution passed **Domain 349/0/0 + Server 303/0/0**; fixed-SHA TCP recovery passed **9/0/0**, Windows real LOAD02 passed **3/0/0**, and ordinary-client raw receipts again prove the second barrier while four real Pending holds exist before wallet commit. All 8,004 predecessor evidence files remain unchanged.

At `636306c86381e95316a0172cc7519a5eb6254364`, Numerical full acceptance [36888428025](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36888428025) and two other workflows succeeded. Numerical checkout took 94 seconds. Gameplay [36888427975](https://github.com/AlenSheng/godot_FanstaryCard/actions/runs/36888427975) was cancelled: its PostgreSQL job's unchanged 20-minute limit was exceeded, after 9m46s of full checkout. The cancelled Gameplay suite is incomplete and is not counted as passed; the Numerical success does not cover it. The original cancellation annotation and available raw archive remain preserved.

The follow-up applies the same already verified runtime sparse checkout to Gameplay's PostgreSQL job, retains its 20-minute limit, and adds a diagnostic marker only after every original same-room/restart/inventory assertion finishes. A new source commit triggers all four normal PR checks. Final outcomes are recorded separately; no failed or cancelled attempt is rerun or erased.

## Acceptance and delivery boundary

No independent acceptance is changed: **16 Accepted / 41 Partial / 72 NotRevalidated / 3 Blocked**, 132 unique tasks. The previous LOAD02, public-input combat strategy, real deck ledger changes and second four-Pending ordinary-client barrier remain intact. B03/B06 unmet prerequisites and broader ledger gaps stay open. Four old-cloud simulation raw ZIPs (31,096,278 bytes) remain unavailable; no Library ID is invented.

Local new evidence: `relicround-local/evidence/markrunning-20261001-v2/`. Its final manifest references and verifies the preserved 8,004-file predecessor manifest SHA256 `3133ffc01ce595d03a3127468e56b41265fc8fdd0066a43a818407b67740cad5`; it does not overwrite that manifest or any predecessor evidence.
