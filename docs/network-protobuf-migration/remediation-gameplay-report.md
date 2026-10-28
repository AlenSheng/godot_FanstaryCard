# Gameplay remediation evidence — 2026-09-28

Executor: actual Codex agent `/root/fc_realtime`; baseline HEAD `411ce66`. No production combat algorithm changed, no push/deploy/reset/stash.

## Rules decision and formula regression

Read server AGENTS, GDD combat/network sections, SERVER_SPEC, SERVER_0_TO_1_GUIDE and migration QA evidence. Referenced `.agents/skills/server_create/SKILL.md` remains missing. Initial review found a genuine documentation conflict: original user commit `54cab7f` deliberately changed CombatResolver and CombatAuthoritativeRulesTests to first-card core, 20% additional core stacks and per-card rounding, while GDD and one equipment test retained nonlinear resonance and aggregate rounding. Work on that conflict paused while independent PVP work continued.

User explicitly chose **“保留当前代码规则，同步文档与旧测试（推荐）”** through coordinator. Thus CombatResolver is unchanged. Equipment test now checks K=1.4, core count3, elemental segments 46/32 and piercing3, totals49/35. Fourteen additional parameter rows independently fix the GDD A/A2/A4/A5 equipment/resistance examples as elemental and direct segments (including upgraded armor), avoiding merely replacing 54 with49. GDD current formula, examples, active overview/UI/acceptance and derived equipment comparisons were synchronized; historical version entries retained. Historical unmeasured win-rate percentages and week-based damage guesses no longer masquerade as present-rule predictions.

Actual full Domain command (cwd server):

```text
dotnet test tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj --artifacts-path .artifacts/remediation-gameplay --results-directory .artifacts/remediation-gameplay/results --logger "trx;LogFileName=domain-final.trx" --logger "console;verbosity=minimal"
```

**222 passed, 0 failed, 0 skipped**, exit0. Prior run before 14 added vectors:208/208. SDK10.0.400 from coordinator, runtime10.0.11.

## Full gameplay network chain

Original failure was NOT OpponentId (line86): retained original QA log shows event-ID equality at line96. Mutation returns multiple messages sharing requestId; helper returned the queued original room.snapshot on immediate retry. Updated helper matches requestId AND original event type for mutation retries while retaining strict event-ID equality and command-rejection detection. Server routing/replay code unchanged.

Actual chain now runs PVP kill, duplicate combat request, persisted equipment into relic, relic.read/take for gold and equipment with exact duplicate-event checks, 36 gold inventory, extraction start and duplicate, durable mid-extraction checkpoint, abrupt process-tree termination, restart to completed settlement/equipment ownership, then a second restart with unchanged wallet/settlement counts.

Added four-human test with default PB/legacy JSON disabled/query-token disabled: all four accounts log in via real PB HTTP; bootstrap/loadout -> preparation -> ticket -> authenticated WSS -> enqueue; all receive ready-required/confirm via binary room.ready; DB reaches Running; four player-specific PVE room snapshots and exactly four non-bot match rows asserted. Fixture sets BotFillDelaySeconds=30 because Development defaults to immediate bot fill; it does not alter production defaults.

Actual final combined command (cwd server, isolated loopback PostgreSQL18.6:54329 connection file via FANTASYCARD_TEST_POSTGRES, never printed):

```text
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --artifacts-path .artifacts/remediation-gameplay --filter "FullyQualifiedName~Real_default_protobuf_preparation|FullyQualifiedName~Real_process_pvp_relic" --results-directory .artifacts/remediation-gameplay/results --logger "trx;LogFileName=gameplay-final.trx" --logger "console;verbosity=normal"
```

**2 passed, 0 failed, 0 skipped**, exit0,19.5s overall (PVP10s, PB-ready5s). Evidence `.artifacts/remediation-gameplay/results/gameplay-final.trx`. Initial corrected standalone PVP also1/1 passed13s (`pvp-chain.trx`); ready with proper fixture config1/1 passed5s (`pb-ready-four-human.trx`).

Failures retained: first new ready run timed out during Bootstrap HTTP (60s), `pb-ready.trx`; cause not established by this agent. Second run completed all24 HTTP calls but expected4 ready participants/got1 due to Development's immediate botfill setting (`pb-ready-retry.trx`); explicit30-second test fixture corrected it. Later runs did not reproduce Bootstrap hang; this does NOT prove the transient fixed. Protocol agent coordinating PG/activity and persistent process diagnostics. Test Call now logs begin/headers/body elapsed times with ResponseHeadersRead, without credentials, for subsequent diagnosis.

One GDD-edit stdin script failed its UTF-8 parse before file mutation; corrected using explicit UTF-8 file operations. No test assertion was relaxed to hide gameplay behavior. Shared economy fixes and full solution QA are other agents' work, not claimed here.

Changed files: GDD.md; server/tests/FantasyCard.Domain.Tests/Combat/EquipmentCombatRulesTests.cs; server/tests/FantasyCard.Server.Tests/EndToEnd/RealNetworkGameplayTests.cs; qa-report.md (append-only historical diagnosis correction); this report.
