using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Persistence;
using FantasyCard.Server.Rooms;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

static void Require(bool value, string message) { if (!value) throw new InvalidOperationException(message); }
static string Hash(object value) => Convert.ToHexStringLower(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(value)));
using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(120));
var ct = deadline.Token;
var output = "/evidence/native";
Directory.CreateDirectory(output);
var connection = Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES") ?? throw new InvalidOperationException("Owned PG setting absent");
var schema = "pr13_b12_policy_" + Guid.NewGuid().ToString("N");
await using var admin = NpgsqlDataSource.Create(connection);
await using (var create = admin.CreateCommand("CREATE SCHEMA " + schema)) await create.ExecuteNonQueryAsync(ct);
var settings = new NpgsqlConnectionStringBuilder(connection) { SearchPath = schema };
var rows = new List<object>();
var removed = false;
try
{
    await using var data = NpgsqlDataSource.Create(settings.ConnectionString);
    using var metrics = new ServerMetrics();
    await new DatabaseMigrator(data, NullLogger<DatabaseMigrator>.Instance).StartAsync(ct);
    var catalog = CombatCardCatalog.CreatePrototype();
    using var rawRows = new StreamWriter(Path.Combine(output, "witnesses.original.jsonl"), append: false);
    foreach (var hero in new[] { HeroClass.Mage, HeroClass.Priest, HeroClass.Guardian })
    foreach (var level in Enumerable.Range(0, 6))
    foreach (var labelOn in new[] { false, true })
    foreach (var effectiveOn in new[] { false, true })
    {
        var label = labelOn ? "candidate-label:on" : "candidate-label:off";
        var rules = new NumericalRules(CardsSpentDraw: effectiveOn, FractionalGuardian: effectiveOn);
        var room = new BattleRoom(Guid.NewGuid(), label, catalog, 7721 + level, rules);
        var playerId = Guid.NewGuid();
        room.AddPlayer(new(playerId, hero, Enumerable.Repeat("common-01", 20).ToArray(), null, level));
        var matchId = Guid.NewGuid();
        await using (var insert = data.CreateCommand("INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',7721,$3,'Running',now())"))
        {
            insert.Parameters.AddWithValue(matchId); insert.Parameters.AddWithValue(room.RoomId); insert.Parameters.AddWithValue(label);
            await insert.ExecuteNonQueryAsync(ct);
        }
        var before = room.Capture();
        var repo = new RoomSnapshotRepository(data, TimeProvider.System, metrics);
        await repo.SaveIfDueAsync(before, ct);
        async Task<string> Raw()
        {
            await using var query = data.CreateCommand("SELECT snapshot_json::text || rng_state_json::text FROM room_snapshots WHERE room_id=$1");
            query.Parameters.AddWithValue(room.RoomId); return (string)(await query.ExecuteScalarAsync(ct))!;
        }
        var durableBefore = await Raw();
        var saved = (await new RoomSnapshotRepository(data, TimeProvider.System, metrics).GetAsync(room.RoomId, ct))!;
        var restored = BattleRoom.Restore(saved, catalog, 999);
        Require(Hash(before) == Hash(restored.Capture()), "Complete restored snapshot differs");
        Require(restored.ConfigVersion == label, "Display label did not survive database");
        var player = restored.GetPlayer(playerId);
        var expectedFenxian = effectiveOn ? FenxianImmediateDrawPolicy.CoreCardsSpent : FenxianImmediateDrawPolicy.CurrentRhythm;
        var expectedGuardian = effectiveOn ? GuardianShieldBonusPolicy.FractionalRemainder : GuardianShieldBonusPolicy.CurrentSteps;
        Require(player.Combat.FenxianDrawPolicy == expectedFenxian && player.Combat.GuardianShieldPolicy == expectedGuardian, "Label replaced effective combat policies");
        Require(restored.Numerics.CardsSpentDraw == effectiveOn && restored.Numerics.FractionalGuardian == effectiveOn, "Persisted numerical flags differ");
        Require(!restored.Numerics.OptionalMonsterPool && !restored.Numerics.BudgetedBotLoot && !restored.Numerics.MortalBotPve, "Unrelated candidates enabled");
        var draws = Enumerable.Range(0, 5).Select(_ => player.Combat.UpdateFenxian(CardElement.Fire, 1).Draw).ToArray();
        var expectedDraws = hero == HeroClass.Mage && !effectiveOn ? new[] { 0, 0, 1, 1, 2 } : new[] { 0, 0, 0, 0, 0 };
        Require(draws.SequenceEqual(expectedDraws), "Draw behavior disagrees with effective policy");
        var shields = new List<int>();
        for (var i = 0; i < 5; i++)
        {
            var draft = player.Combat.PreviewShield(1); var applied = player.Combat.GainShield(draft.Shield);
            player.Combat.CommitGuardianShieldRemainder(draft.RemainderTenthsAfter); shields.Add(applied);
        }
        var expectedShieldTotal = hero != HeroClass.Guardian ? 5 : effectiveOn ? 10 + 2 * level : 5 * (1 + (level >= 4 ? 3 : level >= 2 ? 2 : 1));
        Require(shields.Sum() == expectedShieldTotal && player.Combat.GuardianShieldRemainderTenths == 0, "Shield behavior disagrees with effective policy");
        var durableAfter = await Raw();
        Require(durableBefore == durableAfter, "Controlled local probes mutated persisted original");
        var onceAgain = BattleRoom.Restore((await repo.GetAsync(room.RoomId, ct))!, catalog, 123);
        Require(Hash(before) == Hash(onceAgain.Capture()), "Reopening original changed effective policy or instances");
        var effectiveRecord = new { cardsSpentDraw = onceAgain.Numerics.CardsSpentDraw, fractionalGuardian = onceAgain.Numerics.FractionalGuardian };
        var row = new { hero = hero.ToString(), level, labelOn, effectiveOn, displayLabel = label, matchId, roomId = room.RoomId, playerId,
            reportedEffective = effectiveRecord, fenxianPolicy = player.Combat.FenxianDrawPolicy.ToString(), guardianPolicy = player.Combat.GuardianShieldPolicy.ToString(), draws, shields,
            expectedDraws, expectedShieldTotal, originalSnapshotSHA256 = Hash(before), restoredSnapshotSHA256 = Hash(onceAgain.Capture()),
            durableBeforeSHA256 = Hash(durableBefore), durableAfterSHA256 = Hash(durableAfter), before, saved, localProbeAfter = restored.Capture() };
        rows.Add(new { hero = hero.ToString(), level, labelOn, effectiveOn, reportedEffective = effectiveRecord, draws, shields });
        await rawRows.WriteLineAsync(JsonSerializer.Serialize(row));
    }
    await rawRows.FlushAsync(ct);
    Require(rows.Count == 72, "Full preregistered matrix incomplete");
}
finally
{
    using var cleanupDeadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
    await using var drop = admin.CreateCommand("DROP SCHEMA " + schema + " CASCADE"); await drop.ExecuteNonQueryAsync(cleanupDeadline.Token); removed = true;
}
await File.WriteAllTextAsync(Path.Combine(output, "summary.original.json"), JsonSerializer.Serialize(new { passed = true, executed = rows.Count, matrix = new { heroes = 3, weaponLevels = 6, displayedLabels = 2, effectivePolicies = 2 },
    labelOnEffectiveOff = 18, labelOffEffectiveOn = 18, ownSchemaRemoved = removed, rows,
    scope = "Current compiled real room and repository persisted policy classification plus independent draw/shield boundary checks; controlled display labels, not production candidate activation or full gameplay statistics", MAIN_accepted = false }) + "\n");
Console.WriteLine(JsonSerializer.Serialize(new { ok = true, executed = rows.Count, ownSchemaRemoved = removed }));
