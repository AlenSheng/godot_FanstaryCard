# Server API migration execution report

Executor: real Codex agent `/root/fc_server_api`, batch two, 2026-09-28. Worktree `F:\GitHubFiles\godot_FanstaryCard-protobuf`. No commit, push, deployment, reset, clean or stash by this agent.

## Implemented

- All non-realtime registered HTTP endpoint groups in Identity, Bootstrap, Players, Progression/Economy, Mail, Matchmaking/Preparation and Settlement now use a typed `GameBody<T>` binder and `ProtobufHttpFilter`. Existing repositories, domain validation, transaction and normalized DTO idempotency paths remain in use.
- New `ProtobufHttp/` contains binary request binding, explicit legacy JSON option, Accept quality/specificity negotiation, direct DTO-to-Protobuf result writing, middleware translation for limiter/exception errors, private response headers and pagination headers. No JSON is embedded in binary messages and malformed requests are not replayed.
- Default `ProtobufHttp:AllowLegacyJson=false`. Enable explicitly for legacy rollout. Missing Accept chooses PB by default; when compatibility is enabled an old JSON request or old bodyless GET still receives JSON. Explicit Accept quality preferences and explicit `q=0` override wildcard matching.
- PB request/response maximum 2 MiB; mapper depth 24, repeated fields 4096, string size 128 KiB. Body reads have a 15-second timeout and cancellation. The response capture stream is bounded. HTTP limit does not alter WSS limits. Empty-contract endpoints validate supplied bodies, including malformed PB and disabled JSON, before business execution.
- Typed HTTP errors preserve 400/401/403/409/413/415/429 and transport status, trace ID, Retry-After. Successful 204 carries no body. Accepted/Created Location property is copied. Binary responses set no-store, nosniff and Vary: Accept, including errors after Response.Clear.
- With coordinator approval, only the read methods of EconomyRepository and MailRepository gained SQL pagination. Default/max page size is 200; `limit` 1..200 and `offset` 0..1000000, invalid values yield 400. Stable timestamp plus UUID ordering. Mail unread count is global, independently queried.
- Full page returns `X-Market-Next-Offset` or `X-Mail-Next-Offset`; partial page omits it. A full final page can be followed by an empty page. Dedicated `/market` and `/mail` retrieve subsequent pages; `/market/context` uses `listings`, `/economy/context` uses `market`, Bootstrap uses `market` and `mail.items`. Bootstrap always starts at page 0, size 200. Client agent was informed and implements aggregation.

## Coordinator integration

Coordinator added `AddProtobufHttp(configuration)`, middleware outside exception handler and rate limiter, and exception status selection for BadHttpRequestException. Realtime ticket endpoint owner must attach ProtobufHttpFilter. Existing real-network tests explicitly enable legacy compatibility only inside their process helper. Production settings remain explicit false.

## Commands and actual evidence

All .NET commands ran from `server`, with local supplied SDK 10.0.400 (`DOTNET_ROOT`/PATH), and isolated outputs `.artifacts/server-api`. DB connection came from the supplied local test-connection file without printing it; tests allocate an isolated schema and do not use production.

1. `dotnet build src/FantasyCard.Server/FantasyCard.Server.csproj --artifacts-path .artifacts/server-api -v minimal`: PASS, 0 warnings/errors. Initial attempt failed because a new middleware file was written to a duplicated `server/server` path (write failed, no stray file) and CA1000 required an explicit rationale for ASP.NET static BindAsync. Corrected, rebuilt successfully.
2. `dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --artifacts-path .artifacts/server-api --filter FullyQualifiedName~ServerApiBoundaryTests -v minimal`: initial 6/6 PASS.
3. Final `dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --artifacts-path .artifacts/server-api --filter 'FullyQualifiedName~ServerApiBoundaryTests|FullyQualifiedName~Protobuf_real_database' -v minimal`: **11 passed, 0 failed, 0 skipped**, 5 seconds test duration. This builds the actual integrated server as well.

Boundary cases: actual loopback Kestrel binary binding; signed int64 maximum; malformed request 400; default JSON rejection 415; q negotiation and explicit exclusion; typed 401/403/409; no-store; middleware-origin 429 and RetryAfter=12; empty 204; malformed body on Empty DELETE rejected.

Actual server + PostgreSQL vertical flow: PB local login; Bootstrap/profile/cards/decks/inventory/shop/economy context/market context/mail reads; selected-class profile update; deck write; PB purchase then same normalized JSON operation/key returns original outcome and wallet is charged once; 205 market entries and 205 mails yield 200+5 disjoint pages; mail global unreadCount stays 205; Bootstrap advertises both page continuations; invalid limit and malformed PB return typed 400.

Test-development failures were not counted as passes: attempted local account rename correctly returned existing 409 identity rule (test changed to selected class); 7-character test idempotency key correctly returned 400 (test key extended); generated mail field is Id, not MailId (compile fixed); parameterized multiple seed statements were rejected by PostgreSQL (test split statements). One test run did not finish promptly and its own verified process was stopped; the DB test now has a 60-second total timeout. The next build retried locked output copying three times while that test process exited, then the final 11 tests passed.

## Remaining gates and limits

- Independent full integration/performance and Godot end-to-end gates belong to batch-three QA; this report does not claim them passed.
- This task tested representative success/error/write/read paths. Real Steam platform verification was not executed; provider request format remains unchanged.
- Inventory is domain-bounded: the read includes only Inventory/Equipped, 50 storage slots plus at most 15 equipped slots (three classes with five slots each). Its snapshot does not need pagination merely to satisfy the network migration. Transport ceilings remain defense in depth for corrupt/out-of-band data.
- Offset paging is not a transactionally frozen snapshot across requests: concurrent market/mail inserts or removal can shift later pages. Stable ordering avoids tie nondeterminism but a future cursor/snapshot contract would improve consistency.
- LocalAuthPolicy's pre-existing managed-login exception was retained; no identity/security behavior was silently redefined during serialization migration.


## Final review: mail reward response budget

Coordinator identified claim-all as an unbounded write response. Fixed within MailRepository's existing transaction: pending query stops at 4097 (a detection row, never silently truncated); >4096 rejects with 413. All per-mail granted arrays and the exact typed candidate response are validated and CalculateSize checked against 2 MiB before the first GrantAsync/update/idempotency write. Single-mail claim performs the same response preflight; persisted replay responses are also checked. Exceptions roll back, preserving all-or-nothing rewards. No reward amount, eligibility, or mail ordering changed. `ProtobufHttp/GameResponseBudget.cs` centralizes the preflight.

Re-ran the same final filtered command: **11 passed, 0 failed, 0 skipped**, 4 seconds, including expanded actual PostgreSQL assertions for three rejection shapes: 4097 mails; 4000 mails whose individually valid attachment strings produce a >2 MiB response; one mail with 4097 attachments. Every claim-all returns typed 413 with unchanged wallet, no read/claimed marks, and zero successful mail.claim-all idempotency records. The oversized single-mail case also returns 413 with no wallet change or mail.claim idempotency record. These tests use only their isolated schema.

Other write-response review: profile/card/equipment/shop purchase/market purchase/settlement acknowledgement are bounded individual DTOs; deck has 20 cards, loadout five slots, preparation bounded deck/equipment data, matchmaking bounded party state, shop refresh returns the configured small catalog. Mail claim-all was the unbounded response found; individual mail attachments share the new preflight to protect historical/admin payloads. Inventory's 50 + 15 domain capacity is clarified above; no mechanical inventory paging is proposed.
