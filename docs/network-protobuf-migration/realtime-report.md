# Realtime migration implementation and evidence

Executor: real Codex agent `/root/fc_realtime`; 2026-09-28. Ownership: Realtime server directory plus new `server/tests/FantasyCard.Server.Tests/Realtime/ProtobufTicketTests.cs`.

## Implemented

- Authenticated `POST /api/v1/realtime/ticket`, registered frozen Protobuf boundary (Empty -> RealtimeTicketResponse), WritePolicy rate limit and no-store. Capacity rejection has HTTP 429 and Retry-After: 30.
- Cryptographically random 30-second tickets; only ticket/session hashes retained. Lock-protected atomic remove permits one consumer. Maximum 4096 outstanding entries, one pending ticket per player; new issue retires the previous pending ticket. Expired entries removed on issuance.
- Ticket player/session binding revalidated against IdentityRepository immediately before upgrade. Session expiration and player bans use the existing database check. Every accepted, rate-limited command revalidates before routing; idle connections check every five seconds. Registry reference check rejects superseded connections.
- Direct Authorization bearer upgrades supported. Query access_token requires explicit `Realtime:AllowLegacyAccessTokenQuery=true`, default false. Supplying an invalid ticket cannot fall back to another credential.
- Existing v1 routing, replay, request id, revision and resume logic retained. Existing multiple login-session policy retained; connecting a newer socket replaces the older socket, merely signing in does not delete other session rows.
- Upstream cumulative 16 KiB limit preserved; fragmented message completion has ten-second deadline, including empty nonfinal fragments. Binary frames only.
- Downstream 16 KiB budget; at most 32 pending senders, a five-second send deadline, single send/close gate, bounded 500 ms close output. Overflow aborts only the slow connection. No unbounded queued encoded messages.

## Measured budget and tests actually run

SDK supplied by coordinator: .NET SDK 10.0.400. Commands run from `server`, with SDK directory in DOTNET_ROOT/PATH.

Final command:

```text
dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --artifacts-path .artifacts/realtime --filter FullyQualifiedName~Realtime --results-directory .artifacts/realtime/results --logger trx;LogFileName=realtime.trx --logger console;verbosity=minimal
```

Actual result: **59 passed, 0 failed, 0 skipped**, process exit 0. This includes build of Contracts, Domain, Server and test assembly. Evidence: `server/.artifacts/realtime/results/realtime.trx`.

New tests verify 32 concurrent ticket consumers produce exactly one winner, session hash defensive copy/player binding, exact expiry, reissue invalidation, malformed ticket rejection/default compatibility setting, cumulative fragmented receive boundary and bounded pending sends. Existing tests cover connection replacement, slow presentation connection, replay/gap, resume and command duplicate semantics.

Real authoritative BattleRoom snapshot/projection with full 36-item backpack, four visible relic piles, and representative hand: **5313 bytes**. On-demand 41-item relic detail: **4497 bytes**. Values captured in the TRX output. This is a real domain-generated test fixture, not a production traffic capture or proof of every possible content combination. The outbound cap remains 16384 bytes; oversized data is explicitly closed rather than silently truncated or increasing the protocol budget.

Intermediate runs: existing 54/54 and initial added tests 57/57 passed. Subsequent added transport test initially failed compilation due to ambiguous array CopyTo overload; corrected using explicit spans. Next run had 58 pass / 1 failure: test assumed every already-queued send must throw after abort, but queued sends can correctly finish after seeing the closed socket. Assertion changed to require all callers settle and overflow aborts. Final 59/59 rerun passed. A test-writing script initially used wrong working directory, then an explicit UTF-8 read was needed on Windows; both failed before test file updates and were corrected. No failed run is counted as passing.

## Integration and remaining verification

AddRealtimeModule and MapRealtimeEndpoints contain ticket registration/mapping, so no new Program registration required beyond the coordinator's Protobuf HTTP middleware integration. Coordinator owns Hosting.Diagnostics log filtering; perimeter owner owns Caddy redaction. This code never logs credentials. Whole-stack no-credential logging is not proven by these unit tests.

QA phase must execute real HTTP Protobuf ticket -> WebSocket flow, single-use rejection at upgrade, expiry/revocation/bans during idle and active connections, ten-second slow fragment deadline, default query-token rejection, explicit compatibility mode, actual message type/size closes and client reconnection with a fresh ticket. The 59 tests are not a claim that these real network gates have run. No PostgreSQL or production connection was made by this agent's commands. No deploy, push, commit, reset, clean or stash performed.

Required `.agents/skills/server_create/SKILL.md` is missing in this tree; recorded according to PLAN. Valid server AGENTS and plan/contract/network documents were read. Shared Program/config/contracts/client files were not edited.

## Final review correction: malformed frame budget

The complete-frame limiter now executes before protobuf decoding via `RealtimeFrameReader`, after close/type/size/fragment-timeout checks. Malformed frames consume the same budget as valid commands. Invalid-message replies are therefore limited by admitted frames, and over-budget rate-limit notices remain at most one per second. Database authentication remains after admission and successful decode.

Added `MalformedFrameFloodConsumesBudgetAndBoundsErrorResponses`: send 100 malformed varint frames to the actual boundary reader with a three-frame budget; observed three invalid-message replies, one rate-limit reply, 97 rate-limited frames, no commands. A subsequent valid ping is blocked in the same window and accepted after one second. This tests the production reader used by the endpoint, not a duplicate limiter simulation.

Reran the same Realtime test command above after this change: **60 passed, 0 failed, 0 skipped**, exit 0; updated `.artifacts/realtime/results/realtime.trx`. Added owned file `server/src/FantasyCard.Server/Realtime/RealtimeFrameReader.cs`; updated endpoint and own test only. This supersedes the earlier final count of 59.
