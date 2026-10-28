# Independent migration QA — 2026-09-28

Executor: real `fc_qa` child agent; runtime identity is recorded by the coordinator in execution-state.json. Tested worktree: `F:\GitHubFiles\godot_FanstaryCard-protobuf`. No production server/database, push, deployment, destructive Git operation or gameplay edits by QA.

## Result

**The strict solution builds, and no new failing test remains relative to the archived HEAD baseline; the full solution is still red because three existing baseline tests fail. Extended testing also reproduced a fourth, previously untested existing market relisting defect. This is not a claim of release readiness or defect-free business behavior.**

Final complete command (SDK 10.0.400, from server, isolated local PostgreSQL enabled):

`dotnet test FantasyCard.Server.slnx --artifacts-path .artifacts/qa-final --logger "trx;LogFilePrefix=qa-20260928-120741" --results-directory .artifacts/qa-final/results`

| Suite | Passed | Failed | Skipped | Evidence |
|---|---:|---:|---:|---|
| Domain | 207 | 1 | 0 | qa-20260928-120741_net10.0_20260928120756.trx |
| Server | 232 | 2 | 0 | qa-20260928-120741_net10.0_20260928120917.trx |
| Godot official/golden/HTTP codec | 103 checks | 0 | 0 | work/qa-client-20260928-120741/codec.log |
| Godot actual HTTP fixture/worker/session guards | 19 checks | 0 | 0 | work/qa-client-20260928-120741/transport.log |

Solution exit 1; client exit 0. Raw full log: `work/qa-solution-20260928-120741.log`. The first complete final run is also retained: `work/qa-solution-20260928-120539.log` and matching TRX. All database tests were enabled against coordinator-provisioned PostgreSQL 18.6 on loopback port 54329, each fixture using its own schema. Credentials were read from a local file and never printed.

Baseline failures repeated without gameplay changes:

1. `EquipmentCombatRulesTests.Combat_formula_applies_attack_bonus_target_resistance_then_piercing`: expected 54, actual 49.
2. `PostgresCardEconomyTests.Cumulative_upgrade_spend_is_refunded_once_and_last_copy_resets_level`: expected 1045, actual 1033.
3. `Real_process_pvp_relic_replay_and_extraction_survive_forced_restart`: opponent/player ID mismatch at RealNetworkGameplayTests.cs:96. Later combat/relic/extraction/restart assertions in this case are **not reached** and therefore are not certified by this run.

The old xUnit2012 build failure was corrected by the coordinator using an equivalent collection assertion. QA did not weaken the strict final build flags.

## Actual runtime coverage

There are **46** frozen registry method/path pairs. The independent default-Protobuf process calls all **44 authenticated** routes anonymously with syntactically valid bodies and route arguments: every response must be typed Protobuf **401**, not a broad allowance for 400/404. This checks endpoint wiring and auth boundaries, and is separate from business-success coverage below.

| Area | Actual exercised behavior | Evidence / limit |
|---|---|---|
| Auth/bootstrap/profile/decks | PB local sign-in, full bootstrap, profile/class update, deck read/save | ServerApiDatabaseTests + independent/default test; Steam provider mocks in existing suite, no live Steam credentials |
| Cards | PB activate GW08, upgrade, dismantle with returned versions | MigrationBusinessTests; frozen economy baseline failure still remains separately |
| Equipment/loadout | PB quote/enhance armor and class weapon, inventory, read/save loadout | MigrationBusinessTests |
| Market | PB list, actual purchase, assert DB ownership transferred, list/cancel a different fresh item, market/context reads | MigrationBusinessTests; expectedVersion stays explicit query parameter |
| Shop/economy | PB shop/context/wallet reads, refresh; PB purchase then same key+normalized JSON operation returns original result with one debit | ServerApiDatabaseTests + MigrationBusinessTests |
| Mail | PB list/read/read-all/claim/claim-all/delete/delete-read; seeded 17-gold attachment, duplicate claim, exactly +17 in DB | Final targeted MigrationBusinessTests after complete suite; B's oversize claim-all transaction guard and 200+5 pagination tests also pass in full suite |
| Matchmaking/preparation | PB create/read preparation, enqueue/read ticket, cancel ticket/preparation | MigrationBusinessTests; actual ready-to-room confirmation beyond these HTTP operations is not covered by this new test |
| Settlement | PB read by settlement and match IDs, repeat acknowledgement, another player's 404 | Seeded completed persisted settlement; not proof of full in-room reward generation. Timestamps compared at PostgreSQL microsecond precision |
| Ticket/WS | Default-PB ticket -> binary welcome/pong, same-ticket upgrade rejection, default access_token query rejection, fresh-ticket takeover, active session expiry closes WS and blocks new ticket | MigrationIndependentTests |
| Lifecycle | Actual 31-second ticket expiration rejects upgrade; DB ban closes otherwise-idle WS within 12-second bound and denies new ticket | MigrationTicketLifecycleTests, both cases passed in full suite |
| Real Godot -> .NET -> PostgreSQL | PB login/bootstrap/profile/deck, ticket/WS ping, reconnect/replay/takeover | Client agent's real runner: 20 checks passed, independently inspectable work/client-real-server logs; executed by fc_client, not attributed to QA |
| Compatibility and budgets | malformed body, typed errors, negotiation/q, JSON disabled, 204, Retry-After, pagination, numeric and length/depth budgets | Existing/new server boundary tests and 103-check Godot codec suite |
| Perimeter | public admin denial/redaction, JSON exceptions, binary proxy | Perimeter agent's 20 tests + 14 local proxy checks; no production deployment |

