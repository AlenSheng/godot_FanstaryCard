using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Progression;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonCraftingTests
{
    private static readonly int[] SwitchedWishFailures=[1,1,2,0];
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task OpaqueLegacyMarksArePreservedAndCannotBuyASeasonCraft()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db);
        var state=await p.Progression.GetSeasonCraftingAsync(p.Player,Ct);Assert.Equal(77,state.Wallet!.ChallengeMarks);
        Assert.Equal(0,state.Wallet.BlueprintMarks);Assert.Equal(0,state.Wallet.OrangeBlueprintMarks);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Progression.CraftSeasonEquipmentAsync(p.Player,"empty",new(p.Season.SeasonId,"Purple","Head","Water","Vitality",state.Wallet.Version),Ct));
        Assert.Equal(77L,await db.ScalarAsync<long>("SELECT challenge_marks FROM player_season_wallets WHERE player_id=$1",p.Player));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM player_crafting_wishes"));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task MixedTypedPaymentTargetsTheSelectedSlotAndElementAndReplaysAfterRestartAndCacheExpiry()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db,_=>0);
        var wallet=await CraftingTestInputs.FundAsync(db,p,1,3);var request=new CraftEquipmentRequest(p.Season.SeasonId,"Purple","Hands","Water","Vitality",wallet.Version);
        var results=await Task.WhenAll(Enumerable.Range(0,2).Select(_=>p.Progression.CraftSeasonEquipmentAsync(p.Player,"same",request,Ct)));
        Assert.Equal(results[0],results[1]);var result=results[0];
        Assert.Equal("Hands",result.Equipment.Slot);Assert.Equal("Water",result.Equipment.Element);Assert.Equal("MarkCraft",result.Equipment.SourceKind);
        Assert.Equal(1,result.BlueprintsSpent);Assert.Equal(3,result.OrangeBlueprintsSpent);Assert.Equal(1,result.Wish.Failures);
        await CraftingTestInputs.SqlAsync(db,"DELETE FROM idempotency_records WHERE player_id=$1",p.Player);
        p.Clock.Now=p.Season.EndsAtUtc;
        Assert.Equal(result,await new ProgressionRepository(db.DataSource,p.Clock).CraftSeasonEquipmentAsync(p.Player,"same",request,Ct));
        await Assert.ThrowsAsync<IdempotencyConflictException>(()=>p.Progression.CraftSeasonEquipmentAsync(p.Player,"same",request with {WishedEffect="Bulwark"},Ct));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE source_kind='MarkCraft'"));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM season_equipment_actions WHERE action_kind='equipment.craft'"));
        Assert.Equal(77L,await db.ScalarAsync<long>("SELECT challenge_marks FROM player_season_wallets WHERE player_id=$1",p.Player));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task SwitchingWishesRetainsEachGroupAndTheThirdSameGroupAttemptGuaranteesItsEffect()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db,_=>0);
        await CraftingTestInputs.FundAsync(db,p,16,0);
        var failures=new List<int>();var effects=new List<string?>();
        foreach(var wish in new[]{"Vitality","Bulwark","Vitality","Vitality"})
        {
            var wallet=(await p.Progression.GetSeasonCraftingAsync(p.Player,Ct)).Wallet!;
            var result=await p.Progression.CraftSeasonEquipmentAsync(p.Player,"wish-"+effects.Count,new(p.Season.SeasonId,"Purple","Head","Fire",wish,wallet.Version),Ct);
            failures.Add(result.Wish.Failures);effects.Add(result.Equipment.EffectAffix);
        }
        Assert.Equal(SwitchedWishFailures,failures);Assert.Equal("Vitality",effects[3]);
        Assert.Equal(1,Assert.Single((await p.Progression.GetSeasonCraftingAsync(p.Player,Ct)).Wishes,row=>row.WishedEffect=="Bulwark").Failures);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task LowTierCannotFundOrangeAndLockedQualityAndStaleWalletDoNotAdvancePity()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db);
        var wallet=await CraftingTestInputs.FundAsync(db,p,100,13);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Progression.CraftSeasonEquipmentAsync(p.Player,"orange",new(p.Season.SeasonId,"Orange","Head","Fire","Piercing",wallet.Version),Ct));
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_state SET highest_unlocked_difficulty=0 WHERE player_id=$1",p.Player);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Progression.CraftSeasonEquipmentAsync(p.Player,"locked",new(p.Season.SeasonId,"Purple","Head","Fire","Piercing",wallet.Version),Ct));
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1",p.Player);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Progression.CraftSeasonEquipmentAsync(p.Player,"stale",new(p.Season.SeasonId,"Purple","Head","Fire","Piercing",wallet.Version-1),Ct));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM player_crafting_wishes"));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE source_kind='MarkCraft'"));
    }
}
