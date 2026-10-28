# Local changes merged into release — 2026-09-29

Scope: login version label, settlement retry UI/state and localization, card selection order display/regressions, persisted settlement protobuf serialization fix, and real Godot gameplay load client/coordinator.

Validation performed before commit:

- Godot 4.7.2 headless client/tests/run_play_retry.gd: all 15 test groups passed, exit 0.
- Python compile check tools/gameplay_load_test.py: passed.
- git diff --check for source: passed.
- dotnet test server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --filter FullyQualifiedName~SettlementEncodingTests: could not start; required .NET SDK 10.0.400 is not installed. C# changes are not newly build/test verified in this merge.

Gameplay test limitations remain as documented in the accompanying summary: 52 client flow failures and HTTP latency stop. The tool is diagnostic, not evidence of successful 100-player sustained combat capacity. Temporary production request limits were already restored. This commit/merge does not deploy the server or enable candidate rules.

Local SDK, bin/obj build outputs, raw temporary execution files and unrelated generated website/image artifacts are preserved locally and excluded from this source commit.
