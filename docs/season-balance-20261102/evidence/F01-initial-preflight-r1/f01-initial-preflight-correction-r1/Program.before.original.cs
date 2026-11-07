using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Persistence;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

var output = Environment.GetEnvironmentVariable("F01_PREFLIGHT_OUTPUT") ?? throw new InvalidOperationException("Owned output required.");
var planPath = Environment.GetEnvironmentVariable("F01_PREFLIGHT_PLAN") ?? throw new InvalidOperationException("Original proposal required.");
Directory.CreateDirectory(output);
var checks = new Dictionary<string, bool>(StringComparer.Ordinal);
void Check(string name, bool value)
{
    checks.Add(name, value);
    if (!value) throw new InvalidOperationException("Preflight assertion failed: " + name);
}
var config = GameConfigCatalog.Current;
Check("formal17 embedded configuration", config.Version == "season-v1-config-17" && config.ContentHash == "3e4efc7f04d2acc0d70f1ef3ba7f2ce9cc4b675543b443606880a10b6cc1e490");
var season = SeasonDefinition.FromCalendarDays("f01-preflight-r1", new DateOnly(2026, 11, 1), config.Version, "season-equipment-v1");
using var plan = JsonDocument.Parse(File.ReadAllText(planPath));
var actors = plan.RootElement.GetProperty("actors").EnumerateArray().Select(x => x.Clone()).ToArray();
var attempts = plan.RootElement.GetProperty("attempts").EnumerateArray().Select(x => x.Clone()).ToArray();
Check("nine actor identities unique", actors.Length == 9 && actors.Select(x => x.GetProperty("id").GetString()).Distinct().Count() == 9);
Check("252 proposed starts only", attempts.Length == 252 && attempts.Select(x => x.GetProperty("id").GetString()).Distinct().Count() == 252);
foreach (var actor in actors)
{
    var id = actor.GetProperty("id").GetString()!;
    Check(id + " no old capital or granted seasonal gear", !actor.GetProperty("old_D03_capital_imported").GetBoolean()
        && actor.GetProperty("starting_season_gold").GetInt64() == 0 && actor.GetProperty("starting_season_fragments").GetInt64() == 0
        && actor.GetProperty("starting_blueprints").GetInt64() == 0 && actor.GetProperty("starting_orange_blueprints").GetInt64() == 0
        && actor.GetProperty("starting_season_equipment").GetArrayLength() == 0);
    for (var day = 1; day <= 14; day++)
    {
        var dayRows = attempts.Where(x => x.GetProperty("actor").GetString() == id && x.GetProperty("day").GetInt32() == day).ToArray();
        Check(id + " day " + day + " two declared hours", dayRows.Select(x => x.GetProperty("shanghai_start_hour").GetInt32()).Order().SequenceEqual(new[] { 9, 18 }));
    }
}
foreach (var attempt in attempts)
{
    var day = attempt.GetProperty("day").GetInt32();
    var hour = attempt.GetProperty("shanghai_start_hour").GetInt32();
    Check(attempt.GetProperty("id").GetString()! + " original calendar", season.NaturalDayAt(season.StartsAtUtc.AddDays(day - 1).AddHours(hour)) == day);
}
foreach (var group in attempts.GroupBy(x => x.GetProperty("seed").GetInt32()))
    Check("paired seed " + group.Key, group.Count() == 3 && group.Select(x => x.GetProperty("actor").GetString()!.Split('-')[1]).Distinct().Count() == 1);
