# Frozen HTTP / realtime contract (2026-09-28)

Contract owner: real agent `/root/fc_protocol`. Contract is frozen for batch two. Future wire changes must be coordinated with this owner and regenerate schemas. Existing gameplay DTOs remain separate from generated wire classes.

## Consumption

- HTTP source: `protocol/http/v1/game.proto`. Namespace `FantasyCard.Contracts.Http.V1`; official Google.Protobuf 3.33.0 and Grpc.Tools 2.76.0 (central versions). Build generates C# into intermediate outputs, not hand-maintained classes.
- HTTP exact method/path-template map: `protocol/http/v1/endpoints.json`; 46 entries including authenticated POST `/api/v1/realtime/ticket` (Empty -> RealtimeTicketResponse). Template constraints are retained. GET routes have Empty request; 204 responses have Empty response and no body. JSON perimeter routes are deliberately absent.
- Godot data: `client/data/http_schema.json`, `client/data/http_endpoints.json`; realtime remains `client/data/realtime_schema.json`. `python tools/generate_network_protocol.py` regenerates all three; `--check` rejects drift. Old `generate_client_schema.py` forwards to this unified entry point.
- Server: `HttpProtocolRegistry.Find(method,path)` returns `HttpEndpointContract` with RequestDescriptor / ResponseDescriptor. `HttpDtoMapper.DecodeRequest(contract,byte[],typeof(existing DTO))` produces existing typed DTOs. `HttpDtoMapper.EncodeResponse(contract,object)` emits binary protobuf directly. Arrays for cards/decks/market wrap in an `items` message, registry `unwrap_items=true` tells Godot to restore the existing UI array shape. Empty response / status 204 handling belongs to the boundary.
- All non-success responses use `HttpError` (type/title/status/detail/trace_id/code/optional retry_after_seconds). HttpStatus, Retry-After, bearer auth, idempotency keys and trace headers retain their transport semantics. No parse-error retry with JSON.
- `RealtimeTicketResponse.ticket` is opaque; `expires_at` is UTC ISO-8601 string. Client calls ticket endpoint with bearer auth then connects `/ws/v1/session?ticket=...`; credential logging and single-use consumption belong to realtime agent.

## Data adaptation

HTTP wire field names are snake_case. Godot recursively restores camelCase. Its integers must remain signed 64-bit integers; never JSON.stringify/parse or float-roundtrip. UUID, UTC ISO-8601 dates and existing enum names use strings. `CardEffectResponse` decimal effects are invariant strings on wire; convert just these effect fields to float for current UI calculations (drawCharge/drawSpeedModifier/drawSpeedSeconds/stunSeconds/drawBlockSeconds/conflictCancelBonus/conflictHealCoefficient). Monetary amounts and versions always remain int64.

Optional scalar absence means null / omitted. Explicit optional zero/empty is distinct. Message absence means absent/null. Repeated values mean empty list if absent. Nullable equipment slots encode as empty UUID string and decode to null, retaining five-slot positions. PurchaseShopRequest.quantity is optional; absence maps to existing default 1. Enum names are case-sensitive at the DTO adapter and invalid names are rejected.

`ShopProductResponse.payload` is **ShopProductPayload**, with typed optional card_id/quality/rarity/count/amount/hero_class fields. The server adapter reads existing persisted JSON once into these fields; no JSON is put on wire. Godot game_store code currently parsing payload strings must accept this dictionary directly. `ShopPurchaseResponse.granted` is existing human-readable text (e.g. `3 cards`), not JSON.

`SettlementResponse.details` is **SettlementDetails**: room_id/revision/phase/position/hero_class/asset_count/items. Items contain item/equipped, item contains item_id/kind/quantity/is_safe/equipment. SettlementEquipment holds numeric persisted enum values for slot/quality/element and optional affix strings. Persistence JSON is mapped by field into this named message. Existing details UI sees the same dictionary shape; unknown historical fields are not promised in this new wire contract.

HTTP limits are independently fixed at 2 MiB per body, depth 24, 4096 elements per repeated field, 128 KiB per string. Reject oversized data explicitly; pagination remains an endpoint concern. These limits do not change the realtime 16 KiB budget.

## Realtime compatibility

Actual production codec is authoritative for repairing missing v1 declarations:

| Message | Tags restored | Wire type |
|---|---|---|
| BattleComboResolvedEvent | 24 resonance_multiplier, 25 conflict_pair_count, 26 conflict_cancellation | string/int32/string |
| MapPlayerCountEvent | 1 player_count | int32 |
| RoomSnapshotEvent | 16 map_player_count | int32 |

No existing tag is renumbered or repurposed. Existing decimal strings stay strings. C# realtime codec preserves old DTO routing and is validated against official generated messages. Its repeated integer reader now preserves original ordering when packed/unpacked occurrences alternate; overflowing tenth varint byte is rejected. Client codec owner must add matching packed/unpacked handling before full cross-language gate is complete.

## Evidence / remaining gate

`dotnet build server/src/FantasyCard.Contracts/FantasyCard.Contracts.csproj --artifacts-path server/artifacts/protobuf-protocol -v minimal`: PASS, zero warnings/errors, SDK 10.0.400.

`dotnet run --project protocol/tests/ProtocolVectors.csproj --artifacts-path server/artifacts/protobuf-vectors -- protocol/golden-vectors.json`: PASS 21 assertions, eight official golden vectors. Exercises both official/legacy directions, int64 extremes, optional absence/zero, nested messages, typed shop payload, packed/unpacked and mixed ordering, unknown fields, malformed lengths, zero tag, overflowing varint, HTTP size/string limits and route registry.

`python tools/generate_network_protocol.py --check`: PASS 70 realtime + 61 HTTP messages / 46 routes.

These are contract gates, not full endpoint integration or Godot proof. Godot golden-vector runs wait for batch-two codec changes; database integration, authentication failures and UI flow are batch-three gates. SDK was supplied by coordinator. First build failed CA1859 (Load return type), corrected to concrete array and rebuilt successfully. First generator run used unsupported Python 3.9 write_text(newline=...), corrected and rerun. No unexecuted test is marked passed.
