using System.Text.Json;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;

namespace FantasyCard.Server.Tests.Persistence;

public sealed partial class PostgresSeasonPreparationTests
{
    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData("None")] [InlineData("fire")] [InlineData("")]
    [Trait("Category","PostgresIntegration")]
    public async Task InvalidLootPreferencesRollbackAllPreparationState(string preference)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        var player=await PlayerAsync(db);var season=Define();var clock=new Clock(season.StartsAtUtc);
        await new SeasonRepository(db.DataSource,clock).PublishAsync(season,GameConfigCatalog.Current.ContentHash,Ct);
        var request=await RequestAsync(db,player,"D0");
        var repository=new PreparationRepository(db.DataSource,clock);
        await Assert.ThrowsAsync<DomainValidationException>(()=>repository.CreateAsync(player,"same-preference",request with {LootPreferenceElement=preference},Ct));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE player_id=$1",player));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM player_season_wallets WHERE player_id=$1",player));
        var accepted=await repository.CreateAsync(player,"same-preference",request with {LootPreferenceElement="Water"},Ct);
        Assert.Equal(CreatePreparationStatus.Created,accepted.Status);
        Assert.Equal("Water",accepted.Preparation!.Snapshot.LootPreferenceElement);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task PreferenceParticipatesInDurableReplayIdentityAndCannotChangeUnderTheSameKey()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        var player=await PlayerAsync(db);var season=Define();var clock=new Clock(season.StartsAtUtc);
        await new SeasonRepository(db.DataSource,clock).PublishAsync(season,GameConfigCatalog.Current.ContentHash,Ct);
        var request=(await RequestAsync(db,player,"D0")) with {LootPreferenceElement="Water"};
        var repository=new PreparationRepository(db.DataSource,clock);
        var first=await repository.CreateAsync(player,"preference-replay",request,Ct);
        Assert.Equal(CreatePreparationStatus.Created,first.Status);
        var replay=await new PreparationRepository(db.DataSource,clock).CreateAsync(player,"preference-replay",request,Ct);
        Assert.Equal(CreatePreparationStatus.Replayed,replay.Status);
        Assert.Equal(first.Preparation!.PreparationId,replay.Preparation!.PreparationId);
        Assert.Equal("Water",replay.Preparation.Snapshot.LootPreferenceElement);
        var conflict=await repository.CreateAsync(player,"preference-replay",request with {LootPreferenceElement="Fire"},Ct);
        Assert.Equal(CreatePreparationStatus.RequestConflict,conflict.Status);
    }
}

public sealed partial class PostgresSeasonRoomTests
{
    private static readonly JsonSerializerOptions LootPreferenceJson=new(JsonSerializerDefaults.Web);
    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData("change")] [InlineData("erase")] [InlineData("remove")]
    [Trait("Category","PostgresIntegration")]
    public async Task OriginalPreparationRejectsChangedMissingOrRemovedPreferenceOnEveryRead(string mutation)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        var season=Define();var clock=new Clock(season.StartsAtUtc);
        await new SeasonRepository(db.DataSource,clock).PublishAsync(season,GameConfigCatalog.Current.ContentHash,Ct);
        var fixture=await RoomAsync(db,clock,season.ContextFor(0));
        using var metrics=new ServerMetrics();var repository=new RoomSnapshotRepository(db.DataSource,clock,metrics);
        var original=fixture.Room.Capture();await repository.SaveIfDueAsync(original,Ct);
        var raw=await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1",original.RoomId);
        var changed=original with {Revision=original.Revision+20,Players=mutation=="remove"?[]:
            original.Players.Select(player=>player with {LootPreferenceElement=mutation=="erase"?null:"Fire"}).ToArray()};
        await Assert.ThrowsAsync<InvalidOperationException>(()=>repository.SaveIfDueAsync(changed,Ct));
        Assert.Equal(raw,await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1",original.RoomId));
        var json=JsonSerializer.Serialize(changed,LootPreferenceJson);
        await Sql(db,"UPDATE room_snapshots SET snapshot_json=$2::jsonb WHERE room_id=$1",original.RoomId,json);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>repository.GetAsync(original.RoomId,Ct));
        Assert.NotNull(Assert.Single(await repository.GetRunningAsync(Ct)).ReadError);
        await Sql(db,"UPDATE match_players SET state='Settled' WHERE match_id=$1",fixture.Match);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>repository.GetOwnedTerminalAsync(fixture.Player,original.RoomId,fixture.Match,Ct));
    }
}
