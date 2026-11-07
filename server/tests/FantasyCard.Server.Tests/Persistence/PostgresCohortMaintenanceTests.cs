using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Config;

namespace FantasyCard.Server.Tests.Persistence;

/// <summary>Import observed simulation snapshots, then prove disposal through the actual repository. No new gameplay.</summary>
public sealed class PostgresCohortMaintenanceTests
{
    public static bool Enabled => PostgresMigrationTests.HasTestDatabase && SeasonCohortMaintenanceTests.Enabled;
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact(Skip = "Requires explicit nine-bank plan and isolated PostgreSQL.", SkipUnless = nameof(Enabled))]
    [Trait("Category", "PostgresIntegration")]
    public async Task OriginalBankIdsDiscardThroughRealTransactionsAndRestartReplayWithoutRefund()
    {
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_D03_MAINTENANCE_OUTPUT") ?? throw new InvalidOperationException("Owned output required.");
        Assert.False(Directory.Exists(output)); Directory.CreateDirectory(output);
        var schemaOutput = Environment.GetEnvironmentVariable("FANTASYCARD_DISCARD_SCHEMA_EVIDENCE") ?? throw new InvalidOperationException("Owned schema log required.");
        var config = GameConfigCatalog.Current;
        var season = SeasonDefinition.FromCalendarDays("d03-cohorts", new(2026, 11, 1), config.Version, "season-equipment-v1", highestOpenDifficulty: 5);
        var clock = new CraftingClock(season.StartsAtUtc.AddHours(2));
        var rows = SeasonCohortMaintenance.Inputs(); Assert.Equal(9, rows.Length);
        var summaries = new List<object>();
        foreach (var row in rows)
        {
            // Independent simulations may reuse deterministic loot IDs. Preserve the exact originals;
            // each bank gets its own schema rather than renaming IDs or pretending they coexisted.
            await using var db = await PostgresTestSchema.CreateAsync(false);
            File.AppendAllText(schemaOutput, JsonSerializer.Serialize(new { row.Id,
                schema = new Npgsql.NpgsqlConnectionStringBuilder(db.ConnectionString).SearchPath }) + Environment.NewLine);
            await db.MigrateAsync();
            var seasons = new SeasonRepository(db.DataSource, clock);
            await seasons.PublishAsync(season, config.ContentHash, Ct);
            var bank = SeasonCohortMaintenance.Load(row);
            var initialJson = JsonSerializer.Serialize(bank);
            var initial = JsonSerializer.Deserialize<SeasonCohortBank>(initialJson)!;
            var player = await CraftingTestInputs.PlayerAsync(db, clock);
            await seasons.EnsurePlayerAsync(player, season.ContextFor(0), Ct);
            await CraftingTestInputs.SqlAsync(db, "UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1", player);
            // These are snapshot imports, not new income or a replay of the old matches.
            await CraftingTestInputs.SqlAsync(db, "UPDATE player_season_wallets SET gold=$2,equipment_fragments=$3,blueprint_marks=$4,orange_blueprint_marks=$5 WHERE player_id=$1",
                player, bank.Gold, bank.Fragments, bank.Blueprints, bank.OrangeBlueprints);
            var importContexts = new List<object>();
            foreach (var owned in bank.Items.Concat(bank.Overflow))
            {
                var item = owned.Item; var e = item.Equipment!;
                // The old bank deliberately did not save a mint difficulty for model crafts/initial fixtures.
                // Keep that historical null in the bank. A separate legal D5 import fixture lets the current
                // repository validate disposal, without claiming to reconstruct the old mint transaction.
                var originalDifficulty = e.SeasonOrigin?.Season.Difficulty;
                var fixtureDifficulty = originalDifficulty ?? 5;
                importContexts.Add(new { item.ItemId, original_generated_difficulty = originalDifficulty,
                    fixture_generated_difficulty = fixtureDifficulty, fixture_only_when_original_unknown = originalDifficulty is null });
                await CraftingTestInputs.SqlAsync(db, """
                    INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,effect_affix,secondary_trait,
                        origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty,recipe_extracted,unique_affix,unique_element)
                    VALUES($1,$2,$3,$4,$5,$6,'Inventory',$7,$8,$9,$10,$11,$12,$12,'ActiveSeason','season-equipment-v1',$13,$14,$15,$16,$17)
                    """, Guid.Parse(item.ItemId), player, e.Slot, e.Quality, e.Level, e.IsBound, (long)owned.Version, clock.Now,
                    e.Element, (object?)e.EffectAffix ?? DBNull.Value, (object?)e.SecondaryTrait ?? DBNull.Value, season.SeasonId, owned.Source,
                    fixtureDifficulty, owned.Learned, (object?)e.UniqueAffix ?? DBNull.Value, (object?)e.UniqueElement ?? DBNull.Value);
            }
            var walletBefore = await db.ScalarAsync<string>("SELECT row_to_json(w)::text FROM player_season_wallets w WHERE player_id=$1", player);
            var permanentBefore = await db.ScalarAsync<string>("SELECT row_to_json(w)::text FROM player_wallets w WHERE player_id=$1", player);
            var bodiesBefore = await db.ScalarAsync<string>("SELECT jsonb_agg(to_jsonb(e)-'location'-'version' ORDER BY instance_id)::text FROM equipments e WHERE owner_id=$1", player);
            var requests = SeasonCohortMaintenance.PlanDisposal(bank, config);
            DiscardEquipmentResponse? response = null;
            if (requests.Length > 0)
            {
                var request = new DiscardEquipmentRequest(requests.Select(x => new DiscardEquipmentItemRequest(Guid.Parse(x.Item.ItemId), x.Version)).ToArray(), season.SeasonId);
                var repository = new ProgressionRepository(db.DataSource, clock);
                response = await repository.DiscardEquipmentAsync(player, "d03-maintenance-" + row.Id, request, Ct);
                Assert.Equal(requests.Length, response.Items.Count);
                foreach (var item in response.Items)
                {
                    var before = Assert.Single(requests, x => Guid.Parse(x.Item.ItemId) == item.InstanceId);
                    Assert.Equal("Recycled", item.Location); Assert.Equal(before.Version + 1L, item.Version);
                }
                var replay = await new ProgressionRepository(db.DataSource, clock).DiscardEquipmentAsync(player, "d03-maintenance-" + row.Id,
                    request with { Items = request.Items!.Reverse().ToArray() }, Ct);
                Assert.Equivalent(response, replay, strict: true);
                SeasonCohortMaintenance.ApplyDisposal(bank, requests);
                Assert.Equal(requests.Length, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND reason='equipment.discard'", player));
                Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_discard_batches WHERE player_id=$1", player));
            }
            Assert.Equal(walletBefore, await db.ScalarAsync<string>("SELECT row_to_json(w)::text FROM player_season_wallets w WHERE player_id=$1", player));
            Assert.Equal(permanentBefore, await db.ScalarAsync<string>("SELECT row_to_json(w)::text FROM player_wallets w WHERE player_id=$1", player));
            Assert.Equal(bodiesBefore, await db.ScalarAsync<string>("SELECT jsonb_agg(to_jsonb(e)-'location'-'version' ORDER BY instance_id)::text FROM equipments e WHERE owner_id=$1", player));
            Assert.Equal(bank.Items.Count + bank.Overflow.Count, await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1 AND location='Inventory'", player));
            Assert.Equal(initial.Recipes, bank.Recipes); Assert.Equal(initial.Wishes, bank.Wishes);
            Assert.Equal(initial.Attempts, bank.Attempts); Assert.Equal(initial.Deaths, bank.Deaths);
            bank.SelectionPolicy = SeasonCohortMaintenance.Policy; bank.Check();
            File.WriteAllText(Path.Combine(output, row.Id + ".bank-after-pg.original.json"), JsonSerializer.Serialize(bank));
            File.WriteAllText(Path.Combine(output, row.Id + ".receipt.original.json"), JsonSerializer.Serialize(new { row, snapshot_import = true,
                original_censor = initial.StopReason, requests, response, walletBefore, permanentBefore, bodiesBefore,
                importContexts, old_match_history_replayed = false, historical_mint_metadata_reconstructed = false,
                recipes_and_wishes_preserved_in_bank_only = true }));
            summaries.Add(new { bank.Id, bank.Attempts, old_censor = initial.StopReason, current_censor = bank.StopReason,
                discarded = requests.Length, owned = bank.Items.Count, overflow = bank.Overflow.Count });
        }
        File.WriteAllText(Path.Combine(output, "summary.original.json"), JsonSerializer.Serialize(new { new_matches = 0, config.Version, config.ContentHash, summaries }));
    }
}
