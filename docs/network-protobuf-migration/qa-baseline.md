# QA phase-one baseline — 2026-09-28

Executor: real Codex child agent `fc_qa` (coordinator records runtime ID in execution-state.json).
Baseline: `b8e848ebb6f9a4bcbbdd83d99bdb5589a99b04ce`.

## Isolation and instructions

Read PLAN.md, fc_qa.toml, server/AGENTS.md, GDD network section, SERVER_SPEC, SERVER_0_TO_1_GUIDE and CLIENT_INTEGRATION network/startup conventions. The referenced `.agents/skills/server_create/SKILL.md` is absent. The user authorizes replacing the former JSON-only HTTP policy; gameplay constraints remain applicable.

Exported HEAD with `git archive HEAD server client protocol config tools docs GDD.md -o work/qa-baseline/source.tar`, then extracted under work/qa-baseline. No product source was edited. The full client defaults to a production server URL, so no full client scene was launched. A minimal isolated Godot project copies only baseline protobuf.gd, realtime_schema.json and the existing test_protobuf.gd, with no autoload or network connection.

## Executed commands and evidence

- From isolated `work/qa-baseline/server`: `dotnet --version` and `dotnet test FantasyCard.Server.slnx --artifacts-path ../qa-artifacts --logger "trx;LogFilePrefix=baseline" --results-directory ../qa-results`. Failed before build: installed PATH host reports **No .NET SDKs were found**, while global.json requests 10.0.400. Exit -2147450735. Log: `work/qa-baseline/dotnet-baseline.log`. No .NET tests passed or skipped by a runner, because no runner started.
- `Godot_v4.7.2-stable_win64_console.exe --headless --path work/qa-baseline/proto-only --script res://run.gd`: exit 0, existing `test_protobuf.gd.run_test()` returned ok=true. Golden wire, nested repeated/default fields, unknown fields and truncation passed. Log: `work/qa-baseline/godot-protobuf.log`.
- Same Godot executable with `--script res://probe.gd`: baseline `RoomPlayer.safe_slot_indexes` unpacked bytes `58 01 58 02` decode to [1,2]; packed bytes `5A 02 01 02` fail with **Unexpected wire type**. This is a reproduced compatibility defect, not a passing compatibility test. Log: `work/qa-baseline/godot-packed-probe.log`.
- Read-only local checks: no psql, pg_isready or docker on PATH; no matching PostgreSQL Windows service; no listening local TCP 5432 found. No database connection was made. FANTASYCARD_TEST_POSTGRES was cleared for the attempted child test process, avoiding inherited external database access.

Machine CPU: Intel Core Ultra 7 155H. Godot: 4.7.2 stable official ed1daf0bf. .NET SDK unavailable through PATH at baseline attempt.

## Phase-three validation plan

1. Repeat full .NET solution and Godot protocol suites using frozen generated artifacts; add cross-language vectors for packed/unpacked, optional zero/presence, negative/int64 boundaries, unknown fields, nested repeated messages and malformed/oversize inputs.
2. Obtain an isolated local PostgreSQL database before running existing conditional persistence and RealNetwork E2E tests. Existing tests select FANTASYCARD_TEST_POSTGRES and use isolated schemas; confirm every selected fixture before enabling it. Use FANTASYCARD_E2E_SERVER_DLL when build output is isolated.
3. Exercise protobuf login -> bootstrap -> profile/deck, then registered non-realtime modules; check 401/403/409/429, Retry-After, unsupported media and non-protobuf proxy errors. Assert one economy mutation across same-key PB/JSON retries using normalized domain requests; verify differing same-key requests conflict and another player cannot access assets.
4. Exercise ticket expiry/reuse, replaced/expired sessions, resume/replay/sequence gaps, malformed/fragmented frames and bounded queues, preserving existing room gameplay.
5. Compare the same real typed bootstrap/profile and room snapshot samples as JSON and PB: bytes, encode/decode time and allocation, Godot main-thread time. Once a local end-to-end server exists, report p50/p95/p99 with warmup, iterations and compression settings. No performance improvement is claimed before measurement.

