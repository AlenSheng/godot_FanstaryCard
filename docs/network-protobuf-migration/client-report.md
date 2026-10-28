# fc_client execution report

Agent: `/root/fc_client`. Worktree: `F:\GitHubFiles\godot_FanstaryCard-protobuf`. No commit/push/deploy. Frozen schemas/registry were consumed without editing generated files. Existing UI layout and user changes were preserved; UI edits below only adapt network object shapes.

## Implemented

- `client/network/protobuf.gd`: selectable realtime/HTTP schema, independent 16 KiB / 2 MiB body limits, depth 24, 4096 repeated elements, 128 KiB HTTP strings. Packed and unpacked scalar occurrences preserve order, signed int32/int64 extremes remain integers, optional presence is preserved, singular nested messages merge, unknown fields skip, malformed tags/lengths/varints/wires and invalid UTF-8 reject. Outbound encoding validates types/ranges/budgets.
- `client/network/http_protocol.gd`: exact method/template registry including GUID constraints, trailing slash/query handling, explicit perimeter list, typed protobuf HTTP errors, 204, Content-Type validation, recursive camelCase conversion. Nullable DTO/message absence becomes null; equipment slots retain null positions. Sparse ShopProductPayload deliberately omits absent properties to preserve UI `has()` and `get(default)` semantics. Only CardEffect decimal fields become floats; money/version remain int64.
- `client/network/gateway.gd`: `request_raw` for game traffic, Accept/Content-Type application/protobuf, bounded reception, same bytes/key across retries, integer Retry-After handling, terminal invalid-response errors with no JSON fallback, session generation and old callback suppression. Paged market/mail responses aggregate before publishing, including embedded bootstrap/economy/context lists. Limit 4096 rows per collection, 16 MiB aggregate bytes, max 32 continuation pages, monotonic cursors; errors return no partial data. Ticket uses authenticated POST then `?ticket=`, never access_token fallback; async ticket generation guards account switches.
- `client/state/game_store.gd`: typed shop payload, null-safe optional shop/snapshot/login player access, reject incomplete required lobby messages before UI publication.
- `client/ui/main.gd`, `client/ui/reference_ui.gd`: typed shop payload consumers, sparse optional fields; main settlement/details and market equipment null guards.
- `client/ui/exploration_view.gd`, `client/ui/inventory_view.gd`: null-safe settlement/equipment access. No layout/style/animation edits.
- New test files: `client/tests/test_http_protobuf_client.gd`, `test_http_protobuf_transport.gd`, `http_protobuf_fixture.py`, `run_http_protobuf_client.py`.

## Actual commands and evidence

Ran from worktree:

```powershell
python client/tests/run_http_protobuf_client.py --godot 'F:\GitHubFiles\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe'
git diff --check -- client/network client/state client/ui
```

Final runner exit 0. Godot 4.7.2 stable official `ed1daf0bf`, Python 3.9. Runner creates isolated project under `work/client-fixture`, with no production autoload, copies frozen golden vectors, starts only `127.0.0.1:38971` fixture, and stops it afterward. Engine ERROR output is treated as failure independently from process exit.

- Isolated editor import: exit 0, no engine errors.
- Codec/registry/DTO checks: **103 assertions, zero failures**. Eight official vectors, semantic encode/decode, packed interleaving, signed extrema, optional zero/absence, singular message merge, unknown/malformed handling, body/string/collection budgets, null and sparse-payload presentation shape, every 46 route template/method, strict wrong method/GUID/extra-path rejection, retained realtime regression test.
- Actual HTTP/WebSocket loopback transport: **18 assertions, zero failures**. Binary login/bootstrap/profile, large int64, standalone and embedded list pagination, invalid cursor and aggregate-limit rejection without partial data, 429 fixed-body/key retry, 204, malformed successful write response sent once, HTML proxy error without JSON fallback, ticket URL excludes bearer, old delayed 401 cannot clear the next session.
- Logs: `work/client-fixture/import.log`, `codec.log`, `transport.log`, `results.json`.
- `git diff --check`: exit 0. Git warned LF will normalize to CRLF in protobuf.gd; no whitespace errors.

