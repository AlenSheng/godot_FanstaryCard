# Economy remediation evidence — 2026-09-28

Executor: real agent `/root/fc_server_api`, resumed by coordinator with explicit authority to fix the reported economic defects. Worktree `F:\GitHubFiles\godot_FanstaryCard-protobuf`, starting HEAD `411ce66`. Read migration QA/server reports and applicable server instructions/design references. Missing historical server_create skill remains previously recorded. No push, deployment, merge, reset, stash, production database access, or extra child agent.

## Market relisting root cause and repair

GDD 6.4 permits unbound inventory equipment listing and returns unsold equipment after 48 hours. GDD 6.6 sends bought equipment to the buyer's inventory. Nothing makes a previously sold/cancelled/expired item permanently untradeable. V005 instead made `market_listings.equipment_id` globally UNIQUE, so a retained historical row prevented the legitimate next listing and yielded PostgreSQL 23505 / HTTP 500.

New forward migration `V029__market_listing_history.sql` drops only that old uniqueness constraint and creates `ux_market_listings_active_equipment`, unique on equipment_id WHERE status='Active'. Sold/Cancelled/Expired history, transaction foreign keys, request-key uniqueness, player locking and ownership/location transaction code remain intact. Original V001–V028 source/checksums were not edited. No EconomyRepository business transaction change was needed.

Real PostgreSQL tests cover:

- Restore V028's old constraint on populated isolated sold history, remove only that isolated fixture's V029 migration record, run the actual migrator, rerun it idempotently, verify V005 checksum and sale transaction/history survive.
- Sell -> buyer relists -> original owner buys back. Two distinct sold rows and two transactions remain, fees/ledger reconcile. Replaying the original purchase while the item is relisted does not debit again, move it, or change ownership/location. Repeated resale purchase likewise charges once.
- Cancel/relist and expire/relist retain both history and exactly one Active row. Replayed cancellation of an old listing cannot cancel a later listing or restore its currently listed equipment.
- Four different-key concurrent listings on one item produce exactly one success; four same-key requests return one logical listing. Changed payload with same key rejects; a direct duplicate Active insertion is rejected by the new partial unique index.

## Additional genuine reconciliation bug

The new resale test exposed an existing audit assumption: `SoldListingMismatchCount` compared EVERY historical buyer against the equipment's CURRENT owner and required CURRENT location='Inventory'. Legitimate resale and wearing the equipment therefore falsely marked the economy unhealthy.

With coordinator approval, `EconomyReconciliation.cs` now verifies immutable sale facts: a Sold listing has its transaction, and transaction seller/price agree with that listing. The transaction's listing foreign key binds the historical equipment. Active-listing owner/location and orphan MarketListed checks, transaction arithmetic/buyer-vs-seller checks, negative balances and ledger chain checks remain. Tests prove normal resale and subsequent Equipped state are healthy; changing historical sale price (while preserving transaction sum arithmetic) and removing a historical transaction are both detected by SoldListingMismatchCount.

## Refund failure: stale fixture, not a production refund change

Evidence: GDD 4.6.1 common Blue unlock=50, upgrades +1/+2/+3 cost 12/24/48. `server/docs/CLIENT_INTEGRATION.md` explicitly defines dismantle refund `floor((card cost + cumulative upgrade soul spend)/4)`; existing CardEconomyRules computes this, and the old failing test itself asserted UpgradeSoulSpent=84 and SoulAmount=33. Its artificial seed left wallet=1000 and should yield 1033, yet expected 1045 (an unexplained extra 12). No production price/refund formula was changed.

Instead of just replacing 1045 with 1033, the fixture now performs the real chain: start 1000 -> craft -50 -> three upgrades -12/-24/-48 -> dismantle +33 = 899; replay leaves five ledger entries and net delta -101; the card resets/unlocks=false; recraft costs 50, leaves 849 and level-zero refund=12. It verifies persisted wallet, ledger sum and reconciliation, plus the explicit 33 and 84 values. The +4/+5 old-doc duplicate-card mismatch is outside this defect and was not used to redefine rules.

## Actual verification

SDK 10.0.400, strict warnings-as-errors unchanged, local PostgreSQL loopback 54329 with per-test disposable schemas. Connection was read from the coordinator's task-local connection file and not printed. Working directory: `server`.

Final command:

```text
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --artifacts-path .artifacts/remediation-economy --filter 'FullyQualifiedName~PostgresMarketRelistingTests|FullyQualifiedName~PostgresCardEconomyTests|FullyQualifiedName~PostgresMigrationTests|FullyQualifiedName~EconomyReconciliation' --logger 'trx;LogFileName=economy-remediation-verified.trx' --results-directory .artifacts/remediation-economy/results -v minimal
```

**PASS: 11 passed, 0 failed, 0 skipped, 18 seconds.** Build completed without warnings/errors. TRX: `server/.artifacts/remediation-economy/results/economy-remediation-verified.trx`.

Failed iterations retained separately: first 9-test run had two test timestamp equality failures because PostgreSQL stores microseconds while DateTimeOffset includes 100ns ticks; comparison now normalizes only CreatedAt/ExpiresAt to actual database precision and keeps other fields fully equal. Next run exposed the real audit bug above (8/9 passed). A patch invocation used duplicated server/server path and failed before editing; its accidentally continued test still exercised old audit SQL (10/11 passed). Correct path applied, final 11/11 passed. Earlier TRXs are economy-remediation.trx, economy-remediation-final.trx, economy-remediation-reviewed.trx; they are failures, not claimed passes.

## Changed files / remaining coordinator gates

- server/src/FantasyCard.Server/Persistence/Migrations/V029__market_listing_history.sql
- server/src/FantasyCard.Server/Progression/EconomyReconciliation.cs
- server/tests/FantasyCard.Server.Tests/Persistence/PostgresMarketRelistingTests.cs
- server/tests/FantasyCard.Server.Tests/Persistence/PostgresCardEconomyTests.cs
- docs/network-protobuf-migration/remediation-economy-report.md

Coordinator/QA will rerun full solution plus actual PB HTTP purchase->same-item relist. This agent's evidence is actual repository + PostgreSQL economic behavior and migration/reconciliation, not a claim that the complete cross-client suite or production rollout is done. Once historical duplicates exist, rollback cannot reinstate the old global UNIQUE without losing valid history; do not downgrade the database schema by deleting rows. Forward migration has only been exercised in isolated local schemas.
