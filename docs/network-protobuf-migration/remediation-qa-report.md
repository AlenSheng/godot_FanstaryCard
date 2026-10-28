# Remediation integration QA — 2026-09-28

Actual executor: **Codex agent `/root/fc_realtime` performing the coordinator-assigned independent integration-QA role**. The attempt to resume `fc_qa` returned a runtime thread-limit error; that agent was not silently marked started and is not credited with this run. This QA phase read the protocol, economy and gameplay remediation reports and relevant changed sources. The same agent previously owned gameplay fixes, so this is separate integration execution, not an assertion of independent personnel review of its own gameplay work.

## Strict solution result

Starting remediation baseline `411ce66` plus all frozen server/Contracts/economy/gameplay changes. SDK10.0.400, .NET10.0.11, Windows, isolated local PostgreSQL18.6 on127.0.0.1:54329. Connection loaded from coordinator file into FANTASYCARD_TEST_POSTGRES without printing credentials. All PostgreSQL test schemas are disposable/local. No warning suppression, no test filters on this solution run, no skip substitutions.

Command from `server`:

```text
dotnet test FantasyCard.Server.slnx --artifacts-path .artifacts/remediation-qa --results-directory .artifacts/remediation-qa/results --logger "trx;LogFilePrefix=strict-solution" --logger "console;verbosity=minimal"
```

Exit **0**. TRX counters independently parsed:

| Assembly | Executed | Passed | Failed | Not executed |
| --- | ---: | ---: | ---: | ---: |
| Domain | 222 | 222 | 0 | 0 |
| Server | 239 | 239 | 0 | 0 |
| Total | 461 | 461 | 0 | 0 |

Server test duration2m38s. Raw log: `work/remediation-qa-solution.log`. TRX:

- `server/.artifacts/remediation-qa/results/strict-solution_net10.0_20260928123537.trx`
- `server/.artifacts/remediation-qa/results/strict-solution_net10.0_20260928123820.trx`

Includes repaired formula/14 new segment vectors, true craft-upgrade-refund transaction fixture, forward market history migration and concurrency/audit tests, HTTP protobuf boundary/business/authorization coverage, ticket expiry and ban lifecycle, PVP/relic/extraction/durable restart/replay, and four-human default-Protobuf preparation/ready/room entry. In particular ordinary-build `RoomActor_death_preserves_safe_assets_and_moves_losses_to_relic` passed14.68s; `RoomActor_extraction_commits_settlement_and_removes_terminal_room` passed2.04s. Protected-package behavior is a separate coordinator gate and cannot be inferred from these ordinary binaries.

## Actual Protobuf HTTP resale probe

After solution binaries had compiled, strengthened QA-owned `MigrationBusinessTests.cs`: seller lists equipment -> buyer buys -> buyer relists the **same equipment ID**, receives a different listing ID, then cancels the new listing. Assert two history rows, one Active while relisted, original row Sold, equipment MarketListed then Inventory, ownership remains buyer and exactly one original sale transaction survives. All requests use actual application/protobuf over a real loopback server with a real isolated database. Default JSON and query-token compatibility are false. This replaces the prior fresh-item workaround.

First strengthened run reached and passed the market assertions but later failed old matchmaking cancellation with typed409: Development's immediate bot-fill worker had already moved the ticket out of Queued. The test now explicitly uses the normal30-second matching delay so the cancellation operation is exercised. No endpoint success assertion was relaxed and production configuration was not edited.

Final command:

```text
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --artifacts-path .artifacts/remediation-qa --filter FullyQualifiedName~Migration_binary_business --results-directory .artifacts/remediation-qa/results --logger "trx;LogFileName=pb-same-equipment-resale-final.trx" --logger "console;verbosity=minimal"
```

Exit **0**, **1 passed,0 failed,0 skipped**,13s. Evidence: `work/remediation-qa-pb-resale-final.log`, `.artifacts/remediation-qa/results/pb-same-equipment-resale-final.trx`. Failed iteration preserved as `work/remediation-qa-pb-resale.log` and `pb-same-equipment-resale.trx`.

The461-test solution result predates only this subsequent QA-test enhancement; the enhancement was built with strict settings and run separately. Production sources were unchanged between these executions. This QA role changed no production source, committed nothing and deployed/pushed nothing.

## Limits and handoff

No Bootstrap timeout occurred in this solution run; earlier one-off timeout remains unrooted and is not declared fixed. A's120-request controlled diagnosis and new request/server logging are separate evidence. Godot optimization/actual client tests belong to C; protected publish/runtime and local TLS proxy gates belong to root. Their outcomes must be integrated by the coordinator rather than attributed to this role. No live Steam credentials or production deployment verification was performed. Runtime performance captured incidentally by a broad concurrent test suite is not used for performance improvement claims.

QA-owned changes this phase: `server/tests/FantasyCard.Server.Tests/ProtobufHttp/MigrationBusinessTests.cs` and this report. No new sub-agent was spawned.
