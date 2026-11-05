using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Configuration;

public sealed record SeasonJourneyRewardConfig(string RewardId,int Level,string Kind,int Amount,string Ownership,
    bool RequiresClassChoice,string? CosmeticId);
public sealed record SeasonCosmeticConfig(string CosmeticId,string Kind,string NameKey,string DescriptionKey);
public sealed record SeasonJourneyRewardGrant(string RewardId,int Level,string Kind,int Amount,string Ownership,
    HeroClass? HeroClass,IReadOnlyList<string> CardIds,string? CosmeticId);
public sealed record SeasonJourneyRewardBudget(int EquipmentFragments,int WarriorSoul,int ClassSoul,int CardPacks,int CardCopies);

/// <summary>Only a published original-season reward group creates claimable rewards.</summary>
public sealed record SeasonJourneyRewardsConfig(IReadOnlyList<SeasonJourneyRewardConfig> Rewards,
    IReadOnlyList<SeasonCosmeticConfig> Cosmetics)
{
    private static readonly string[] PackQualities=["White","Green","Blue","Purple"];
    private static readonly (string Id,string Kind)[] CollectionRewards=
    [
        ("trail-seeker","AvatarFrame"),("relic-seeker","Title"),("first-threshold","Collection"),
        ("waymark-seal","CardBack"),("veil-warden","Title"),("veilbound-seal","AvatarFrame"),
        ("fivefold-chronicle","Collection"),("convergent-sigil","CardBack"),("veil-cartographer","Title"),
        ("relicbound-pathfinder","AvatarFrame")
    ];

    public void Validate(SeasonJourneyConfig? journey,SeasonShopConfig? shop,IReadOnlyList<CardConfigDefinition> cards)
    {
        if(journey is null||shop is null)
            throw new InvalidDataException("Journey rewards require their original experience and card-pack policies.");
        journey.Validate();
        if(shop.PackCards!=3||(shop.WhiteWeight,shop.GreenWeight,shop.BlueWeight,shop.PurpleWeight)!=(50,30,15,5)||
            PackQualities.Any(quality=>!cards.Any(c=>c.Quality==quality&&SeasonShopConfig.PackEligible(c))))
            throw new InvalidDataException("Journey card packs require the complete original three-copy quality pools.");
        if(Rewards.Count!=30||!Rewards.Select(r=>r.Level).Order().SequenceEqual(Enumerable.Range(1,30))||
            Rewards.Select(r=>r.RewardId).Distinct(StringComparer.Ordinal).Count()!=30||
            Cosmetics.Count!=10||Cosmetics.Select(c=>c.CosmeticId).Distinct(StringComparer.Ordinal).Count()!=10)
            throw new InvalidDataException("Journey rewards require exactly thirty levels and ten unique cosmetics.");
        foreach(var reward in Rewards)
        {
            var (kind,amount)=reward.Level<=20?((reward.Level%5) switch
            {
                1 or 4=>("EquipmentFragments",10),2=>("WarriorSoul",6),3=>("ClassSoul",2),_=>("CardPack",1)
            }):("Cosmetic",1);
            var cosmetic=reward.Level<=20?null:CollectionRewards[reward.Level-21].Id;
            if(reward.RewardId!=$"journey-level-{reward.Level:D2}"||reward.Kind!=kind||reward.Amount!=amount||
                reward.Ownership!=(kind=="EquipmentFragments"?"SeasonalBound":"PermanentBound")||
                reward.RequiresClassChoice!=(kind=="ClassSoul")||reward.CosmeticId!=cosmetic)
                throw new InvalidDataException("Journey rewards differ from the approved level, amount, choice or ownership.");
        }
        foreach(var (id,kind) in CollectionRewards)
        {
            var cosmetic=Cosmetics.SingleOrDefault(c=>c.CosmeticId==id);
            if(cosmetic is null||cosmetic.Kind!=kind||cosmetic.NameKey!=$"journey_cosmetic_{id.Replace('-','_')}_name"||
                cosmetic.DescriptionKey!=$"journey_cosmetic_{id.Replace('-','_')}_description")
                throw new InvalidDataException("Journey cosmetics differ from their approved identity, display slot or localized keys.");
        }
    }

    public SeasonJourneyRewardConfig At(int level)=>Rewards.SingleOrDefault(r=>r.Level==level)
        ??throw new DomainValidationException("This journey level has no original published reward.");

    public SeasonCosmeticConfig Cosmetic(string id)=>Cosmetics.SingleOrDefault(c=>c.CosmeticId==id)
        ??throw new DomainValidationException("This cosmetic is not in the original published journey.");

    public SeasonJourneyRewardBudget Budget()=>new(Rewards.Where(r=>r.Kind=="EquipmentFragments").Sum(r=>r.Amount),
        Rewards.Where(r=>r.Kind=="WarriorSoul").Sum(r=>r.Amount),Rewards.Where(r=>r.Kind=="ClassSoul").Sum(r=>r.Amount),
        Rewards.Where(r=>r.Kind=="CardPack").Sum(r=>r.Amount),checked(3*Rewards.Where(r=>r.Kind=="CardPack").Sum(r=>r.Amount)));

    /// <summary>The caller persists this result atomically with the asset grant; retries reuse it.</summary>
    public SeasonJourneyRewardGrant Draw(int level,HeroClass? choice,GameConfigCatalog original,Func<int,int> random)
    {
        if(!ReferenceEquals(original.SeasonJourneyRewards,this))
            throw new DomainValidationException("Journey grants require the exact original published reward policy.");
        var reward=At(level);RequireChoice(reward,choice);
        var cards=reward.Kind=="CardPack"?Enumerable.Range(0,original.SeasonShop?.PackCards
            ??throw new DomainValidationException("The original card-pack policy is unavailable."))
            .Select(_=>original.SeasonShop!.Draw(original.Cards,random).CardId).ToArray():[];
        var grant=new SeasonJourneyRewardGrant(reward.RewardId,level,reward.Kind,reward.Amount,reward.Ownership,choice,cards,reward.CosmeticId);
        ValidateGrant(grant,original);return grant;
    }

    public void ValidateGrant(SeasonJourneyRewardGrant grant,GameConfigCatalog original)
    {
        if(!ReferenceEquals(original.SeasonJourneyRewards,this))
            throw new DomainValidationException("Journey grants require the exact original published reward policy.");
        var reward=At(grant.Level);RequireChoice(reward,grant.HeroClass);
        if(grant.RewardId!=reward.RewardId||grant.Kind!=reward.Kind||grant.Amount!=reward.Amount||
            grant.Ownership!=reward.Ownership||grant.CosmeticId!=reward.CosmeticId||
            grant.CardIds.Count!=(reward.Kind=="CardPack"?3:0)||
            grant.CardIds.Any(id=>!original.Cards.Any(c=>c.CardId==id&&SeasonShopConfig.PackEligible(c))))
            throw new DomainValidationException("The frozen journey grant differs from its original reward.");
    }

    private static void RequireChoice(SeasonJourneyRewardConfig reward,HeroClass? choice)
    {
        if(reward.RequiresClassChoice?(choice is null||!Enum.IsDefined(choice.Value)):choice is not null)
            throw new DomainValidationException("Only a class-soul reward requires exactly one valid class choice.");
    }
}
