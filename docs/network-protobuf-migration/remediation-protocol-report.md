# fc_protocol remediation report — 2026-09-28

Executor: real `/root/fc_protocol`; starting HEAD `411ce667568649dadb0cdff884fc9caf53c71025`. Scope is mapper performance and controlled Bootstrap diagnostics. No wire/schema/gameplay/database production change; no push/deployment.

## Mapper change and compatibility

`HttpDtoMapper` now caches compiled DTO getters, typed direct scalar copy delegates, and constructor delegates. Same-type int32/int64/bool fields pass directly from DTO into generated properties without reflection or boxing. Nullable scalar absence and explicit zero/empty presence remain distinct. UUID/date/decimal/enum conversion keeps the existing explicit adapter. `Validate` skips non-repeated numeric scalar fields (which have no size/depth checks) while retaining collection, string, nested-message and total-body limits.

Strict Release protocol vectors: **25/25 passed**, including concurrent cold cache initialization, int64 extremes, optional absence/zero/empty, mail read/claimed aliases, packed/unpacked ordering, malformed/oversized input and official vectors. ServerApiBoundaryTests: **10/10 passed**, no skips; TRX `.artifacts/protocol-remediation/boundary-results/boundary.trx`. `python tools/generate_network_protocol.py --check`: passed unchanged 70 realtime + 61 HTTP messages / 46 routes. New benchmark tool builds with TreatWarningsAsErrors, zero warnings/errors.

## Controlled codec comparison

Same persisted QA Bootstrap JSON (249001 bytes), .NET 10.0.11 Release, local Core Ultra 7 155H. Before and after executable trees were retained separately. Three sequential alternating before/after runs, no test load launched by this role concurrently; each run 20 warmups + 100 measured operations. Request DTO is rehydrated from the same file in every process. Its PB output is 35555 bytes; do not confuse this codec fixture with original raw live 36093-byte response. Results are under `.artifacts/protocol-remediation/20260928-122146/` (use `current-run.txt` for exact local directory if wall-clock label differs).

| Metric | Before | After |
|---|---:|---:|
| PB encode allocation B/op | 779469 | 286757 |
| PB encode mean ms/op across three runs | 3.914–4.550 | 2.324–2.852 |
| PB decode allocation B/op | 874892 | 868868 |
| PB decode mean ms/op across three runs | 3.303–3.870 | 2.775–3.250 |
| JSON encode allocation B/op (control) | 249792 | 249792 |
| JSON encode mean ms/op across six runs | 1.334–1.669 | same control range |

PB encoding allocation dropped 63.2% for this sample. PB still takes more CPU and allocates more than JSON encoding. CPU observations are machine/workload dependent; this is not a claim of universal or end-to-end speed advantage. Initial build-run measurements are also retained, not substituted for the three paired runs.

## Real HTTP compression measurement

`tools/NetworkProtocolBenchmark` creates an ephemeral loopback Kestrel fixture, runs the actual mapper/JSON encoder on each captured Bootstrap request, enables the standard gzip middleware only inside the tool, and verifies decompressed response bytes exactly. No production compression setting was changed. No database/auth work occurs in this fixture. Ten warmups plus 100 measured requests for each format/compression combination; gzip Fastest, no auto decompression in measured client interval.

Evidence: `.artifacts/protocol-remediation/compression-verified-20260928-123030/` (`requests.jsonl`, sample hashes/bytes, result.json). Successful 400 measured requests with matching decompressed content.

| Format | Compression | Bytes | p50 ms | p95 ms | p99 ms |
|---|---|---:|---:|---:|---:|
| PB | off | 35555 | 2.745 | 5.390 | 8.617 |
| PB | gzip Fastest | 4805 | 4.280 | 5.361 | 5.802 |
| JSON | off | 249001 | 2.454 | 3.808 | 11.958 |
| JSON | gzip Fastest | 10758 | 1.901 | 2.997 | 3.509 |

These local sequential measurements establish real HTTP compression behavior and encoded size, not production latency or capacity. Compression adds CPU and loopback timing can change with scheduling.

## Bootstrap timeout diagnosis

A separate real Release server with isolated PostgreSQL schema executed 120 sequential alternating Bootstrap requests (60 PB, 60 JSON), every response 200 and fully consumed, with per-request 20-second deadline, unique trace ID, begin/header/body stages and uninterrupted stdout/stderr capture. PB p50/p95/max = 24.021/39.690/218.079 ms; JSON = 24.311/45.458/195.149 ms. Evidence `.artifacts/protocol-remediation/diagnose-20260928-122625/`; stderr empty. Schema retained locally for diagnosis. No timeout occurred in this controlled run.

**This does not resolve the earlier transient timeout.** Realtime owner independently saw one 60-second cancellation during its new four-player preparation case. Its next two runs completed Bootstrap (one exposed a distinct test BotFillDelay configuration issue, subsequent four-player case passed). Root requested continued correlation. The diagnostic tool includes `monitor` mode sampling loopback pg_stat_activity/wait events/blocking PIDs into unique local logs. A first sampling window caught only one backend after the short test had completed, so it is not evidence against a lock during the failed run.

