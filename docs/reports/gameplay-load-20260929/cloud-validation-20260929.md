# PR13 cloud validation, 2026-09-29

The user authorized deployment and bounded load testing on the not-yet-public formal cloud service. The test target was `https://www.relicbound.cn`. The server ran PR13 server source `cb96d163d14719b24b89bceeefe1e7be24eff4ff`; later PR13 commits changed the client and local load generator only. `release` was not merged or changed.

## Deployment and safeguards

- Pre-deployment cloud checkout and deployed marker: `c0a8ebd462502df327e4bc98cd4c9356e14ad1da` on `release`; readiness `Healthy`.
- The cloud checkout had a three-line, uncommitted `HttpDtoMapper` indexer guard that is already in the PR13 base. It was preserved as `stash@{0}: pr13-preserve-cloud-indexer-fix`. Two pre-existing untracked `.env.before-*` backups were left untouched.
- The updater fetched the PR13 branch, backed up PostgreSQL to `/opt/fantasycard-app/backups/fantasycard-20260929T070844Z-before-cb96d163d14719b24b89bceeefe1e7be24eff4ff.dump`, rebuilt the server image and passed its local, public TLS, and admin-boundary health checks. The deployed marker is `cb96d163d14719b24b89bceeefe1e7be24eff4ff`.
- All clients came from one public IP. The default per-IP authentication limit of 10 requests/minute caused 429 responses in the first 50-client attempt. For subsequent capacity runs, the cloud `.env` was temporarily set to auth 150, economy write 300, market read 300. The exact original `.env` was backed up with mode 600 at `/opt/fantasycard-app/backups/pr13-env-before-capacity-20260929` (SHA-256 `b6447257f742989ad27f1ba583432800424c50febd46904e9bd627ae089d8987`). After the final run it was restored byte-for-byte; the live container again has limits 10/30/120 and readiness `Healthy`. No permanent rate-limit change is in the PR.
- The original `release` build can be restored by switching the cloud checkout to `release` and running the updater without `FANTASYCARD_DEPLOY_BRANCH`. The database backup and preserved Git stash remain available. This rollback was prepared but not needed.

## Bounded runs

Raw reports and JSONL are local under ignored `outputs/gameplay-load/`; they may contain private account or session data. [The evidence manifest](cloud-evidence-manifest-v2.json) records SHA-256, size and relative name for all 2,084 files from the new cloud runs. No raw client output is committed.

| Run directory | Workload | Outcome | Key evidence |
| --- | --- | --- | --- |
| `20260929-151009-ab9b66` | 10 clients, 720 s, default limits | Duration reached; old schema 4 calls it incomplete | All 10 completed 3–4 acknowledged cycles, 37 total; 0 forced terminations; no old-room registration error in server logs. |
| `20260929-152329-a345db` | 50 clients, default limits | Invalid workload at 134 s | 90 auth 429 attempts from one IP; only 20 online and 18 in room at peak. This is a limit test, not capacity evidence. |
| `20260929-152749-61888e` | 50 clients, temporary limits, old transport | Performance redline at 185 s | 50 online/in room; 27 settlements; HTTP P95 1614/1731/1945 ms in three consecutive effective windows; no forced terminations. |
| `20260929-153825-df0af0` | 1 client, persistent transport | Smoke passed, exit 0 | One acknowledged settlement; 9 of 12 attempts reused the connection; reused attempt median 297 ms versus cold 1014 ms; no forced termination. |
| `20260929-154256-6c293c` | 50 clients, persistent transport | Invalid workload at 265 s | 46 settlements; HTTP redline did not fire, but four clients could not finish battle within 240 s. |
| `20260929-155029-4f6d86` | 50 clients, battle fallback | Invalid workload at 204 s | Two clients received `NOT_IN_ROOM` while their settlement assets were still being committed. This exposed the missing client recovery poll. |
| `20260929-155805-888652` | 50 clients, settlement recovery, 360 s | Duration reached; old schema 4 calls it incomplete | 50 clients completed at least one cycle, 40 at least two, 86 total; 818/1075 attempts reused the connection; one non-consecutive HTTP P95 breach; 0 forced terminations. |
| `20260929-160743-0d480d` | 50 clients, 150 s, schema 5 | `load_window_completed`, exit 0 | All evidence gates met; 50 online and active in room, 14/14 required samples, 9 settlements, no forced termination. |
| `20260929-161132-1d21cf` | Two groups of 50, 120 s apart | Invalid workload at 141 s | One first-group status file was briefly absent during Windows file replacement. No client had failed; the sampler now retains the prior owned status until the 30 s stale bound. |
| `20260929-161746-51e014` | Two groups of 50, 120 s apart, 360 s | `load_window_completed`, exit 0 | 100 peak online and active in room, 130 acknowledged cycles, 35/33 required samples, 0 forced terminations or failed processes; 98 clients completed at least one cycle and 41 at least two by the time limit. |

The final two-group run had two individual HTTP P95 breach windows and no three-window stop. Its server CPU peak was 40.6%, minimum server memory available 58.5%, and minimum local generator memory available 3.5 GiB. It recorded 1,409 reused connections out of 1,873 HTTP attempts and two explicit `battle.abandon.fallback` actions. Its `load_window_completed` classification verifies the bounded workload and stop rules; it does not mean every client finished a match before the 360-second limit or that all PR13 acceptance gates are closed.

## Latency attribution

For the first 180 seconds of the equal-size 50-client runs, the old transport had 599 successful logical HTTP requests, a nearest-rank P95 of 3166 ms and median of 1015 ms. The persistent transport had 677 successful requests, P95 of 1533 ms and median of 419 ms. This is a 51.6% lower P95 on those observed sets. Request counts and gameplay timing differ, so this is diagnostic A/B evidence rather than a controlled causal estimate. During the old-transport redline, Prometheus estimated server HTTP P95 at about 45 ms and mean at about 14 ms over one minute; client delay was dominated by the transport path. The new client reuses a verified TLS `HTTPClient` connection for sequential requests, retaining the existing `HTTPRequest` path for overlap and Web builds. [Godot's HTTPClient documentation](https://docs.godotengine.org/en/stable/classes/class_httpclient.html) explicitly supports multiple requests on one connection.

## Checks and remaining acceptance work

- GitHub `Gameplay load offline checks` passed all four jobs on `f92b5de12162eff8a1e4b82d3c4cc61d3888a107`: Python, Godot client, full Server.Tests offline, and disposable PostgreSQL replay. Local Python suite: 33 tests passed. The Godot play/settlement regression suite and real HTTPS reuse probe passed.
- The separate Numerical regression and Numerical full acceptance workflows still fail to compile pre-existing `FantasyCard.Domain.Tests/Combat/CombatAuthoritativeRulesTests.cs` because its `PlayerCombatState` call uses removed `useConsumptionBasedFenxian` parameters. This failure predates PR13 and is outside the gameplay-load workflow.
- LOAD-04/05 fault injection matrices, complete historical raw-data reconciliation, and long-term capacity/SLO evidence still require work. The 100-client result establishes this bounded 360-second test under temporary per-IP limits, not sustained public-service capacity at the default limits.
