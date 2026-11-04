using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Settlement;

namespace FantasyCard.Server.Tests.Persistence;

public sealed partial class PostgresSeasonSettlementTests
{
    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task NewlyGeneratedAbsentTraitCannotMintOrCommitEarlierCurrencyAndPendingHoldsRemainReleasable()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var definition=Define();var clock=new Clock(definition.StartsAtUtc);
        var f=await SetupAsync(db,clock,definition);using var metrics=new ServerMetrics();var repository=new SettlementRepository(db.DataSource,clock,metrics);
        var item=Guid.NewGuid();var receipt=await SettleAsync(repository,f,[new("Gold","gold",false,9),new("Equipment",item.ToString("D"),false,Equipment:new("Head","Blue","Fire",null,null))]);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>repository.CommitHoldsAsync(receipt.SettlementId,Ct));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT gold FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",f.Player,definition.SeasonId));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1",item));
        Assert.Equal(2L,await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'",receipt.SettlementId));
        Assert.Equal(2,await repository.ReleaseHoldsAsync(receipt.SettlementId,Ct));Assert.Equal(0,await repository.ReleaseHoldsAsync(receipt.SettlementId,Ct));
    }
}
