# A05 frozen real-process receipt proposals

Production source is `f812879e4518fd09bf22656451cb563d62940298`. A05.2/.3 are submitted for independent MAIN acceptance; A05.1 remains Partial. Nine original primary expectations Passed. Full fresh canonical assembly: Server295/0/0 and Domain317/0/0. The separate focused matrix is 3Pass/1Fail, and the later controlled causal probe is 1Fail. No task is signed Accepted here.

The failure is an actual recovery-M old Bootstrap poll returning during the production ACK await and refilling the visible receipt. Actual ACK200 and a newer Bootstrap confirm durable completion, but the old client display remains. A05.1 requires durable/visible terminal consistency, so its full criterion fails. This counterexample does not demonstrate extra asset credit, ledger corruption, or an old callback clearing A's actual new N. Those distinct .2/.3 postconditions have actual Program/Godot/PG/readonly-audit evidence. Independent MAIN must assess that separation, not infer it from the full-suite green result.

ROOT independently rehashed all1,678 local evidence files/278,078,413bytes, all6,445 original tracked non-bin/obj source files, actual32 build/config entries and all9 harness files. Every original case's canonical setup/expected and referenced receipt line was checked. [Derived checks](DERIVED_CHECKS.json) retain actual TRX counts, the failed test names, controlled client phases and eight readonly residue/conservation checks without account rows. [Original manifest](ORIGINAL_LOCAL_RAW_MANIFEST.json) gives every historical raw path/size/hash. Raw PB, SQL account rows, host/client logs and authority contexts remain in the sealed authorized local artifact; they are not copied into Git. Historic raw is unchanged. Four unrelated raw ZIPs remain paused and local.

[Reports](READY_FOR_INDEPENDENT_ACCEPTANCE.json) contain all canonical fields and S0–S5 receipts. Native image digest, common monotonic cutoff and independent reviewer are null with reasons. The negative-control earlier DLL hash and exact original causal shell wrapper were not frozen; [provenance gaps](MISSING_FACTS.json) remain explicit. The proposed one-line `client/state/game_store.gd` await guard is unapplied and untested; it requires parent coordination with the fixed UI candidate.

For independent replay, copy this directory from the fixed receipt commit and use the preparation helper. It archives exact f812 into a new directory and overlays only the seven canonical test files. It performs no tests or service operation. Replace the example paths with new private directories; never reuse the sealed original artifact.

```bash
source /workspace/relicround-env/activate.sh
python /tmp/a05-packet/prepare_replay.py --repo /workspace/godot_FanstaryCard --output /tmp/a05-independent/source
initdb -D /tmp/a05-independent/pg -A trust --no-locale -E UTF8
mkdir /tmp/a05-independent/socket
pg_ctl -D /tmp/a05-independent/pg -l /tmp/a05-independent/pg.log -o "-k /tmp/a05-independent/socket -p 55517 -h ''" start
export FANTASYCARD_TEST_POSTGRES='Host=/tmp/a05-independent/socket;Port=55517;Database=postgres;Username=agent;Pooling=true;Maximum Pool Size=8'
export FANTASYCARD_PROCESS_SERVER_DLL=/tmp/a05-independent/source/server/src/FantasyCard.Server/bin/Release/net10.0/FantasyCard.Server.dll
export FANTASYCARD_PROCESS_EVIDENCE=/tmp/a05-independent/canonical
cd /tmp/a05-independent/source/server
dotnet build FantasyCard.Server.slnx -c Release
dotnet test tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj -c Release --no-build --logger 'trx;LogFileName=domain.trx' --results-directory /tmp/a05-independent/domain
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --no-build --filter FullyQualifiedName~ProcessLifecycleRecoveryTests.A05_ --logger 'trx;LogFileName=a05.trx' --results-directory /tmp/a05-independent/canonical
```

The minimal original matrix has four entries covering nine canonical cases; inspect actual setup, all raw and asset/route audits. The preserved focused failure is a possible result under frozen f812 and must be retained, not bypassed. For the whole required C-SERVER suite omit the filter and retain a separate output directory (the original fresh assembly had295 entries, zero skip). The process DLL/config outputs must remain inside the actual source tree. `A3GAME_GODOT_EXECUTABLE` is set by activation; missing PG/Godot skips invalidate this profile.

For the controlled positive P0 replay, materialize another new source with `prepare_replay.py --causal`, build there with the same local PG/Godot environment, point `FANTASYCARD_PROCESS_SERVER_DLL` to that source's Release DLL and use a new evidence directory, then run:

```bash
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj -c Release --no-build --filter FullyQualifiedName~Frozen_f812_actual_poll_return_during_ACK_must_not_restore_completed_receipt --logger 'trx;LogFileName=causal.trx' --results-directory /tmp/a05-independent/causal
```

Against f812 this correctness assertion is expected to fail (exit1) after valid recovery-M/real-PB setup, with `counterexample_confirmed=true`, `stale_after_ack=true`, actual ACK and complete after-audit. The original negative ordinary-terminal control and red raw remain locally indexed; a later corrected negative assembly cannot be claimed as that historical run. This later causal build contains two extra test files and is not the original295 assembly. No timeout, retry budget or assertion was weakened.

After preserving new raw, verify no owned host/Godot remains, inspect owned schemas/connections and stop only this private PG with `pg_ctl -D /tmp/a05-independent/pg -m fast stop`. Original cleanup matched50 host starts/stops; all recorded host/Godot PIDs absent, owned PG stopped. These commands document a replay recipe; ROOT did not re-execute the full matrix merely to write this receipt. No CI/LIVE/human requirement is added to OFFLINE/POSTGRES/AUDIT contracts.
