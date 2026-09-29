# PR 13 implementation progress (2026-09-29)

The implementation branch is `codex/pr13-implementation-20260929`, based on PR 13 input `ab3f630` and `release` base `28c6c7e`. PR 13 remains a draft. No production service, rate limit, account, or deployment was changed.

## Implemented and locally checked

| Area | Change | Check |
| --- | --- | --- |
| Generator and accounting | Validates owned PID/epoch/status; separates live/online/room; counts event sequences and evidence loss; bounds groups, duration and target; uses monotonic scheduling, bounded probes, generator resource samples, explicit stop outcomes and forced termination evidence. | `python -m unittest discover -s tools/tests -q`: 32 passed; dry-run prepare returned 0. |
| Godot client | Three-cycle default smoke; ticket-authoritative match identity before ready send; finite ready retries; settlement completion follows acknowledged server response; STOP yields cancelled; lifecycle and HTTP attempts have audit events; autoload skips shared `user://session.cfg` in load mode. | Godot 4.7.2 `run_play_retry.gd`: 15 suites passed; `run_gameplay_load_parse.gd`: passed. |
| Matchmaking and room lifecycle | Enqueue replay joins `match_players` on both player and preparation. A settled player releases the old room route after durable settlement, while teammates remain in that room. Recovered terminal players do not reserve a route. | Full local Server.Tests: 191 passed, 62 skipped; disposable PostgreSQL CI replay integration: 1 passed, 0 skipped. |
| CI | Added offline Python, Godot and .NET workflow with artifacts. | Workflow has not yet executed on GitHub. |

## Evidence still required for acceptance

- The replay regression ran on CI's disposable PostgreSQL service and passed. The complete database suite remains unverified locally because `FANTASYCARD_TEST_POSTGRES` is unavailable.
- An explicitly authorized, bounded one-client cloud smoke completed three real consecutive matches on the same account at `https://www.relicbound.cn`. Run `20260929-141906-a00d74` returned exit 0 with 3 acknowledged settlements, 3 room starts, 499 consecutive JSONL events, no audit loss, 0 failed client checks, and no forced termination. The 56 ten-second windows show no stop-line trigger. This establishes the single-client cycle path; it does not establish capacity or P95 recovery under concurrent load. The preceding run `20260929-141727-3c4981` stopped with invalid ownership evidence because the Windows Godot console launcher PID differs from the engine PID; the runner now launches the engine executable directly.
- The authorized ten-client, one-group, five-minute maximum run `20260929-143213-09f7dc` stopped automatically at 183.7 seconds after 3 clients exited with `room_start_timeout` in their second cycle. Seven settlements had been acknowledged; the other 7 live processes were cancelled and all processes exited without forced termination. The initial login window had 10 expected `/api/v1/client-info` cancellations, then recovered; later stop windows did not show a sustained HTTP redline. Instance-specific CPU, memory, disk and actor wait metrics were available through a temporary SSH tunnel, which was closed after diagnosis.
- The ten-client report used schema version 3, which counted login cancellations as HTTP errors and latencies. Version 4 now keeps cancellation count and latency separate from completed HTTP requests; 32 offline accounting tests pass after this correction. The raw run and its hash remain unchanged, so comparison reports must name the accounting version.
- Read-only server logs at the failure time repeatedly reported `Ready-match launch iteration failed: Player ... is already assigned to a room.` The affected clients had received `room.ready_accepted` for the next match but no `room.started`. The service-side route fix above addresses this proven failure path locally. It has **not** been deployed or validated on the cloud server. A separate economy reconciliation log reported `ledgerChainMismatches=1`; cause and relation to this run are unknown, and this change does not touch economy data.
- The historical raw load set, deployed server image/config and instance-specific metrics are not yet fully reconciled. HTTP P95 improvement and capacity recovery have **not** been established. The smoke's 26 logical HTTP requests are diagnostic only; one cancelled `/api/v1/client-info` request occurred during login, and the run passed its configured stop checks.
- LOAD-04/05 fault matrices, service-side trace stages, and conditional LOAD-08/09 performance changes require runtime evidence. The ten-client run surfaced a concrete LOAD-09 room-route defect; its fix still needs a deployed comparison run. These remain InProgress, Planned or Conditional in the execution status; none is marked Accepted.

The first prerequisite for a performance claim is a known server build, isolated test target, complete client JSONL and server/DB metrics for the same run. Until then the historical redlines stay unchanged and the PR remains draft.

The first GitHub `Gameplay load offline checks` run (commit `9402a86`, run `36533144017`) passed Python, Godot and .NET jobs. The follow-up run (commit `da89838`, run `36533402709`) passed all four jobs: Python accounting, Godot client, .NET contract, and disposable PostgreSQL replay integration (1/1). The separate existing `Numerical regression` workflow fails because stale Domain.Tests source references removed `PlayerCombatState` members; the same failure was present in the implementation baseline and is outside this load-test workflow.

## Local raw evidence index

Raw files remain under ignored `outputs/gameplay-load/`; they are not committed because client logs can contain private account or session data. The [local evidence manifest](local-evidence-manifest.json) records names, sizes and SHA-256 hashes for all 60 files from the three runs. Selected checksums:

| Run/file | SHA-256 |
| --- | --- |
| `20260929-141906-a00d74/report.json` | `32caae0f942c0c407e0de31bc0645c5a5ebac9e8d7e35f35e02af8479ec682e8` |
| `20260929-141906-a00d74/g001c0108dd7b.json.telemetry.jsonl` | `455163033ae5cfbe0ea77dee4e9d349cbd521182a0d3b80fe5732fc8a91daec4` |
| `20260929-143213-09f7dc/report.json` | `bcd71df8c1870553f83a1fefefb43c6001847633c7cc29c7708c1d1a76372a27` |