var calendar = new List<object>();
foreach (var day in new[] { 1, 7, 14 })
{
    var now = season.StartsAtUtc.AddDays(day - 1).AddHours(9);
    var active = config.SeasonActivity!.Windows(season).Where(x => x.Contains(now)).Select(x => x.EventId).ToArray();
    Check("activity state day " + day, active.Length == (day == 14 ? 1 : 0));
    Check("journey week day " + day, SeasonJourneyConfig.WeekAt(season, now) == (day == 14 ? 2 : 1));
    var reference = config.SeasonJourney!.ReferenceAt(season, now);
    calendar.Add(new { day, now, active_events = active, reference_experience = reference,
        shop_day_key = EconomySchedule.GetDailyResetKey(now), reference_is_not_granted_experience = true });
}
var localMidnight = season.StartsAtUtc.AddDays(1);
Check("natural day switches at Shanghai midnight", season.NaturalDayAt(localMidnight.AddTicks(-1)) == 1 && season.NaturalDayAt(localMidnight) == 2);
Check("shop day does not switch at natural midnight", EconomySchedule.GetDailyResetKey(localMidnight.AddTicks(-1)) == EconomySchedule.GetDailyResetKey(localMidnight));
Check("shop day switches at Shanghai04", EconomySchedule.GetDailyResetKey(localMidnight.AddHours(4).AddTicks(-1)) != EconomySchedule.GetDailyResetKey(localMidnight.AddHours(4)));
var deathRejected = false;
try { _ = config.SeasonJourney!.SourceExperience("Dead"); }
catch (DomainValidationException) { deathRejected = true; }
Check("death itself is not an experience source", deathRejected);
Check("activity potion cost is six shared tokens", config.SeasonActivity!.Exchange("event-potion").TokenCost == 6 && config.SeasonActivity.Exchange("event-potion").EventLimit == 1);