Earlier transport attempt produced Godot `raw_to_base64` errors for empty protobuf bodies and expected rejected fake HTTP/1.0 websocket handshake even though assertions passed. Both were corrected (guard empty bodies; fixture performs valid upgrade/normal close), then rerun with no engine errors. Those earlier runs are not clean passes.

## Boundaries and remaining gates

- This is client boundary proof using a local synthetic fixture, not real database/Steam or full room gameplay integration. Transactional economic deduplication, server ticket expiry/single-use, live login-to-room/reconnect/replay and actual performance comparisons belong to independent QA.
- The existing full application project was not imported/launched by this agent; coordinator/QA should compile and exercise all shipped UI scripts with a temporary loopback server setting. Never use the shipped production URL for tests.
- Older `session_integration.gd` uses JSON and unregistered `/fixture/*`, `/unauthorized` paths and therefore needs a protobuf-aware fixture update for the new explicit boundary. `art_preview.gd` still constructs/parses legacy string product mock payloads; update those preview fixtures if they are part of the gate. Runtime game requests do not have this legacy path.
- HTTP Retry-After numeric seconds supported; RFC-date Retry-After remains a compatibility follow-up if a proxy emits it (current server uses numeric seconds).
- Pagination yields an explicit error beyond client budget rather than silently dropping rows; no new UI controls were added.

## Production request callsite inventory