Detailed concrete business request trace is generated at `server/.artifacts/qa-migration/business-covered.txt`. Authorization-route coverage is not substituted for successful business behavior. No live third-party Steam login, production certificate/CDN, distributed load, Docker image build, or successful full PVP/relic/extraction/restart chain is claimed.

## Performance measurements

Machine: Intel Core Ultra 7 155H; Windows 10.0.26200; SDK 10.0.400, runtime 10.0.11, Google.Protobuf 3.33.0; Godot 4.7.2 official. Debug .NET tests, same actual new-account Bootstrap response within each run. No Accept-Encoding and no HTTP compression enabled. Numbers are observations on this machine, not production capacity estimates.

.NET codec: 20 warmups and 100 measured operations, single-thread allocated bytes via GC.GetAllocatedBytesForCurrentThread. PB includes typed DTO mapping/validation; JSON uses the same DTO and WebJson options. Final sample PB **36,093 B**, JSON **249,001 B**.

| Final operation | Mean ms/op | Allocated B/op |
|---|---:|---:|
| PB encode DTO | 3.526 | 779,880 |
| PB decode DTO | 2.229 | 878,660 |
| JSON encode DTO | 0.505 | 249,878 |
| JSON decode DTO | 1.058 | 452,296 |

Before metadata caching, a prior actual Bootstrap sample (36,093 PB / 249,006 JSON) measured PB encode **35.515 ms / 13,569,469 B**, PB decode **14.896 ms / 7,452,274 B**; JSON encode **1.737 ms / 249,922 B**, decode **4.870 ms / 452,296 B**. Different timestamp/ID text and system load prevent treating these separate runs as a controlled percentage speedup. Both raw sets are retained in `server/.artifacts/qa-migration/before/` and `samples/`. The cache removes a material allocation cost; final PB still costs more CPU and allocations than JSON.

HTTP loopback, sequential real Bootstrap GETs, 5 warmup + 30 measured per format, full body consumption, nearest-rank p50/p95/p99. JSON uses an explicitly compatible process on a second loopback port with the same database/player. Full regression tests were running concurrently, so tail latency is noisy:

| Run | Format | p50 ms | p95 ms | p99 ms |
|---|---|---:|---:|---:|
| First full run | PB | 19.84 | 30.13 | 33.61 |
| First full run | JSON | 28.51 | 39.40 | 43.33 |
| Final full run | PB | 27.83 | 50.95 | 94.27 |
| Final full run | JSON | 22.65 | 36.65 | 37.34 |

The direction changes between runs; **no reliable end-to-end speed improvement is established**. One earlier repeated-Bootstrap attempt timed out at HttpClient's 100-second limit; later repetitions completed. The cause was not established and no fix is asserted. Initial development log filenames were reused before unique run naming was introduced; the timeout is preserved in tool transcript and this report, not misrepresented as an available unmodified raw logfile.

Godot main-thread codec benchmark: actual captured Bootstrap 36,093 PB / 249,006 JSON, 5 warmups + 30 iterations. PB decode+DTO adaptation **79.73 ms**, encode+adaptation **49.49 ms**; JSON parse **14.21 ms**, stringify **11.44 ms**. This led the client owner to move >8 KiB responses to a worker. Separate final scheduling verification by fc_client used a slightly different 36,092-byte sample, 3 repetitions: synchronous mean **58.830 ms**, worker wall mean **66.723 ms**, **14 frames advanced**, max frame gap **16.703 ms** at headless 60 fps. Worker scheduling reduces main-thread blocking; it does not eliminate codec CPU time, and these different runs must not be used for a claimed percentage speedup. Godot per-operation allocation measurements are **not available** from this script.

Offline gzip level 6 of the earlier same bytes: PB **3,766 B**, JSON **5,635 B**. This is a size-only calculation, not measured compressed HTTP latency. Compression-on end-to-end behavior was not enabled or measured.

## Reproduction and changed QA files

`tools/run-protobuf-qa.ps1 -DotnetRoot <local SDK directory> -ConnectionFile <isolated local PostgreSQL connection file> -Godot <console executable>` runs strict solution tests plus the isolated Godot HTTP runner and preserves timestamped logs. It rejects a non-loopback database host. The final expected solution exit remains 1 until the three existing failures are addressed.

