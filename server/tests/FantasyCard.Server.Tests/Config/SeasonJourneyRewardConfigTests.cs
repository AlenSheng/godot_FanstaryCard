using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.ConfigExporter;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Server.Tests.Config;

public sealed class SeasonJourneyRewardConfigTests
{
    [Fact]
    public void ExactCompiledOriginalGroupHasThirtyApprovedRewardsAndSeparateEconomicBudget()
    {
        var tables=JourneyRewardTestInputs.Tables();var bytes=ConfigCompiler.Compile("journey-rewards-roundtrip",tables,out var hash);
        Assert.Equal(bytes,ConfigCompiler.Compile("journey-rewards-roundtrip",tables,out var again));Assert.Equal(hash,again);
        var config=GameConfigCatalog.Load(bytes);var policy=Assert.IsType<SeasonJourneyRewardsConfig>(config.SeasonJourneyRewards);
        Assert.Equal(hash,config.ContentHash);Assert.Equal(new(80,24,8,4,12),policy.Budget());
        Assert.Equal(30,policy.Rewards.Count);Assert.Equal(10,policy.Cosmetics.Count);
        Assert.Equal(3,policy.Cosmetics.Count(c=>c.Kind=="AvatarFrame"));Assert.Equal(2,policy.Cosmetics.Count(c=>c.Kind=="CardBack"));
        Assert.Equal(2,policy.Cosmetics.Count(c=>c.Kind=="Collection"));Assert.Equal(3,policy.Cosmetics.Count(c=>c.Kind=="Title"));
        Assert.All(policy.Rewards.Where(r=>r.Level>20),r=>{Assert.Equal("Cosmetic",r.Kind);Assert.Equal("PermanentBound",r.Ownership);Assert.NotNull(r.CosmeticId);});
        var journey=Assert.IsType<SeasonJourneyConfig>(config.SeasonJourney);
        foreach(var days in new[]{30,42,60})Assert.Equal(30,journey.Progress(journey.Threshold(30,days),days).Level);
        Assert.Equal(20,policy.Rewards.Count(r=>r.Level<=20));Assert.Equal(80,policy.Rewards.Where(r=>r.Ownership=="SeasonalBound").Sum(r=>r.Amount));
    }

    [Fact]
    public void OriginalWithoutRewardTablesNeverCreatesRewardsEvenAtMaximumExperience()
    {
        var tables=JourneyRewardTestInputs.Tables().Where(t=>t.Name is not ("SeasonJourneyRewards" or "SeasonCosmetics")).ToArray();
        var original=GameConfigCatalog.Load(ConfigCompiler.Compile("journey-without-rewards-original",tables,out _));
        Assert.Null(original.SeasonJourneyRewards);Assert.Equal(30,original.SeasonJourney!.Progress(12525,42).Level);
        var rewards=JourneyRewardTestInputs.Catalog().SeasonJourneyRewards!;
        Assert.Throws<DomainValidationException>(()=>rewards.Draw(5,null,original,_=>throw new InvalidOperationException("No roll is allowed.")));
    }

    [Theory]
    [InlineData("SeasonJourneyRewards",0,"amount",11L)]
    [InlineData("SeasonJourneyRewards",0,"ownership","PermanentBound")]
    [InlineData("SeasonJourneyRewards",1,"kind","Gold")]
    [InlineData("SeasonJourneyRewards",2,"requires_class_choice",false)]
    [InlineData("SeasonJourneyRewards",4,"amount",3L)]
    [InlineData("SeasonJourneyRewards",19,"cosmetic_id","trail-seeker")]
    [InlineData("SeasonJourneyRewards",20,"cosmetic_id","veil-warden")]
    [InlineData("SeasonJourneyRewards",29,"level",31L)]
    [InlineData("SeasonJourneyRewards",1,"level",1L)]
    [InlineData("SeasonCosmetics",0,"kind","DamageBonus")]
    [InlineData("SeasonCosmetics",0,"name_key","untranslated")]
    [InlineData("SeasonCosmetics",0,"description_key","")]
    [InlineData("SeasonJourneyRules",0,"enabled",false)]
    [InlineData("SeasonShopRules",0,"enabled",false)]
    public void InflatedRewardsOwnershipChoicesCosmeticsOrDisabledDependenciesCannotPublish(string table,int row,string field,object value)
    {
        var changed=JourneyRewardTestInputs.Change(JourneyRewardTestInputs.Tables(),table,row,field,value);
        Assert.Throws<InvalidDataException>(()=>ConfigCompiler.Compile("invalid-journey-rewards",changed,out _));
    }

    [Theory]
    [InlineData("SeasonJourneyRewards")][InlineData("SeasonCosmetics")][InlineData("SeasonJourneyRules")]
    [InlineData("SeasonWeeklyContracts")][InlineData("SeasonShopRules")][InlineData("SeasonShopProducts")]
    public void PartialRewardOrDependencyGroupCannotPublish(string missing)
    {
        var tables=JourneyRewardTestInputs.Tables().Where(t=>t.Name!=missing).ToArray();
        Assert.Throws<InvalidDataException>(()=>ConfigCompiler.Compile("partial-journey-rewards",tables,out _));
    }