With coordinator authorization, shared `NetworkServerProcess` test helper now persists server output immediately into unique UTC/PID/GUID files under `.artifacts/protocol-remediation/process-logs`, redacting access_token/ticket query values and Bearer tokens. Previous failed-request server logs were not persisted by that helper. Realtime owner is adding header/body phase traces to its new case. No speculative BootstrapRepository change was made.

## Reproduction

Build tool (from repository root):

`dotnet build tools/NetworkProtocolBenchmark/NetworkProtocolBenchmark.csproj -c Release --artifacts-path server/.artifacts/protocol-remediation/tool`

Run the resulting DLL with **absolute input/output paths** (SDK Web `dotnet run` can change the working directory):

- `codec <bootstrap.json> <new-output-directory>`: sample hashes, 50 warmups/300 iterations, encode/decode and allocations.
- `compression <bootstrap.json> <new-output-directory>`: loopback Kestrel on/off gzip comparison and byte verification.
- `diagnose <connection-file> <new-output-directory> <dotnet-exe> <server-dll> <server-project-directory>`: unique DB schema, real server, 120 requests, logs. Connection must point to loopback; credentials are never printed.
- `monitor <connection-file> <new-output-directory>`: 60 seconds of PG wait/blocker samples.

Existing output directories are rejected to prevent overwriting evidence. One initial compression `dotnet run` used relative paths and failed DirectoryNotFound; rerun via DLL with correct paths passed. While editing vectors, an existing legacy-codepage test source read failed UTF-8 decoding; source was explicitly normalized to UTF-8 and rerun with the added compatibility assertions.

Final protected/obfuscated publish validation belongs to coordinator: compiled accessors use the same public property/descriptor names required by the original reflection adapter. No protection flag or rule was changed by this agent.


### Final diagnosis status / freeze

Realtime owner's final combined PVP restart + four-player default-PB preparation tests passed with the new process-log capture included. The two PG sampling windows (`monitor-20260928-123042`, `monitor-20260928-123238`) started after those short successful runs and each recorded only one backend observation; neither overlaps the failed request. They cannot explain or rule out the earlier timeout. No dump was taken because no hung process remained. The timeout remains **unreproduced in the controlled run and unrooted**, not fixed. Persisted process logs and per-request stages now make the next occurrence inspectable.

All role source changes are frozen for coordinator strict QA: Contracts/Http/HttpDtoMapper.cs; protocol/tests/Program.cs; tools/NetworkProtocolBenchmark/Program.cs and csproj; authorized shared NetworkServerProcess diagnostic persistence in RealNetworkEndToEndTests.cs. No active role test/diagnostic process remains. Schema unchanged. Report-only additions after freeze do not affect tested binaries.

### Protected-package cold-start follow-up

Coordinator's actual protected-package TLS probe reproduced a 10-second response-header timeout after successful PB login. Its original failure evidence remains `work/remediation-tls/server.log`, `results.json`, and `work/remediation-tls-run.log`. This expands the unresolved issue beyond the earlier 60/100-second observations; no claim is made that any timeout was fixed.

A scratch diagnostic copy of the TLS verifier was configured to preserve a hung service for 45 seconds on Bootstrap failure so a live stack could be collected. It did not alter application binaries. With the same protected `builds/server-protected/server-63okamu3` package, six independent cold services, six new database schemas and six new Caddy instances all passed **20/20 real loopback TLS/WSS checks per run**, including each process's first Bootstrap. Evidence: `work/protocol-timeout/tls-repro-1` through `tls-repro-6`, each with its own results and server/proxy logs. The final five were run sequentially with PG sampling already active; `.artifacts/protocol-remediation/monitor-cold-20260928-1250/requests.jsonl` captured 159 backend observations at review time, no blocker IDs and no active query older than one second. The first TLS repeat also had synchronized sampling (`monitor-tls-20260928-1245`, 40 observations, no such wait). This does not sample the original failed request and cannot rule out a transient cross-process/resource problem.

During coordinator's long protected test run, no server subprocess remained when the suspected hang was investigated. A live managed stack of the still-running xUnit test process PID 9072 was successfully captured in `.artifacts/protocol-remediation/stack-test-9072.txt`: main thread waiting for xUnit tasks, two workers in async file reads, others mostly idle. There was no active mapper or type-initialization stack, but an async wait stack alone cannot establish root cause. A subsequent heap-dump attempt failed because the process had already exited; no diagnostic heap is claimed. Coordinator subsequently confirmed that the suite completed normally with 459 passed / 2 failed, rather than hanging; the two settlement failures are under a different owner's protected-build investigation.

Conclusion remains deliberately narrow: controlled hot and cold requests pass, real historical timeouts remain unexplained, and logs/phase tracing now preserve the next occurrence. No speculative pool, repository, timeout-extension, or protocol change was made. Diagnostic tools were installed only in local ignored work directories; no production diagnostics setting was changed.
