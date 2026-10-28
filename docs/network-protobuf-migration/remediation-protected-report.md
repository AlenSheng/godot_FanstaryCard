# Protected settlement test diagnosis (2026-09-28)

## Reproduced cause and change

The original protected full validation reported 459/461 passing (coordinator evidence: private `server-validation-iiysbsn9/tests.log`). An independent copy of the protected test binaries was instrumented with Mono.Cecil to log integer `Assert.Equal` actual operands immediately before assertions. Production assemblies were not modified. Running only the two cases reproduced death failure and extraction success.

Death failed at `SELECT count(*) FROM match_settlements WHERE match_id=$1 AND result='Dead'`: actual 0, expected 1, before the settlement worker runs. Extraction returned settlement count 1, pending holds 3, worker count 1, wallet 23, potion count 1, and passed. This rules out the proposed worker-swallowed-exception explanation for this reproduction.

`RoomActor.CommandWorkItem.Execute` completes its task before the reader enqueues observers; persistence executes independently. Awaiting a snapshot establishes authoritative room state, not committed database state. The test had raced asynchronous settlement persistence. Settlement and holds are inserted in one database transaction.

Only `server/tests/FantasyCard.Server.Tests/Persistence/PostgresRuntimeIntegrationTests.cs` changed: both cases now wait for their existing settlement count condition, then execute all original assertions. The helper has a 10-second linked cancellation deadline, cancellable SQL and 20 ms condition polling; deadline failure includes query and last value. No fixed settle sleep, relaxed assertion, or production synchronization was introduced.

## Commands and evidence

- `dotnet vstest work/client-protected-tests/FantasyCard.Server.Tests.dll --TestCaseFilter:FullyQualifiedName~RoomActor_death_preserves|FullyQualifiedName~RoomActor_extraction --Logger:console;verbosity=normal --ResultsDirectory:work/client-protected-probe/results`: diagnostic pre-fix copy, 1 passed / 1 failed. Logs `work/client-protected-probe/{tests,assertions}.log` under the repository. Temporary copies and IL probe are untracked diagnostics, not deliverables.
- Initial post-fix command `dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --filter <same two cases> --no-restore`: did not reach tests; NETSDK1064 missing Microsoft.Extensions.Configuration.Binder 10.0.0 in pre-existing restore cache. It is not a test failure or pass.
- Retried using a separate `.artifacts/client-protected-fix` artifacts path and restore. Result appended below.

The coordinator owns rebuilding the final protected package and its complete strict validation; this report does not claim that rerun passed before evidence is available.
`dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --artifacts-path .artifacts/client-protected-fix --filter "FullyQualifiedName~RoomActor_death_preserves|FullyQualifiedName~RoomActor_extraction" --logger "console;verbosity=normal"`: restore/build succeeded; 2/2 passed, zero skipped, 19.8658 seconds. Actual evidence: repository `work/client-protected-probe/fixed-tests-restored.log`.

## Coordinator final package verification

After both test fixes and the strengthened PB resale case were frozen, root reran export_protected_server.export_server() and validate_protected_server.validate() with ignored task-local PRIVATE staging, SDK10.0.400 and Obfuscar2.2.50. Actual operations: full solution Release build, server Release publish, Obfuscar for three production assemblies plus test reference rebinding. The validator checked exact protected assembly hashes, initialized a fresh loopback PostgreSQL cluster and ran dotnet vstest on both protected test assemblies without filters. No warnings or errors were suppressed.

Final package builds/server-protected/server-av91ig_u: **461/461 passed,0 failed,0 skipped** (Server239, Domain222), exit0. Server duration3m31s. Evidence in task workspace work/remediation-tools/server-validation-uiqg7n3m/{tests.log,verification.json,results/*.trx}; export log work/remediation-protected-final.log. Initial failure evidence remains server-validation-iiysbsn9 (459 pass/2 fail), with its candidate marker intact. Only the validated final package's marker was removed; protection-verification.json records all assembly hashes. Both validator-owned database clusters stopped in finally.

Root ran python tools/verify_local_tls_proxy.py --dotnet <task-local-dotnet> --server-dll builds/server-protected/server-av91ig_u/FantasyCard.Server.dll --psql <task-local-psql> --connection-file <private-loopback-file> --caddy server/.artifacts/perimeter/caddy.exe --work-dir work/remediation-tls-final (absolute executable/DLL arguments). **20/20 passed**, exit0: genuine certificate/IP-SAN validation, PB login/bootstrap, no-store/nosniff, short ticket, binary WSS session/pong, admin isolation/authentication, origin denial, upstream502 and credential-free logs. Owned processes/schema cleaned up. Evidence work/remediation-tls-final/results.json and work/remediation-tls-final-run.log.

No Docker build, Linux runtime, live Steam, public certificate or cloud ACL is claimed. This does not erase the separately recorded intermittent Bootstrap timeouts. Two initial report-update stdin scripts failed encoding before any file write; file patch/ASCII script succeeded, with no source or test impact.