var connectionString = Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES") ?? throw new InvalidOperationException("Owned test database required.");
await using var admin = NpgsqlDataSource.Create(connectionString);
var schema = "f01_initial_preflight_" + Guid.NewGuid().ToString("N");
var created = false;
var dropped = false;
object? actual = null;
try
{
    await using (var create = admin.CreateCommand("CREATE SCHEMA " + schema)) await create.ExecuteNonQueryAsync();
    created = true;
    File.WriteAllText(Path.Combine(output, "schema-handle.original.json"), JsonSerializer.Serialize(new { schema, own_test_schema = true, gameplay_starts = 0 }));
    var settings = new NpgsqlConnectionStringBuilder(connectionString) { SearchPath = schema, Pooling = false };
    await using (var source = NpgsqlDataSource.Create(settings.ConnectionString))
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(120));
        var ct = deadline.Token;
        await new DatabaseMigrator(source, NullLogger<DatabaseMigrator>.Instance).StartAsync(ct);
        var now = season.StartsAtUtc.AddHours(9);
        var clock = new FixedClock(now);
        var seasonRepository = new SeasonRepository(source, clock);
        Check("actual season publication", await seasonRepository.PublishAsync(season, config.ContentHash, ct, config));
        var identity = new IdentityRepository(source, new PlayerProvisioningService());
        var profile = await identity.SignInLocalAsync("owned-device", "f01-initial-" + Guid.NewGuid().ToString("N"), RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        await seasonRepository.EnsurePlayerAsync(profile.UserId, season.ContextFor(0), ct);
        await using var connection = await source.OpenConnectionAsync(ct);
        async Task<long> Count(string sql)
        {
            await using var command = new NpgsqlCommand(sql, connection);
            command.Parameters.AddWithValue(profile.UserId);
            return Convert.ToInt64(await command.ExecuteScalarAsync(ct));
        }
        var owned = new Dictionary<string, OwnedCard>(StringComparer.Ordinal);
        await using (var command = new NpgsqlCommand("SELECT card_id,hero_class,rarity,copy_count,is_monster,level,unlocked FROM player_cards WHERE player_id=$1 ORDER BY card_id", connection))
        {
            command.Parameters.AddWithValue(profile.UserId);
            await using var reader = await command.ExecuteReaderAsync(ct);
            while (await reader.ReadAsync(ct))
            {
                Check("initial level0 " + reader.GetString(0), reader.GetInt32(5) == 0);
                if (reader.GetBoolean(6)) owned.Add(reader.GetString(0), new(reader.GetString(0), reader.IsDBNull(1) ? null : (HeroClass)reader.GetInt16(1), (CardRarity)reader.GetInt16(2), reader.GetInt32(3), reader.GetBoolean(4)));
            }
        }
        var decks = new List<object>();
        foreach (var hero in Enum.GetValues<HeroClass>())
        {
            var ids = new List<string>();
            await using (var command = new NpgsqlCommand("SELECT c.card_id FROM player_decks d JOIN player_deck_cards c ON c.deck_id=d.deck_id WHERE d.player_id=$1 AND d.hero_class=$2 ORDER BY c.slot_index", connection))
            {
                command.Parameters.AddWithValue(profile.UserId);
                command.Parameters.AddWithValue((short)hero);
                await using var reader = await command.ExecuteReaderAsync(ct);
                while (await reader.ReadAsync(ct)) ids.Add(reader.GetString(0));
            }
            DeckRules.Validate(hero, ids, owned);
            var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", HeroClass.Guardian => "GUA", _ => throw new InvalidOperationException() };
            var expected = Enumerable.Range(1, 13).Select(x => $"C{x:D2}").Concat(Enumerable.Range(1, 7).Select(x => $"{prefix}-{x:D2}")).ToArray();
            Check("actual " + hero + " starter20", ids.SequenceEqual(expected));
            decks.Add(new { hero = hero.ToString(), cards = ids, card_level = 0, weapon_level = 0, deck_rules_validated = true });
        }
        Check("three initial weapons level0", await Count("SELECT count(*) FROM class_weapons WHERE player_id=$1 AND level=0") == 3);
        Check("initial permanent wallets zero", await Count("SELECT gold+diamond FROM player_wallets WHERE player_id=$1") == 0);
        Check("initial permanent materials zero", await Count("SELECT warrior_soul+priest_soul+mage_soul+guardian_soul+equipment_fragments FROM player_materials WHERE player_id=$1") == 0);
        Check("initial consumables zero", await Count("SELECT health_potion_count+advanced_bag_count+top_bag_count FROM player_consumables WHERE player_id=$1") == 0);
        Check("initial physical equipment zero", await Count("SELECT count(*) FROM equipments WHERE owner_id=$1") == 0);
        Check("initial seasonal balance zero", await Count("SELECT gold+equipment_fragments+challenge_marks+blueprint_marks+orange_blueprint_marks FROM player_season_wallets WHERE player_id=$1 AND season_id='f01-preflight-r1'") == 0);
        Check("actual season entry starts D0", await seasonRepository.GetUnlockedDifficultyAsync(profile.UserId, season.SeasonId, ct) == 0);
        actual = new { actual_normal_local_account = true, debug_prefixes_excluded = new[] { "test_", "test2_" }, decks,
            initial_permanent_gold = 0, initial_diamonds = 0, initial_souls = 0, initial_fragments = 0,
            initial_potions = 0, initial_season_gold = 0, initial_season_fragments = 0, initial_marks = 0,
            initial_equipment_count = 0, initial_unlocked_difficulty = 0,
            returning_and_skilled_permanent5_is_still_an_explicit_historical_fixture_not_proven_account_history = true };
    }
}
finally
{
    if (created)
    {
        await using (var drop = admin.CreateCommand("DROP SCHEMA " + schema + " CASCADE")) await drop.ExecuteNonQueryAsync();
        await using var verify = admin.CreateCommand("SELECT count(*) FROM information_schema.schemata WHERE schema_name=$1");
        verify.Parameters.AddWithValue(schema);
        dropped = Convert.ToInt64(await verify.ExecuteScalarAsync()) == 0;
    }
    File.WriteAllText(Path.Combine(output, "cleanup.original.json"), JsonSerializer.Serialize(new { schema, created, dropped, production_changed = false }));
}
Check("owned schema removed", dropped);
File.WriteAllText(Path.Combine(output, "result.original.json"), JsonSerializer.Serialize(new { ok = checks.Values.All(x => x), checks,
    config_version = config.Version, config_content_hash = config.ContentHash, actual_initial_state = actual, calendar,
    proposed_attempts_only = 252, actual_gameplay_starts = 0, complete_F01 = false, production_changed = false }, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine(JsonSerializer.Serialize(new { ok = true, checks = checks.Count, actual_gameplay_starts = 0, schema_removed = dropped }));

sealed class FixedClock(DateTimeOffset now) : TimeProvider
{
    public override DateTimeOffset GetUtcNow() => now;
}
