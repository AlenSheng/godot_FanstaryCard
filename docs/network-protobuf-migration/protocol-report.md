# fc_protocol execution report

Executor: actual agent `/root/fc_protocol`.

Read PLAN, role TOML, server AGENTS, GDD 0.6.1 and service/design/integration references. Referenced server_create skill absent as independently confirmed by coordinator. User migration instruction supersedes old REST JSON-only text; gameplay behavior unchanged.

Frozen contract and consumption instructions: `protocol-compatibility.md`. Initial contract stage PASS: official Contracts build and 21 executable interoperability assertions. Full game migration is not claimed.

Actual commands:

1. PATH `dotnet --version` under server: FAILED, system installation had no SDK matching 10.0.400. Coordinator provisioned official SDK under task work/toolchain/dotnet-sdk; subsequent commands prepend that path and set DOTNET_ROOT.
2. `python tools/generate_network_protocol.py`: initially FAILED Python 3.9 newline keyword, then PASS after correction.
3. `python tools/generate_network_protocol.py --check`: PASS (70 realtime / 61 HTTP messages, 46 endpoint mappings).
4. `dotnet build server/src/FantasyCard.Contracts/FantasyCard.Contracts.csproj --artifacts-path server/artifacts/protobuf-protocol -v minimal`: first FAILED CA1859, corrected private Load return type; second PASS 0 warnings 0 errors.
5. `dotnet run --project protocol/tests/ProtocolVectors.csproj --artifacts-path server/artifacts/protobuf-vectors -- protocol/golden-vectors.json`: PASS total=21; official Google.Protobuf vectors=8.

Changed: realtime.proto, HTTP game.proto/endpoints.json, golden-vectors.json, protocol/tests console verification, tools/generate_network_protocol.py and legacy schema wrapper, three Godot schemas/registries, Contracts csproj, Http registry/mapper, realtime packed-order/overflow reader fix, this report and compatibility note. Central package versions are integrated by coordinator, not edited by this agent.

Pending validation: Godot runs with next-batch codec; full SDK solution suite with QA; database endpoint tests; performance measurements. No push/deploy/merge/reset/clean/stash/commit executed by this role.

## Follow-up: measured mapper allocation fix

QA identified repeated per-field reflection/normalization as a concrete bottleneck. Added thread-safe ConcurrentDictionary caches for immutable descriptor factories/field arrays, DTO property lookup including read/claimed aliases, type+descriptor read bindings, and constructor/parameter bindings. Request values are never cached. Validation now checks scalars directly instead of allocating a one-element array per field. JSON persisted-field name matching compares without allocating normalized strings. Schema, integer precision, optional/default/null behavior and all limits remain unchanged.

Measurements used the same captured `server/.artifacts/qa-migration/samples/bootstrap.json` (249006 bytes), deserialized into BootstrapResponse, .NET runtime 10.0.11, Release build, 20 warmup + 100 measured iterations, Stopwatch and GC.GetAllocatedBytesForCurrentThread, no compression/network. Before/after artifacts: `server/.artifacts/protocol-perf/before.json` and `after.json`. Rehydrated DTO produced 35555 PB bytes both runs; this is a local mapper benchmark, distinct from QA's original 36093-byte captured response.

| Operation | Before microseconds/op | After microseconds/op | Before allocation B/op | After allocation B/op |
|---|---:|---:|---:|---:|
| PB encode DTO | 25221.494 | 5573.952 | 12862374 | 779469 |
| PB decode DTO | 18310.249 | 4945.963 | 6775219 | 874892 |
| JSON encode DTO (control) | 3344.797 | 1982.549 | 249792 | 249792 |

Time varies with concurrent test workload; allocation reduction directly addresses the reported bottleneck. PB encode still allocates more and takes longer than JSON encode in this sample. This does not establish end-to-end or universal performance superiority. QA was asked to rerun its original measurement on the final mapper.

Actual follow-up commands (SDK path set as above):

- `dotnet run --project .artifacts/protocol-perf/benchmark/Benchmark.csproj -c Release --artifacts-path .artifacts/protocol-perf/build -- .artifacts/qa-migration/samples/bootstrap.json .artifacts/protocol-perf/before.json`: PASS before edit; same command with after.json PASS after edit. Benchmark harness is isolated under ignored .artifacts. Initial invocation had an incorrect temporary path, corrected before measuring. First after-build rejected CA1859 on ReadJson return type; changed to JsonElement? and rebuilt successfully.
- `dotnet run --project protocol/tests/ProtocolVectors.csproj --artifacts-path server/.artifacts/protocol-perf/vectors`: PASS 22 assertions, now including 64 concurrent cold-cache constructions with distinct int64 values; eight golden vectors.
- From server: `dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --artifacts-path .artifacts/protocol-perf/boundary --filter FullyQualifiedName~ServerApiBoundaryTests -v minimal`: PASS 10/10, zero skipped. The current filtered suite has 10 tests, not the 11 mentioned in the task assignment.

Follow-up source changes: HttpDtoMapper.cs, protocol/tests/Program.cs concurrency check, and this report. Contract frozen again after these checks.
