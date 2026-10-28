# fc_client remediation report — frozen for independent QA

Agent `/root/fc_client`; date 2026-09-28. Baseline commit `411ce667568649dadb0cdff884fc9caf53c71025`. Scope: network codec and dedicated tests only. No schemas, UI, gameplay rules, commit, push or deployment changed by this agent.

## Fix

The previous HTTP path recursively allocated a new codec and sliced each embedded message, repeatedly looked up string field numbers, then walked the entire decoded graph again to allocate camelCase dictionaries. The revised decoder:

- Compiles immutable field-number descriptors and raw/UI default dictionaries once when the script loads. Names, camelCase names, scalar kinds, decimal-effect flags and nullable-slot handling are cached.
- Decodes nested messages by bounded offsets in the original PackedByteArray with one instance/cursor; unknown length-delimited fields skip without copying. Strings and externally returned bytes retain necessary slices.
- Merges each singular embedded-message occurrence into the existing dictionary. Later absent scalars retain earlier values; repeated values append in wire order. Each embedded occurrence has its own end boundary, preventing malformed data from consuming following fields.
- Uses a one-byte fast path for tags and varints.
- Produces HTTP presentation dictionaries directly, preserving null/optional/sparse-shop/int64/effect-decimal behavior without a second graph traversal. Public raw `decode()` remains snake_case and presence-aware for realtime and compatibility callers.

The worker scheduling and generation guards in gateway.gd are unchanged. Size, nesting, collection, string, UTF-8, wire-type, field-tag and varint validation remain enabled. No validation was disabled to improve timing.

Production files changed: `client/network/protobuf.gd`, `client/network/http_protocol.gd`.

Test files changed/added: `client/tests/test_http_protobuf_client.gd`, `run_migration_real_server.py` (`--skip-scheduling` for a correctness run under concurrent host load), `run_http_codec_optimization.py`, `test_http_codec_optimization.gd` and its Godot UID.

## Controlled before/after evidence

Same genuine server bootstrap sample, 36,092 bytes, SHA-256 `69a56bedd2e8b58a86fb1caa285d717acf86134eaf8e60117cb7ec7a0d19ae4a`. Same Godot 4.7.2 console process, three warmups per implementation, 20 measured operations each in alternating order. Every result compared equal to the old implementation's dictionary. This stage started no server/database processes.

```powershell
python client/tests/run_http_codec_optimization.py --godot 'F:\GitHubFiles\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe' --baseline-ref 411ce667568649dadb0cdff884fc9caf53c71025 --sample work/client-opt/project/data/bootstrap-real.pb
```

Exit 0, no Godot errors. Raw evidence: `work/client-opt/benchmark/benchmark.log`, `results.json`.

| Metric | Before | After |
|---|---:|---:|
| Decode + presentation mean | 76.574 ms | 17.720 ms |
| Median | 75.082 ms | 17.571 ms |
| Maximum among 20 operations | 90.360 ms | 22.652 ms |
| Mean tracked memory delta with one result retained | 2,570,112 bytes | 1,441,116 bytes |
| Mean net tracked delta after releasing result | 404 bytes | 404 bytes |

Measured speedup on this sample: **4.321×**. This compares the previous and current protobuf implementations; it is not a claim that protobuf is faster than JSON, nor an end-to-end/network/GPU frame result. Total process tracked peak before/after the measured loop was 33,780,507 / 33,805,239 bytes.

Memory measurements use `OS.get_static_memory_usage()` and the cumulative `OS.get_static_memory_peak_usage()` from the debug-capable Godot console engine. They measure Godot-tracked static memory and retained/net deltas, **not total allocated bytes per decode**, not operating-system RSS, and not an isolated per-operation peak. The post-release delta includes measurement harness bookkeeping; it is not presented as proof of a leak or leak absence. Compiled descriptors are resident before both measurement loops.

## Correctness gates actually rerun

```powershell
python client/tests/run_http_protobuf_client.py --godot 'F:\GitHubFiles\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe' --work-dir work/client-opt/fixture
```

Exit 0. **173/173 protocol checks** (including the original 103), **19/19 actual loopback transport checks**. Added comparisons cover every 61 HTTP message's empty/default presentation, HTTP official vectors through the direct adaptation path, singular message merge presence, nested occurrence bounds and depth limits. Original packed/unpacked interleaving, malformed input, integer extrema, nullable messages, sparse shop payload, quotas and route matching still pass. Transport retains the account-switch-during-background-decode test. Evidence: `work/client-opt/fixture/{codec,transport}.log`, `results.json`.

After coordinator opened a real-server test window:

```powershell
$taskroot = 'C:\Users\79498\Documents\Codex\2026-09-28\referenced-chatgpt-conversation-this-is-an'
python client/tests/run_migration_real_server.py --godot 'F:\GitHubFiles\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe' --dotnet "$taskroot\work\toolchain\dotnet-sdk\dotnet.exe" --psql "$taskroot\work\toolchain\postgresql\pgsql\bin\psql.exe" --connection-file "$taskroot\work\toolchain\postgres-test-connection.txt" --work-dir work/client-opt/real-server --skip-scheduling
```

Exit 0. Actual isolated server build/import/readiness passed. **20/20 real Godot → .NET → PostgreSQL checks passed**: binary login/bootstrap, profile/deck reads and writes, typed null/collections/integer versions, ticket websocket connection, ping/pong, missed-event replay after disconnect, second-client replacement and old-client shutdown. Owned service/schema cleanup and credential-log checks passed. Schema: `fc_client_real_e0d8e97c51b246bd850cbee51ab57538` (dropped). No timing conclusion is drawn from this concurrent-host integration run. Evidence: `work/client-opt/real-server/results.json`, `godot-real-server.log`.

```powershell
$env:FANTASYCARD_SERVER_URL='http://127.0.0.1:38971'
& 'F:\GitHubFiles\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe' --headless --language en --path client --editor --import --quit
```

Full application import/parse exit 0, zero `ERROR:` / `SCRIPT ERROR` matches. Evidence: `work/client-opt/full-parse.log`. `git diff --check -- client/network client/tests` exit 0; only Git line-ending normalization notices.

No failing test remains in the executed scope. Current production changes and test fixtures are frozen for independent QA. Full gameplay coverage and the consolidated protobuf-versus-JSON benchmark remain owned by the coordinator/QA; this report does not claim their unexecuted results.