Full login/gameplay, local PostgreSQL integration, production TLS/proxy behavior and performance measurements remain **not executed** at this phase. Only the isolated existing Godot protobuf baseline passed.

## SDK-enabled follow-up (actual run)

Coordinator installed the official SDK locally. With DOTNET_ROOT and PATH pointed to `C:\Users\79498\Documents\Codex\2026-09-28\referenced-chatgpt-conversation-this-is-an\work\toolchain\dotnet-sdk`, `dotnet --version` reports **10.0.400**.

The same strict full-solution command now builds production projects but fails overall:

- Domain: **207 passed, 1 failed, 0 skipped**. Existing baseline failure: `EquipmentCombatRulesTests.Combat_formula_applies_attack_bonus_target_resistance_then_piercing`, line 85, expected 54, actual 49. Frozen gameplay was not edited.
- Server tests: compilation blocked by existing `LocalizedContentContractTests.cs:38` xUnit2012 (Assert.True(collection.Any(...)) must use Assert.Contains), because warnings are errors. No server tests executed in this strict run.
- Log: `work/qa-baseline/dotnet-baseline-sdk.log`; TRX in `work/qa-baseline/qa-results/`.

Additional **diagnostic**, not a passing strict gate:

`dotnet test FantasyCard.Server.slnx --artifacts-path artifacts/qa-baseline -p:TreatWarningsAsErrors=false --logger "trx;LogFilePrefix=baseline-diagnostic" --results-directory ../qa-results`

- Domain: **207 passed, 1 failed, 0 skipped**, same expected54/actual49 failure.
- Server: **160 passed, 0 failed, 47 skipped** (database-dependent suites were explicitly disabled by empty FANTASYCARD_TEST_POSTGRES).
- Overall exit **1**. Log: `work/qa-baseline/dotnet-baseline-diagnostic.log`.
- Artifacts were moved beneath the isolated server tree because existing RealNetwork fixtures walk upward from AppContext.BaseDirectory to locate src/FantasyCard.Server. This matters when enabling the pending local DB tests.

No product or existing test code was altered by QA. PostgreSQL-enabled baseline awaits coordinator's isolated loopback instance.

## PostgreSQL-enabled isolated baseline

Coordinator provisioned PostgreSQL **18.6** listening only on **127.0.0.1:54329**, matching the repository's major version 18. Connection settings were read from the coordinator's local connection file without printing credentials, and the endpoint was checked before execution.

From the archived HEAD server directory, with SDK PATH/DOTNET_ROOT and FANTASYCARD_TEST_POSTGRES set for this process:

`dotnet test FantasyCard.Server.slnx --artifacts-path .artifacts/qa-baseline-db -p:TreatWarningsAsErrors=false --logger "trx;LogFilePrefix=baseline-db" --results-directory ../qa-results`

Actual results (overall exit **1**):

- Domain: **207 passed, 1 failed, 0 skipped**, same combat expected 54 / actual 49 baseline failure.
- Server: **205 passed, 2 failed, 0 skipped**, duration 46 seconds. All 47 formerly skipped database cases were enabled.
- `PostgresCardEconomyTests.Cumulative_upgrade_spend_is_refunded_once_and_last_copy_resets_level`, line 107: expected **1045**, actual **1033**.
- `RealNetworkEndToEndTests.Real_process_pvp_relic_replay_and_extraction_survive_forced_restart`, RealNetworkGameplayTests.cs line 96: expected and actual player IDs differ. This is an archived-HEAD failure, before migration; no claim of deterministic reproducibility beyond this observed run.

Log: `work/qa-baseline/dotnet-baseline-db.log`. Domain/server TRX files: `work/qa-baseline/qa-results/baseline-db_net10.0_20260928113328.trx` and `baseline-db_net10.0_20260928113417.trx`.

The warning-relaxed diagnostic does not clear the strict xUnit2012 build failure. QA has not modified frozen combat/economy rules or the failing assertions. These three observed baseline test failures must be distinguished from migration regressions in phase three. Production HTTP/TLS and performance measurements remain not executed.
