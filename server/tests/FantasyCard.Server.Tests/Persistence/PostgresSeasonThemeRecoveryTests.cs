using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Tests.Config;
using Microsoft.Extensions.Logging.Abstractions;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonThemeRecoveryTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    [InlineData("valid")][InlineData("missing")][InlineData("corrupt")]
    public async Task RecreatedRecoveryWorkerUsesOriginalFireBundleRatherThanNewWoodAndRetainsFailures(string archiveState)
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);using var archive=new ConfigArchiveDirectory();
        var p=await JourneyTestInputs.Create(db);var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);
        var deck=(await new ProgressionRepository(db.DataSource,p.Clock).GetDecksAsync(p.Player,Ct)).Single(d=>d.HeroClass==HeroClassDto.Mage);
        var prepared=await new PreparationRepository(db.DataSource,p.Clock).CreateAsync(p.Player,Guid.NewGuid().ToString("N"),
            new(HeroClassDto.Mage,deck.Version,[null,null,null,null,null],BackpackTierDto.Free,[],0,"D0",p.Season.SeasonId),Ct);
        Assert.Equal(CreatePreparationStatus.Created,prepared.Status);var preparation=prepared.Preparation!;
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,73,season:p.Season.ContextFor(0));
        room.AddPlayer(new(p.Player,HeroClass.Mage,preparation.Snapshot.CardIds,null,CardLevels:preparation.Snapshot.CardLevels,LootPreferenceElement:preparation.Snapshot.LootPreferenceElement));
        room.InitializeMap(ChaosMapGenerator.Generate(73,1,config.SeasonThemes));var snapshot=room.Capture();var cell=snapshot.Map!.Cells.Single(c=>c.IsBoss);
        // A declared checkpoint fixture, not a full movement or fight route.
        snapshot=snapshot with {Players=[snapshot.Players[0] with {Position=cell.Position,Phase=RoomPlayerPhase.Pve,
            Pve=PveBattleFactory.Create(cell,config.SeasonDifficulty(0),config.SeasonThemes!.Selected).Capture()}]};
        room=BattleRoom.Restore(snapshot,catalog,73);var boss=Assert.Single(room.GetPlayer(p.Player).Pve!.Monsters);
        boss.TakeDamage(boss.Shield+boss.MaximumHp/3);boss.ResolveUtilityIntent(new(MonsterIntentKind.Shield,10,CardElement.None));snapshot=room.Capture();
        var match=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm','D0',73,$3,'Running',$4,$5,'season-v1',$6)
            """,match,room.RoomId,config.Version,p.Clock.Now,p.Season.SeasonId,p.Season.StatsVersion);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,preparation_id,is_bot,state) VALUES($1,$2,$3,false,'Active')",match,p.Player,preparation.PreparationId);
        await CraftingTestInputs.SqlAsync(db,"UPDATE preparations SET status='Matched' WHERE preparation_id=$1",preparation.PreparationId);
        using var metrics=new ServerMetrics();var snapshots=new RoomSnapshotRepository(db.DataSource,p.Clock,metrics);await snapshots.SaveIfDueAsync(snapshot,Ct);
        var raw=await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1",room.RoomId);
        if(archiveState!="missing")
        {
            var bytes=config.ExportPublishedBytes();if(archiveState=="corrupt")bytes[^1]^=1;
            PublishedConfigTestInputs.Store(archive.Root,config.Version,bytes,config.ContentHash);
        }
        var next=SeasonThemeConfigIntegrationTests.Variant("Wood");var state=new RoomRecoveryState();
        await using var rooms=new RoomRegistry(p.Clock);
        await new RoomRecoveryWorker(snapshots,rooms,state,p.Clock,NullLogger<RoomRecoveryWorker>.Instance,new PublishedConfigCatalogs(next,archive.Root)).StartAsync(Ct);
        if(archiveState=="valid")
        {
            Assert.True(state.Capture().IsHealthy);Assert.True(rooms.TryGetForPlayer(p.Player,out var actor));
            var recovered=await actor!.ExecuteAsync(new GetRoomSnapshotCommand(),Ct);var savedBoss=Assert.Single(recovered.Players[0].Pve!.Monsters);
            Assert.Equal("Fire",savedBoss.ThemeProfile!.ThemeId);Assert.Equal(boss.ThemeShieldGenerated,savedBoss.ThemeShieldGenerated);
            Assert.Equal(config.Version,recovered.ConfigVersion);Assert.Equal(p.Season.ContextFor(0),recovered.Season);
        }
        else
        {
            Assert.False(state.Capture().IsHealthy);Assert.False(rooms.ContainsRoom(room.RoomId));
            Assert.Equal([room.RoomId],state.Capture().FailedRoomIds);
            Assert.Equal(raw,await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1",room.RoomId));
        }
    }
}