`MigrationIndependentTests` writes real Bootstrap samples plus benchmark JSON. To reproduce the Godot raw codec benchmark, run the client fixture builder first, copy `bootstrap.pb` and `bootstrap.json` from `server/.artifacts/qa-migration/samples/` to that isolated client directory, copy `tools/benchmark-http-protobuf.gd` there, then invoke Godot headless with that script.

QA-owned source changes:

- server/tests/FantasyCard.Server.Tests/ProtobufHttp/MigrationIndependentTests.cs
- server/tests/FantasyCard.Server.Tests/ProtobufHttp/MigrationBusinessTests.cs
- server/tests/FantasyCard.Server.Tests/ProtobufHttp/MigrationTicketLifecycleTests.cs
- tools/benchmark-http-protobuf.gd
- tools/run-protobuf-qa.ps1
- tools/BaselineMarketRelistRepro.cs
- docs/network-protobuf-migration/qa-baseline.md
- docs/network-protobuf-migration/qa-report.md

Test-development failures, all kept distinct from product regressions: CA1869 options caching (fixed test); second craft incorrectly requested for an already activated card (fixed test); missing market expectedVersion query (fixed test); anonymous empty GUID request hit binder400 (replaced with valid syntax and strict401); timestamp equality finer than PostgreSQL precision (compared at microsecond precision). No gameplay assertion was changed to hide a baseline failure.

## Remaining release gates / rollback

Resolve or explicitly accept the three existing failures under gameplay-owner review before claiming full regression success. Reproduce/diagnose the one transient Bootstrap timeout under controlled load; perform longer isolated Release benchmarks if capacity decisions depend on results. Run a successful full room/PVP/relic/extraction/restart chain after fixing its baseline test/behavior issue. Live Steam verification and production TLS/CDN/deployment checks remain external gates.

For coordinated rollback, keep old client binaries available and explicitly enable the documented server JSON and legacy query-token compatibility switches only for the intended old-client rollout window. Do not silently retry failed binary writes as JSON. No rollback or production configuration change was executed by QA.


## Final targeted enhancements and additional existing market defect

After the final complete suite, only the new QA business test was strengthened: 17-gold mail reward plus duplicate claim, and successful market cancellation using a different fresh equipment item. No production file changed for these enhancements. Command:

`dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --artifacts-path .artifacts/qa-final --filter FullyQualifiedName~Migration_binary_business --logger "trx;LogFileName=business-final-cancel.trx" --results-directory .artifacts/qa-final/results`

Final result: **1 passed, 0 failed, 0 skipped**, 5 seconds, exit 0. Evidence: `work/qa-business-final-cancel.log` and `server/.artifacts/qa-final/results/business-final-cancel.trx`. Earlier reward-only strengthened run also passed: `business-final-reward.trx`.

**Existing defect discovered by expanded coverage:** after a buyer purchases an equipment item, trying to list that same item again returns typed HTTP **500**. The failure is retained in `work/qa-business-final-complete.log` / `business-final-complete.trx`. This is not counted among the original three failing baseline tests, because they did not cover resale.

Confirmed at runtime against archived original HEAD `b8e848ebb6f9a4bcbbdd83d99bdb5589a99b04ce`, not inferred merely from the current code: copied the standalone `tools/BaselineMarketRelistRepro.cs` into the isolated baseline test project and exercised its original EconomyRepository: seller lists -> buyer purchases -> buyer relists. The final operation throws PostgreSQL **23505**, constraint **market_listings_equipment_id_key**. The explicit defect-characterization test passed 1/1, meaning it confirmed the bug, not that resale works.

Baseline command (from `work/qa-baseline/server`, same isolated PostgreSQL):

`dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --artifacts-path .artifacts/qa-baseline-db -p:TreatWarningsAsErrors=false --filter FullyQualifiedName~Baseline_market_relisting --logger "trx;LogFileName=baseline-relist.trx" --results-directory ../qa-results`

Evidence: `work/qa-baseline/baseline-relist.log`, `work/qa-baseline/qa-results/baseline-relist.trx`. The original V005 schema declares equipment_id globally UNIQUE, while the original ListAsync inserts a new history row; a sold row continues occupying the key. No economic model/schema fix was made during this network migration. Resale remains a separately documented release issue requiring an intentional forward migration/market-history design review. Successful fresh-item cancellation does not hide or resolve this defect.

## Remediation correction (2026-09-28, fc_realtime)

The earlier description of `Real_process_pvp_relic_replay_and_extraction_survive_forced_restart` as an opponent/player-ID mismatch was incorrect. The retained original log shows line 96 compared two 32-character **event IDs**, after the opponent-ID and successful PVP kill assertions had already passed. The helper consumed a trailing `room.snapshot` from the first mutation because it shared the request ID; the retry assertion therefore compared different event types. The helper now additionally matches the original mutation event type, retains strict event-ID equality, and does not change server replay logic. The complete PVP/relic/extraction/forced-restart/idempotency chain now passes; see `remediation-gameplay-report.md` for actual commands and TRX. The historical failed run above remains evidence of the original test failure, not evidence of failed opponent projection.
