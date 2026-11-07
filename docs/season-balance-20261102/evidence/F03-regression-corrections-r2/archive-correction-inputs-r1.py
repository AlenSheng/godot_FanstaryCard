from pathlib import Path
import datetime, hashlib, json, subprocess

b = Path(__file__).parent; repo = Path.cwd()
private = Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\correction-inputs-cas-r1')
assert not private.exists(); private.mkdir()
flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
sid = subprocess.check_output(['powershell', '-NoProfile', '-Command', '[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'], creationflags=flags).decode().strip()
r = subprocess.run(['icacls', str(private), '/inheritance:r', '/grant:r', '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F'], capture_output=True, creationflags=flags)
assert r.returncode == 0
sha = lambda raw: hashlib.sha256(raw).hexdigest()
base = '746ca9d7e75fec46fde2f302e99310f8543d3e0a'
market = 'server/tests/FantasyCard.Server.Tests/Persistence/PostgresRuntimeIntegrationTests.cs'
blueprints = 'server/tests/FantasyCard.Server.Tests/Persistence/PostgresSeasonBlueprintTests.cs'
migration = 'server/tests/FantasyCard.Server.Tests/ProtobufHttp/MigrationIndependentTests.cs'

def original(name):
    return subprocess.check_output(['git', 'show', base + ':' + name]).decode('utf-8-sig').replace('\r\n', '\n')

market_r1 = original(market).replace('catch (InvalidOperationException)\n            {\n                return (buyerId, requestId, null);',
    'catch (DomainValidationException exception) when (exception.Message == "Listing is no longer available in the current market.")\n            {\n                return (buyerId, requestId, null);')
blueprints_r1 = original(blueprints).replace('using FantasyCard.Server.Common;\n', 'using FantasyCard.Server.Common;\nusing FantasyCard.Server.Rooms;\n')
needle = '        using var metrics=new ServerMetrics();var repository=new SettlementRepository(db.DataSource,p.Clock,metrics);\n        var coordinator=new SettlementCoordinator(repository,p.Clock);'
assert needle in blueprints_r1
blueprints_r1 = blueprints_r1.replace(needle, needle.replace('\n        var coordinator', '\n        await new RoomSnapshotRepository(db.DataSource,p.Clock,metrics).SaveIfDueAsync(snapshot,Ct);\n        var coordinator'))
migration_r2 = (repo / migration).read_text('utf-8-sig').replace('\r\n', '\n')
for old in ['using System.Globalization;\n', 'using FantasyCard.Server.Common;\n',
            '        // This private process checks every route\'s auth/codec boundary; limiter defaults have their own tests.\n'
            '        start.Environment["RequestLimits__EconomyWritePermitLimit"] = Math.Max(new RequestLimitOptions().EconomyWritePermitLimit,\n'
            '            HttpProtocolRegistry.Endpoints.Count(endpoint => endpoint.Method != "GET") + 5).ToString(CultureInfo.InvariantCulture);\n']:
    assert old in migration_r2; migration_r2 = migration_r2.replace(old, '', 1)
reconstructed = {('r1', market): market_r1, ('r1', blueprints): blueprints_r1,
                 ('r1', migration): original(migration), ('r2', migration): migration_r2}
all_stages = {}; recovered = []; total_bytes = 0
for stage in ['r1', 'r2', 'r3']:
    plan = json.loads((b / ('f03-corrections-' + stage) / 'inputs.original.json').read_bytes())
    rows = []
    for name, expected in plan['source_pins'].items():
        raw = (repo / name).read_bytes(); provenance = 'current input still matches the original pre-run SHA'
        if sha(raw) != expected:
            text = reconstructed[(stage, name)]
            candidates = [prefix + text.replace('\n', newline).encode('utf-8') for prefix in [b'', b'\xef\xbb\xbf'] for newline in ['\n', '\r\n']]
            raw = next(value for value in candidates if sha(value) == expected)
            provenance = 'derived exact-byte recovery from fixed Git base and recorded narrow changes; verified against original pre-run SHA'
            recovered.append(dict(stage=stage, path=name, sha256=expected, provenance=provenance))
        assert sha(raw) == expected
        target = private / expected[:2] / (expected + '.blob'); target.parent.mkdir(exist_ok=True)
        if target.exists(): assert sha(target.read_bytes()) == expected
        else: target.write_bytes(raw); total_bytes += len(raw)
        rows.append(dict(path=name, sha256=expected, provenance=provenance))
    all_stages[stage] = dict(original_plan_sha256=sha((b / ('f03-corrections-' + stage) / 'inputs.original.json').read_bytes()), inputs=rows)
(private / 'manifest.private.json').write_text(json.dumps(dict(task='season-balance-20261102', stages=all_stages, recovered_sources=recovered), indent=2) + '\n')
summary = dict(scope='Private immutable content-addressed preservation of correction inputs; not new tests or release acceptance',
    stages={stage: len(value['inputs']) for stage, value in all_stages.items()}, recovered_source_versions=recovered,
    every_input_matches_original_pre_run_SHA=True, unique_blob_count=sum(1 for _ in private.rglob('*.blob')),
    private_bytes=total_bytes, private_manifest_sha256=sha((private / 'manifest.private.json').read_bytes()),
    private_path=str(private), mappings_or_production_secrets_read=False, new_gameplay_starts=0,
    at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(b / 'f03-correction-input-preservation-r1.derived.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({key: value for key, value in summary.items() if key != 'recovered_source_versions'}))