Every production `gateway.request` remains routed through the exact registry; data/schema mapping is centralized. List follows from source scan (test-only fixture calls excluded). This is static coverage and must not be confused with endpoint runtime proof.
client/state\game_store.gd:277:				var result: Dictionary = await gateway.request("/api/v1/auth/steam" if steam_login else "/api/v1/auth/local", HTTPClient.METHOD_POST, sign_in)
client/state\game_store.gd:300:	var response: Dictionary = await gateway.request("/api/v1/client-info")
client/state\game_store.gd:314:	var result: Dictionary = await gateway.request("/api/v1/bootstrap")
client/state\game_store.gd:337:		var economy: Dictionary = await gateway.request("/api/v1/economy/context")
client/state\game_store.gd:356:			var active: Dictionary = await gateway.request("/api/v1/preparations", HTTPClient.METHOD_GET, null, [404])
client/state\game_store.gd:404:		var result: Dictionary = await gateway.request(paths[module], HTTPClient.METHOD_GET, null, [404])
client/state\game_store.gd:419:	var result: Dictionary = await gateway.request("/api/v1/mail", HTTPClient.METHOD_GET, null, [404])
client/state\game_store.gd:426:	var result: Dictionary = await gateway.request("/api/v1/mail/%s/read" % id.uri_encode(), HTTPClient.METHOD_POST, {})
client/state\game_store.gd:440:	var result: Dictionary = await gateway.request("/api/v1/mail/%s/claim" % id.uri_encode(), HTTPClient.METHOD_POST, {})
client/state\game_store.gd:452:	var result: Dictionary = await gateway.request("/api/v1/mail/claim-all", HTTPClient.METHOD_POST, {})
client/state\game_store.gd:514:	var result: Dictionary = await gateway.request("/api/v1/mail/read-all", HTTPClient.METHOD_POST, {})
client/state\game_store.gd:524:	var result: Dictionary = await gateway.request("/api/v1/mail/%s" % id.uri_encode(), HTTPClient.METHOD_DELETE, {})
client/state\game_store.gd:532:	var result: Dictionary = await gateway.request("/api/v1/mail/read", HTTPClient.METHOD_DELETE, {})
client/state\game_store.gd:559:		var result: Dictionary = await gateway.request("/api/v1/players/me", HTTPClient.METHOD_PUT, {"displayName": lobby.player.displayName, "selectedClass": value, "expectedVersion": lobby.player.version})
client/state\game_store.gd:604:	var result: Dictionary = await gateway.request("/api/v1/preparations", HTTPClient.METHOD_POST, {
client/state\game_store.gd:625:	var result: Dictionary = await gateway.request("/api/v1/matches/enqueue", HTTPClient.METHOD_POST, {"preparationId": preparation.preparationId})
client/state\game_store.gd:640:	var result: Dictionary = await gateway.request(path, HTTPClient.METHOD_DELETE)
client/state\game_store.gd:1212:	var result: Dictionary = await gateway.request("/api/v1/settlements/" + id)
client/state\game_store.gd:1228:	var result: Dictionary = await gateway.request("/api/v1/bootstrap", HTTPClient.METHOD_GET, null, [0, 502, 503, 504])
client/state\game_store.gd:1267:	var result: Dictionary = await gateway.request("/api/v1/settlements/" + settlement_id + "/acknowledge", HTTPClient.METHOD_POST, {})
client/ui\deck_builder_view.gd:176:		var response: Dictionary = await Game.gateway.request("/api/v1/cards", HTTPClient.METHOD_GET, null, [0, 400, 404, 409, 429, 500, 502, 503, 504])
client/ui\deck_builder_view.gd:190:		var inventory_response: Dictionary = await Game.gateway.request("/api/v1/inventory", HTTPClient.METHOD_GET, null, [0, 404, 409, 429, 500, 502, 503, 504])
client/ui\main.gd:934:	var result: Dictionary = await Game.gateway.request("/api/v1/cards/%s/%s" % [id.uri_encode(), action], HTTPClient.METHOD_POST, {"expectedVersion": int(entry.get("version", 0))})
client/ui\main.gd:947:		var refreshed: Dictionary = await Game.gateway.request("/api/v1/cards")
client/ui\main.gd:996:	var result: Dictionary = await Game.gateway.request("/api/v1/decks/" + Game.hero_class, HTTPClient.METHOD_PUT, {"cardIds": deck_draft, "expectedVersion": Game.deck().get("version", 0)}, [0, 400, 409, 429, 500, 502, 503, 504])
client/ui\main.gd:1134:	var result: Dictionary = await Game.gateway.request("/api/v1/equipment/" + item.instanceId + "/enhancement-quote")
client/ui\main.gd:1168:	var result: Dictionary = await Game.gateway.request("/api/v1/class-weapons/" + hero_class + "/enhancement-quote")
client/ui\main.gd:1183:	var result: Dictionary = await Game.gateway.request("/api/v1" + prefix + id + "/enhancement-quote")
client/ui\main.gd:1242:	var result: Dictionary = await Game.gateway.request("/api/v1" + path, method, body)
client/ui\main.gd:1361:	var result: Dictionary = await Game.gateway.request("/api/v1/shop/refresh", HTTPClient.METHOD_POST, {})
client/ui\main.gd:1379:	var result: Dictionary = await Game.gateway.request("/api/v1/shop/purchases", HTTPClient.METHOD_POST, {"productId": product_id, "quantity": 1})

Dynamic paths covered by registry:

- game_store cache map: GET shop, market, inventory, cards, decks, mail, wallet; trailing slash accepted.
- game_store cancellation: DELETE preparations/{guid} or matches/tickets/{guid}.
- main card mutation: POST cards/{id}/craft|dismantle|upgrade.
- main enhancement: GET class-weapons/{heroClass}/enhancement-quote and equipment/{guid}/enhancement-quote; POST corresponding enhance.
- main shared operation: loadouts/{heroClass} PUT, market/listings POST/DELETE, market/{guid}/purchase POST, plus shop operations. Exact mapping comes from frozen 46-entry registry.
- gateway ticket: POST realtime/ticket.

Explicit retained network JSON:

- GET /api/v1/client-info (announcement, maintenance, version/capabilities).
- GET /, /health/live, /health/ready (perimeter allowlist, no game format inference).
- game_store `/ws/v1/client-info` text feed remains JSON as the existing public announcement/version perimeter feed. It carries no gameplay commands.
- Local static catalog/localization/settings JSON is not network traffic. Platform Steam ticket acquisition remains platform-defined.

All first-party game HTTP has a named generated Request/Response mapping; unknown routes fail before sending. No wildcard `/api/` selection or parse-error content negotiation.

## Phase-three real-server follow-up (completed)

The earlier fixture-only limitation is now closed for login/profile/deck/session transport. New files:

- `client/tests/test_migration_real_server.gd`
- `client/tests/run_migration_real_server.py`
- `client/tests/test_http_decode_scheduling.gd`

Actual command, from the worktree:

```powershell
$taskroot = 'C:\Users\79498\Documents\Codex\2026-09-28\referenced-chatgpt-conversation-this-is-an'
python client/tests/run_migration_real_server.py --godot 'F:\GitHubFiles\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe' --dotnet "$taskroot\work\toolchain\dotnet-sdk\dotnet.exe" --psql "$taskroot\work\toolchain\postgresql\pgsql\bin\psql.exe" --connection-file "$taskroot\work\toolchain\postgres-test-connection.txt"
```

Final runner exit 0. It builds the actual .NET server into its own artifacts directory, creates a random `fc_client_real_<uuid>` PostgreSQL schema in the dedicated loopback `fc_migration_tests` database, starts the actual server on a reserved 127.0.0.1 port with legacy game JSON and legacy token query disabled, imports an isolated Godot project, then runs the shipped gateway/codec against that service. The connection file is read privately; credentials never enter command arguments or test output. Runner terminates its own server and drops only its generated, validated schema in finally. Final cleanup and credential-log scans passed.

**20 real cross-language assertions passed**, with no engine errors:

- Protobuf local login and credential acceptance.
- Actual bootstrap, user/64-bit version, absent nullable messages, nested decks/cards.
- Profile GET/PUT and deck list GET/PUT.
- Authenticated ticket to actual WebSocket `session.connected`, binary ping/pong.
- Send a ping while deliberately suspending client delivery, disconnect before accepting its pong, reconnect through a new ticket and observe real `session.resume` replay of the missed pong with replay flag set.
- A second Godot gateway for the same authenticated account obtains a new ticket and replaces the first connection. Old gateway clears credentials and disables reconnect.

Evidence: `work/client-real-server/results.json`, `server-build.log`, `godot-import.log`, `godot-real-server.log`, `server.log`. Initial real-server test script failed GDScript inference for an untyped local name; corrected the test to explicit String and reran all gates successfully. No production changes were needed for that failure.

## Large HTTP decode scheduling fix and measured result

Independent QA measured a substantial main-thread cost in interpreted GDScript protobuf decode. `gateway.gd` now sends HTTP response bodies above 8 KiB to WorkerThreadPool. The task only reads frozen schemas/bytes and constructs plain dictionaries; it does not access SceneTree/Node/UI. Main thread awaits process frames, joins only after completion, then reads the result. `_request_page` checks session_generation again before using the decoded response. Small HTTP responses and WSS decoding keep their existing path.

The fixture transport suite was extended and rerun: **19 checks passed**. Its new case changes the active session while a real 4096-card HTTP decode coroutine is pending and confirms the old response returns stale_session while retaining the new session's credential. Codec suite was rerun: **103 checks passed**.

The real-server runner captures one actual bootstrap Protobuf response (no authentication fields) and runs the scheduling comparison in the same Godot process: one warmup plus three synchronous measurements; three background measurements; headless frame cap 60 Hz. Latest sample **36,092 bytes**:

| Measurement | Actual result |
|---|---:|
| Inline decode + DTO adaptation, mean | 58.830 ms |
| Background task + await wall time, mean | 66.723 ms |
| Main-thread frames advanced across background runs | 14 |
| Longest observed main-thread frame interval | 16.703 ms |
| Result dictionary equality / background gate | PASS |

This reduces measured main-thread blocking; it does **not** make total decoding faster. Measurements are headless scheduling evidence, not GPU rendering benchmarks, end-to-end network latency, or a claim that Protobuf outperforms JSON. Raw evidence: `work/client-real-server/godot-decode-scheduling.log`. The runner fails if no frames advance, the longest observed frame interval does not improve over the inline mean, or decoded dictionary semantics differ.

Still outside this agent's executed scope: Steam production credentials, full gameplay/room/battle UI flow and room-state snapshot recovery (the real test covers session event replay), database economic concurrency invariants, compression comparisons. Independent QA/coordinator owns those gates.
