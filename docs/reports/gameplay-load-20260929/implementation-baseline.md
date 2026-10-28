# PR 13 implementation baseline

Captured 2026-09-29 before implementation changes.

| Item | Frozen value |
| --- | --- |
| Target branch | `release` at `28c6c7e7d3898e4d2abd186f53361477ba380330` |
| PR 13 input | `ab3f630caa2734a1a71ea15e7cfe172b65f07c38` (seven commits after target) |
| Implementation branch | `codex/pr13-implementation-20260929` |
| Initial worktree | Clean; prior local outputs preserved in `stash@{1}` at capture time, named `pre-pr13-cleanup-20260929-build-and-validation-artifacts` |
| Python | 3.9.7; existing 22 offline tests passed |
| .NET | SDK 10.0.400 at `C:\Program Files\dotnet`; server tests 189 passed, 62 skipped after restore; Domain.Tests fails compilation against existing `PlayerCombatState` API |
| Godot | 4.7.2.stable.official.ed1daf0bf; 15 offline client suites passed |
| Historical load report | `docs/reports/gameplay-load-20260929/summary.md`; historical raw files preserved in the named stash, not committed |

The preserved raw gameplay load output includes `outputs/gameplay-load/20260929-104400-128750/report.json` (Git blob `8bdb184e68eff8bc233682c8a289605cd80b65b4`) and per-client JSONL. The archived production-run report includes `outputs/prod-load-test-20260929/rerun-02/report.json` (Git blob `9bff0a0489d149bbcf203ceb72e9ffcc72c6c1b4`). These are source pointers, not a completed reaggregation. Matching server logs, deployed image digest, exact database version and instance-specific monitoring selectors remain unverified. No historical capacity or performance conclusion is accepted from this manifest.

## Frozen event contract for implementation

- Each launch gets a `run_id`, `client_id`, and `process_epoch`; every emitted telemetry event gets a strictly increasing `event_seq`. A cycle has a `cycle_id`; unavailable business IDs are omitted or null, never invented.
- Phases are `login`, `initial`, `matchmaking`, `playing`, `settlement`, and `cleanup`; old untagged events remain `unknown/legacy`. Monotonic timestamps measure durations; UTC milliseconds support cross-process correlation only.
- HTTP records one logical request ID and per-attempt number, route template, session generation, result class, total duration, decode duration, body bytes and retry wait when measurable. Pending, timeout and cancellation remain visible outcomes. Auth tokens, tickets, request bodies and private responses are excluded.
- The runner must confirm ownership before counting state or telemetry. Active room count requires a live process, fresh state and online connection. Server-confirmed room occupancy stays unavailable until measured by a trusted server source.
- Historical redline thresholds remain unchanged. Insufficient samples yield `unknown`, not pass. The implementation may stop earlier for evidence loss or safety, but cannot label that run a historical-load pass.

The default execution target for new runs is an isolated local endpoint. Public/production load runs require a separately specified target and explicit run scope; this implementation does not deploy or change rate limits.
