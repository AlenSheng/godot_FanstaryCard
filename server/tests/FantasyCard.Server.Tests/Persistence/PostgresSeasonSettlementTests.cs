using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Tests.Persistence;

public sealed partial class PostgresSeasonSettlementTests
{
    public static bool HasTestDatabase => PostgresRuntimeIntegrationTests.HasTestDatabase;
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task MixedAssetsCommitToTheirOriginalDomainsOnceAndExposeTheReceiptContext()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc);
        var fixture = await SetupAsync(db, clock, definition);
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(db.DataSource, clock, metrics);
        var worn = await EquipmentAsync(db, fixture.Player, definition.SeasonId, definition.StatsVersion);
        var generated = Guid.NewGuid();
        var sourceMatch = await db.ScalarAsync<Guid>("SELECT source_match_id FROM equipments WHERE instance_id=$1", worn);
        var assets = new SettlementAsset[]
        {
            new("Gold", "gold", false, 17), new("EquipmentFragments", "equipment_fragments", false, 5),
            new("WarriorSoul", "warrior_soul", false, 3), new("ClassSoul", "class_soul:Mage", false, 4),
            new("Equipment", worn.ToString("D"), false, Destination: "Equipped"),
            new("Equipment", generated.ToString("D"), false, Equipment: new("Head", "Blue", "Fire", null, "DrawInterval"))
        };
        var receipt = await SettleAsync(repository, fixture, assets);
        Assert.Equal(fixture.Context, receipt.Season);
        Assert.Equal(receipt.SettlementId, (await SettleAsync(repository, fixture, assets)).SettlementId);
        Assert.All(await repository.GetPendingHoldsAsync(Ct), hold => Assert.Equal(fixture.Context, hold.Season));
        Assert.Empty(await repository.GetReadyNotificationsAsync(fixture.Player, Ct));
        Assert.Equal(assets.Length, await repository.CommitHoldsAsync(receipt.SettlementId, Ct));
        Assert.Equal(0, await repository.CommitHoldsAsync(receipt.SettlementId, Ct));
        Assert.Equal(17L, await Balance(db, fixture.Player, definition.SeasonId, "gold"));
        Assert.Equal(5L, await Balance(db, fixture.Player, definition.SeasonId, "equipment_fragments"));
        Assert.Equal(100L, await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", fixture.Player));
        Assert.Equal(200L, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", fixture.Player));
        Assert.Equal(3L, await db.ScalarAsync<long>("SELECT warrior_soul FROM player_materials WHERE player_id=$1", fixture.Player));
        Assert.Equal(4L, await db.ScalarAsync<long>("SELECT mage_soul FROM player_materials WHERE player_id=$1", fixture.Player));
        Assert.Equal(sourceMatch, await db.ScalarAsync<Guid>("SELECT source_match_id FROM equipments WHERE instance_id=$1", worn));
        Assert.Equal(fixture.Match, await db.ScalarAsync<Guid>("SELECT source_match_id FROM equipments WHERE instance_id=$1", generated));
        Assert.Equal("NaturalDrop", await db.ScalarAsync<string>("SELECT source_kind FROM equipments WHERE instance_id=$1", generated));
        Assert.Equal("ActiveSeason", await db.ScalarAsync<string>("SELECT asset_scope FROM equipments WHERE instance_id=$1", generated));
        Assert.Equal(2L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND season_id=$2", fixture.Player, definition.SeasonId));
        Assert.Equal(4L, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND season_id=$2 AND reason='settlement.commit'", fixture.Player, definition.SeasonId));
        Assert.Equal(4L, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND season_id=$2 AND difficulty_id='D0' AND ruleset_id='season-v1' AND config_version=$3 AND stats_version=$4", fixture.Player, definition.SeasonId, definition.ConfigVersion, definition.StatsVersion));
        Assert.Equal(2L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND season_id=$2 AND difficulty_id='D0' AND ruleset_id='season-v1' AND config_version=$3 AND stats_version=$4 AND request_id IS NOT NULL", fixture.Player, definition.SeasonId, definition.ConfigVersion, definition.StatsVersion));
        var read = await repository.GetAsync(fixture.Player, receipt.SettlementId, Ct);
        Assert.Equal(definition.SeasonId, read.Season!.SeasonId);
        Assert.Equal("D0", read.Season.DifficultyId);
        Assert.Single(await repository.GetReadyNotificationsAsync(fixture.Player, Ct));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task LateCommitCreditsArchivedWalletAndCannotOverwriteTheNextSeasonLoadout()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc);
        var fixture = await SetupAsync(db, clock, definition);
        var oldItem = await EquipmentAsync(db, fixture.Player, definition.SeasonId, definition.StatsVersion);
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(db.DataSource, clock, metrics);
        var generated = Guid.NewGuid();
        var receipt = await SettleAsync(repository, fixture,
            [new("Gold", "gold", false, 37), new("EquipmentFragments", "equipment_fragments", false, 9), new("Equipment", oldItem.ToString("D"), false, Destination: "Equipped"),
                new("Equipment", generated.ToString("D"), false, Equipment: new("Head", "Blue", "Fire", null, "DrawInterval"), Destination: "Equipped")]);
        var next = new SeasonDefinition("next", "season-v1", definition.ConfigVersion, "next-stats", definition.EndsAtUtc, definition.EndsAtUtc.AddDays(42), 5);
        var seasons = new SeasonRepository(db.DataSource, clock);
        await seasons.PublishAsync(next, new string('b', 64), Ct);
        clock.Now = next.StartsAtUtc;
        await seasons.EnsurePlayerAsync(fixture.Player, next.ContextFor(0), Ct);
        await Sql(db, "WITH states AS (UPDATE player_season_state SET archived_at=$3 WHERE player_id=$1 AND season_id=$2 RETURNING player_id) UPDATE player_season_wallets SET archived_at=$3 WHERE player_id=$1 AND season_id=$2", fixture.Player, definition.SeasonId, clock.Now);
        var nextItem = await EquipmentAsync(db, fixture.Player, next.SeasonId, next.StatsVersion, "Equipped");
        await Sql(db, "UPDATE player_loadouts SET feet_id=$2 WHERE player_id=$1 AND hero_class=2", fixture.Player, nextItem);
        var version = await db.ScalarAsync<long>("SELECT version FROM player_loadouts WHERE player_id=$1 AND hero_class=2", fixture.Player);
        Assert.Equal(4, await new SettlementRepository(db.DataSource, clock, metrics).CommitHoldsAsync(receipt.SettlementId, Ct));
        Assert.Equal(37L, await Balance(db, fixture.Player, definition.SeasonId, "gold"));
        Assert.Equal(9L, await Balance(db, fixture.Player, definition.SeasonId, "equipment_fragments"));
        Assert.Equal(0L, await Balance(db, fixture.Player, next.SeasonId, "gold"));
        Assert.Equal("ArchivedSeason", await db.ScalarAsync<string>("SELECT asset_scope FROM equipments WHERE instance_id=$1", oldItem));
        Assert.Equal("Inventory", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", oldItem));
        Assert.Equal("ArchivedSeason", await db.ScalarAsync<string>("SELECT asset_scope FROM equipments WHERE instance_id=$1", generated));
        Assert.Equal("Inventory", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", generated));
        Assert.Equal(nextItem, await db.ScalarAsync<Guid>("SELECT feet_id FROM player_loadouts WHERE player_id=$1 AND hero_class=2", fixture.Player));
        Assert.Equal(version, await db.ScalarAsync<long>("SELECT version FROM player_loadouts WHERE player_id=$1 AND hero_class=2", fixture.Player));
        Assert.Equal(definition.SeasonId, (await repository.GetForMatchAsync(fixture.Player, fixture.Match, Ct)).Season!.SeasonId);
        using var economy = new EconomyRepository(db.DataSource, clock);
        var bootstrap = new BootstrapRepository(db.DataSource, new ProgressionRepository(db.DataSource, clock), economy,
            new MailRepository(db.DataSource, clock), new PreparationRepository(db.DataSource, clock), clock);
        Assert.Equal(definition.SeasonId, (await bootstrap.GetSettlementAsync(fixture.Player, fixture.Match, Ct)).UnfinishedSettlement!.Season!.SeasonId);
        var fullBootstrap = await bootstrap.GetAsync(fixture.Profile, Ct);
        Assert.Equal(definition.SeasonId, fullBootstrap.UnfinishedSettlement!.Season!.SeasonId);
        Assert.Equal(0L, fullBootstrap.Wallet.Gold);
    }

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData("legacy")]
    [InlineData("stats")]
    [InlineData("archived")]
    [Trait("Category", "PostgresIntegration")]
    public async Task InvalidEquipmentDomainRollsBackEveryAssetAndKeepsHoldsPending(string invalid)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc);
        var fixture = await SetupAsync(db, clock, definition);
        var item = await EquipmentAsync(db, fixture.Player, invalid == "legacy" ? null : definition.SeasonId,
            invalid == "legacy" ? null : invalid == "stats" ? "wrong-stats" : definition.StatsVersion,
            scope: invalid == "archived" ? "ArchivedSeason" : "ActiveSeason");
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(db.DataSource, clock, metrics);
        var receipt = await SettleAsync(repository, fixture, [new("Gold", "gold", false, 50), new("Equipment", item.ToString("D"), false)]);
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.CommitHoldsAsync(receipt.SettlementId, Ct));
        Assert.Equal(0L, await Balance(db, fixture.Player, definition.SeasonId, "gold"));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE player_id=$1", fixture.Player));
        Assert.Equal(2L, await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'", receipt.SettlementId));
        Assert.Equal("InMatchEquipped", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", item));
        Assert.Empty(await repository.GetReadyNotificationsAsync(fixture.Player, Ct));
    }

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData("missing")]
    [InlineData("difficulty")]
    [InlineData("stats")]
    [InlineData("config")]
    [InlineData("room")]
    [Trait("Category", "PostgresIntegration")]
    public async Task CallerContextMismatchCannotCreateAReceipt(string invalid)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc);
        var fixture = await SetupAsync(db, clock, definition);
        var context = invalid == "missing" ? null : new SeasonContext(definition.SeasonId, invalid == "difficulty" ? 1 : 0,
            "season-v1", invalid == "config" ? "other-config" : definition.ConfigVersion, invalid == "stats" ? "other-stats" : definition.StatsVersion);
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(db.DataSource, clock, metrics);
        var details = JsonSerializer.SerializeToElement(new { roomId = invalid == "room" ? Guid.NewGuid() : fixture.Room, heroClass = "Mage" });
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.SettleAsync(fixture.Match, fixture.Player, "Extracted", details,
            [new("Gold", "gold", false, 11)], Ct, context));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements"));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds"));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task ConcurrentAndRecreatedRepositoryCommitsCreditExactlyOnce()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc);
        var fixture = await SetupAsync(db, clock, definition);
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(db.DataSource, clock, metrics);
        var receipt = await SettleAsync(repository, fixture, [new("Gold", "gold", false, 23), new("EquipmentFragments", "equipment_fragments", false, 7)]);
        var results = await Task.WhenAll(repository.CommitHoldsAsync(receipt.SettlementId, Ct),
            new SettlementRepository(db.DataSource, clock, metrics).CommitHoldsAsync(receipt.SettlementId, Ct));
        Assert.Equal(2, results.Sum());
        Assert.Equal(23L, await Balance(db, fixture.Player, definition.SeasonId, "gold"));
        Assert.Equal(7L, await Balance(db, fixture.Player, definition.SeasonId, "equipment_fragments"));
        Assert.Equal(2L, await db.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE player_id=$1", fixture.Player));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task WalletOperationProtectsReplayAndRejectsChangedHoldBusinessData()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc);
        var fixture = await SetupAsync(db, clock, definition);
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(db.DataSource, clock, metrics);
        var receipt = await SettleAsync(repository, fixture, [new("Gold", "gold", false, 11)]);
        await repository.CommitHoldsAsync(receipt.SettlementId, Ct);
        await Sql(db, "UPDATE settlement_asset_holds SET state='Pending' WHERE settlement_id=$1", receipt.SettlementId);
        await repository.CommitHoldsAsync(receipt.SettlementId, Ct);
        Assert.Equal(11L, await Balance(db, fixture.Player, definition.SeasonId, "gold"));
        await Sql(db, "UPDATE settlement_asset_holds SET state='Pending',asset_snapshot=jsonb_set(asset_snapshot,'{Quantity}','12') WHERE settlement_id=$1", receipt.SettlementId);
        await Assert.ThrowsAsync<FantasyCard.Domain.Players.DomainValidationException>(() => repository.CommitHoldsAsync(receipt.SettlementId, Ct));
        Assert.Equal(11L, await Balance(db, fixture.Player, definition.SeasonId, "gold"));
        Assert.Equal(1L, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND currency='Gold' AND reason='settlement.commit'", fixture.Player));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task AScopedHoldCannotLoseItsContextAndFallBackToLegacyMoney()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc);
        var fixture = await SetupAsync(db, clock, definition);
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(db.DataSource, clock, metrics);
        var receipt = await SettleAsync(repository, fixture, [new("Gold", "gold", false, 11)]);
        await Sql(db, "UPDATE settlement_asset_holds SET season_id=NULL,difficulty_id=NULL,ruleset_id=NULL,config_version=NULL,stats_version=NULL WHERE settlement_id=$1", receipt.SettlementId);
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.CommitHoldsAsync(receipt.SettlementId, Ct));
        Assert.Equal(100L, await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", fixture.Player));
        Assert.Equal(0L, await Balance(db, fixture.Player, definition.SeasonId, "gold"));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task TerminalRoomObservationPassesItsPinnedContextIntoSettlement()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc);
        var fixture = await SetupAsync(db, clock, definition);
        var room = new BattleRoom(fixture.Room, definition.ConfigVersion, CombatCardCatalog.CreatePrototype(), 73, season: fixture.Context);
        var cards = Enumerable.Range(1, 13).Select(i => $"C{i:D2}").Concat(Enumerable.Range(1, 7).Select(i => $"MAG-{i:D2}")).ToArray();
        var player = room.AddPlayer(new(fixture.Player, HeroClass.Mage, cards, null));
        Assert.True(player.Inventory.TryAdd(new ExplorationItem("gold", ExplorationItemKind.Gold, 13)));
        var snapshot = room.Capture();
        snapshot = snapshot with { Players = snapshot.Players.Select(value => value with { Phase = RoomPlayerPhase.Extracted }).ToArray() };
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(db.DataSource, clock, metrics);
        await new SettlementCoordinator(repository, clock).ObserveAsync(fixture.Match, snapshot);
        var receipt = await repository.GetForMatchAsync(fixture.Player, fixture.Match, Ct);
        Assert.Equal(definition.SeasonId, receipt.Season!.SeasonId);
        await repository.CommitHoldsAsync(receipt.SettlementId, Ct);
        Assert.Equal(13L, await Balance(db, fixture.Player, definition.SeasonId, "gold"));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task APreSeasonLegacyMatchFinishesInLegacyAccountsWithoutReplacingSeasonLoadouts()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc.AddMinutes(-1));
        var seasons = new SeasonRepository(db.DataSource, clock);
        await seasons.PublishAsync(definition, new string('a', 64), Ct);
        var key = Guid.NewGuid().ToString("N");
        var player = (await new IdentityRepository(db.DataSource, new PlayerProvisioningService()).SignInLocalAsync(key,
            "Legacy " + key[..10], RandomNumberGenerator.GetBytes(32), clock.Now, clock.Now.AddHours(1), Ct)).UserId;
        await Sql(db, "UPDATE player_wallets SET gold=0 WHERE player_id=$1", player);
        var match = Guid.NewGuid(); var room = Guid.NewGuid();
        await Sql(db, "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',73,$3,'Running',$4)", match, room, definition.ConfigVersion, clock.Now);
        await Sql(db, "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')", match, player);
        var oldItem = await EquipmentAsync(db, player, null, null);
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(db.DataSource, clock, metrics);
        var receipt = await repository.SettleAsync(match, player, "Extracted", JsonSerializer.SerializeToElement(new { roomId = room, heroClass = "Mage" }),
            [new("Gold", "gold", false, 9), new("Equipment", oldItem.ToString("D"), false, Destination: "Equipped")], Ct, configVersion: definition.ConfigVersion);
        clock.Now = definition.StartsAtUtc;
        await seasons.EnsurePlayerAsync(player, definition.ContextFor(0), Ct);
        var current = await EquipmentAsync(db, player, definition.SeasonId, definition.StatsVersion, "Equipped");
        await Sql(db, "UPDATE player_loadouts SET feet_id=$2 WHERE player_id=$1 AND hero_class=2", player, current);
        await repository.CommitHoldsAsync(receipt.SettlementId, Ct);
        Assert.Equal(9L, await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player));
        Assert.Equal(0L, await Balance(db, player, definition.SeasonId, "gold"));
        Assert.Equal(current, await db.ScalarAsync<Guid>("SELECT feet_id FROM player_loadouts WHERE player_id=$1 AND hero_class=2", player));
        Assert.Equal("Inventory", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", oldItem));
        Assert.Null((await repository.GetAsync(player, receipt.SettlementId, Ct)).Season);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task ADelayedSameSeasonCommitCannotReplaceAnAlreadyPreparedNewLoadout()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc);
        var fixture = await SetupAsync(db, clock, definition);
        var oldItem = await EquipmentAsync(db, fixture.Player, definition.SeasonId, definition.StatsVersion);
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(db.DataSource, clock, metrics);
        var receipt = await SettleAsync(repository, fixture, [new("Equipment", oldItem.ToString("D"), false, Destination: "Equipped")]);
        var current = await EquipmentAsync(db, fixture.Player, definition.SeasonId, definition.StatsVersion, "Equipped");
        await Sql(db, "UPDATE player_loadouts SET feet_id=$2 WHERE player_id=$1 AND hero_class=2", fixture.Player, current);
        var version = await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2", fixture.Player);
        var prepared = await new PreparationRepository(db.DataSource, clock).CreateAsync(fixture.Player, "prepare-next",
            new(FantasyCard.Contracts.Players.HeroClassDto.Mage, version, [null,null,null,null,current],
                FantasyCard.Contracts.Matchmaking.BackpackTierDto.Free, [], 0, "D0", definition.SeasonId), Ct);
        Assert.Equal(CreatePreparationStatus.Created, prepared.Status);
        await repository.CommitHoldsAsync(receipt.SettlementId, Ct);
        Assert.Equal("Inventory", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", oldItem));
        Assert.Equal("ActiveSeason", await db.ScalarAsync<string>("SELECT asset_scope FROM equipments WHERE instance_id=$1", oldItem));
        Assert.Equal("PreparationLocked", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", current));
        Assert.Equal(current, await db.ScalarAsync<Guid>("SELECT feet_id FROM player_loadouts WHERE player_id=$1 AND hero_class=2", fixture.Player));
    }

    private static SeasonDefinition Define() => SeasonDefinition.FromCalendarDays("original", new DateOnly(2026, 11, 2), GameConfigCatalog.Current.Version, "season-equipment-v1", highestOpenDifficulty: 5);
    private static async Task<Fixture> SetupAsync(PostgresTestSchema db, Clock clock, SeasonDefinition definition)
    {
        var seasons = new SeasonRepository(db.DataSource, clock);
        await seasons.PublishAsync(definition, new string('a', 64), Ct);
        var key = Guid.NewGuid().ToString("N");
        var profile = await new IdentityRepository(db.DataSource, new PlayerProvisioningService()).SignInLocalAsync(key,
            "Settle " + key[..10], RandomNumberGenerator.GetBytes(32), clock.Now, clock.Now.AddHours(1), Ct);
        var player = profile.UserId;
        await seasons.EnsurePlayerAsync(player, definition.ContextFor(0), Ct);
        await Sql(db, "WITH wallet AS (UPDATE player_wallets SET gold=100 WHERE player_id=$1 RETURNING player_id) UPDATE player_materials SET equipment_fragments=200,warrior_soul=0,mage_soul=0 WHERE player_id=$1", player);
        var match = Guid.NewGuid(); var room = Guid.NewGuid();
        await Sql(db, "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version) VALUES($1,$2,'ChaosRealm','D0',73,$3,'Running',$4,$5,'season-v1',$6)",
            match, room, definition.ConfigVersion, clock.Now, definition.SeasonId, definition.StatsVersion);
        await Sql(db, "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')", match, player);
        return new(player, match, room, definition.ContextFor(0), profile);
    }
    private static Task<SettlementRecord> SettleAsync(SettlementRepository repository, Fixture fixture, IReadOnlyList<SettlementAsset> assets) =>
        repository.SettleAsync(fixture.Match, fixture.Player, "Extracted", JsonSerializer.SerializeToElement(new { roomId = fixture.Room, heroClass = "Mage" }),
            assets.Select(asset=>asset.Equipment is {SeasonOrigin:null} item ? asset with {Equipment=item with {SeasonOrigin=new(fixture.Context,"NaturalChoice",
                GameConfigCatalog.Current.SeasonLoot(fixture.Context.Difficulty,item.Quality is "White" or "Green"?"outer":"elite").RuleId,
                item.Quality is "White" or "Green"?"outer":"elite",item.Quality,false)}}:asset).ToArray(), Ct, fixture.Context);

    private static async Task<Guid> EquipmentAsync(PostgresTestSchema db, Guid player, string? season, string? stats, string location = "InMatchEquipped", string scope = "ActiveSeason")
    {
        var id = Guid.NewGuid();
        await using var command = db.DataSource.CreateCommand("""
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,created_at,element,origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty,source_match_id)
            VALUES($1,$2,'Feet','Blue',0,$3,CURRENT_TIMESTAMP,'Fire',$4,$4,$5,$6,$7,$8,$9)
            """);
        command.Parameters.AddWithValue(id); command.Parameters.AddWithValue(player); command.Parameters.AddWithValue(location);
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, (object?)season ?? DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, season is null ? DBNull.Value : scope);
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, (object?)stats ?? DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, season is null ? DBNull.Value : "NaturalDrop");
        command.Parameters.AddWithValue(NpgsqlDbType.Smallint, season is null ? DBNull.Value : (short)0);
        command.Parameters.AddWithValue(Guid.NewGuid()); await command.ExecuteNonQueryAsync(Ct);
        return id;
    }
    private static Task<long> Balance(PostgresTestSchema db, Guid player, string season, string column) =>
        db.ScalarAsync<long>($"SELECT {column} FROM player_season_wallets WHERE player_id=$1 AND season_id=$2", player, season);
    private static async Task Sql(PostgresTestSchema db, string sql, params object[] values)
    {
        await using var command = db.DataSource.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(Ct);
    }
    private sealed record Fixture(Guid Player, Guid Match, Guid Room, SeasonContext Context, PlayerProfile Profile);
    private sealed class Clock(DateTimeOffset now) : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = now;
        public override DateTimeOffset GetUtcNow() => Now;
    }
}