    [Fact]
    public void OrphanRewardGroupCannotSkipAllSeasonalValidation()
    {
        var tables=JourneyRewardTestInputs.Tables().Where(t=>!t.Name.StartsWith("Season",StringComparison.Ordinal)||t.Name is "SeasonJourneyRewards" or "SeasonCosmetics").ToArray();
        Assert.Throws<InvalidDataException>(()=>ConfigCompiler.Compile("orphan-journey-rewards",tables,out _));
    }

    [Theory]
    [InlineData("SeasonJourneyRewards","amount",true,PublishScope.Server)]
    [InlineData("SeasonJourneyRewards","amount",false,PublishScope.Both)]
    [InlineData("SeasonJourneyRewards","cosmetic_id",true,PublishScope.Both)]
    [InlineData("SeasonCosmetics","name_key",true,PublishScope.Client)]
    public void ClientProjectionRequiresCompleteAndCorrectlyTypedRewardMetadata(string name,string field,bool required,PublishScope scope)
    {
        var tables=JourneyRewardTestInputs.Tables();var table=tables.Single(t=>t.Name==name);
        var columns=table.Columns.Select(c=>c.Name==field?c with {Required=required,Scope=scope}:c).ToArray();
        Assert.Throws<InvalidDataException>(()=>ConfigCompiler.Compile("invalid-reward-projection",tables.Select(t=>t==table?t with {Columns=columns}:t).ToArray(),out _));
    }

    [Fact]
    public void PackFreezesThreeRealCopiesIncludingDuplicatesAndSurvivesSerialization()
    {
        var original=JourneyRewardTestInputs.Catalog();var policy=original.SeasonJourneyRewards!;var calls=0;
        var grant=policy.Draw(5,null,original,_=>{calls++;return 0;});
        Assert.Equal(6,calls);Assert.Equal(3,grant.CardIds.Count);Assert.Single(grant.CardIds.Distinct());
        Assert.True(original.Cards.Single(c=>c.CardId==grant.CardIds[0]).InitiallyUnlocked);
        var options=new JsonSerializerOptions(JsonSerializerDefaults.Web){Converters={new JsonStringEnumConverter()}};
        var frozen=JsonSerializer.Deserialize<SeasonJourneyRewardGrant>(JsonSerializer.Serialize(grant,options),options)!;
        policy.ValidateGrant(frozen,original);Assert.Equal(grant.CardIds,frozen.CardIds);
        foreach(var level in new[]{5,10,15,20})Assert.Equal(3,policy.Draw(level,null,original,_=>0).CardIds.Count);
    }

    [Theory]
    [InlineData(HeroClass.Priest)][InlineData(HeroClass.Mage)][InlineData(HeroClass.Guardian)]
    public void ClassSoulGivesExactlyOneChosenPermanentClassWithoutDrawing(HeroClass choice)
    {
        var original=JourneyRewardTestInputs.Catalog();var policy=original.SeasonJourneyRewards!;
        var grant=policy.Draw(3,choice,original,_=>throw new InvalidOperationException("No random roll is allowed."));
        Assert.Equal(choice,grant.HeroClass);Assert.Equal(2,grant.Amount);Assert.Equal("PermanentBound",grant.Ownership);Assert.Empty(grant.CardIds);
    }

    [Theory]
    [InlineData(3,null)][InlineData(3,(HeroClass)99)][InlineData(1,HeroClass.Mage)][InlineData(5,HeroClass.Priest)][InlineData(30,HeroClass.Guardian)]
    public void MissingInvalidOrExtraneousClassChoicesAreRejected(int level,HeroClass? choice)
    {
        var original=JourneyRewardTestInputs.Catalog();
        Assert.Throws<DomainValidationException>(()=>original.SeasonJourneyRewards!.Draw(level,choice,original,_=>0));
    }

    [Fact]
    public void FrozenGrantCannotChangeAmountCopiesCosmeticOrOriginalCatalog()
    {
        var original=JourneyRewardTestInputs.Catalog();var policy=original.SeasonJourneyRewards!;var pack=policy.Draw(5,null,original,_=>0);
        foreach(var changed in new[]{pack with {Amount=2},pack with {CardIds=pack.CardIds.Take(2).ToArray()},
                    pack with {CardIds=[..pack.CardIds,"C01"]},pack with {CardIds=["UNKNOWN","C01","C01"]},pack with {CosmeticId="trail-seeker"},
                    pack with {Kind="Gold"},pack with {Ownership="SeasonalBound"},pack with {RewardId="journey-level-10"}})
            Assert.Throws<DomainValidationException>(()=>policy.ValidateGrant(changed,original));
        var cosmetic=policy.Draw(21,null,original,_=>throw new InvalidOperationException());
        Assert.Empty(cosmetic.CardIds);Assert.Equal("AvatarFrame",policy.Cosmetic(cosmetic.CosmeticId!).Kind);
        Assert.Throws<DomainValidationException>(()=>policy.ValidateGrant(cosmetic with {CosmeticId="relicbound-pathfinder"},original));
        var excluded=original.Cards.First(c=>!SeasonShopConfig.PackEligible(c)).CardId;
        Assert.Throws<DomainValidationException>(()=>policy.ValidateGrant(pack with {CardIds=[excluded,excluded,excluded]},original));
        var other=JourneyRewardTestInputs.Catalog("other-original-version");
        Assert.Throws<DomainValidationException>(()=>policy.ValidateGrant(pack,other));
        Assert.Throws<DomainValidationException>(()=>policy.At(0));Assert.Throws<DomainValidationException>(()=>policy.At(31));
    }
}
