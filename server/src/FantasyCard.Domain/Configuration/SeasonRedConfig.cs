using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Configuration;

public sealed record SeasonRedConfig(string RuleId,int WeeklyQuota,int MinimumDifficulty,int BossChanceBasisPoints,
    bool ChestEnabled,int ChestChanceBasisPoints,string TimeZone,int WeekStartHour)
{
    private static readonly string[] Slots=["Head","Chest","Hands","Legs","Feet"];
    private static readonly string[] Effects=["Piercing","Bulwark","Vitality"];
    private static readonly string[] Unique=["Inferno","RapidDraw","ChainDraw","Scavenge","GoldenCicada"];

    public void Validate()
    {
        if(RuleId!="weekly-red" || WeeklyQuota!=1 || MinimumDifficulty!=2 || BossChanceBasisPoints!=40 ||
            ChestChanceBasisPoints!=8 || TimeZone!="Asia/Shanghai" || WeekStartHour!=4)
            throw new InvalidDataException("Season red policy differs from the shared weekly source contract.");
    }

    public bool Hits(string source,int difficulty,int roll)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(roll);ArgumentOutOfRangeException.ThrowIfGreaterThanOrEqual(roll,10000);
        if(difficulty<MinimumDifficulty || difficulty>5)return false;
        return source switch {"ChaosBoss"=>roll<BossChanceBasisPoints,"ShopChest"=>ChestEnabled && roll<ChestChanceBasisPoints,
            "Activity"=>false,_=>throw new DomainValidationException("Unknown red drop source.")};
    }

    public static EquipmentRewardData Equipment(int seed,string statsVersion,string? preference,SeasonLootPreferenceConfig? elements)
    {
        var random=new Random(seed);var unique=Unique[random.Next(Unique.Length)];
        var slot=unique=="GoldenCicada"?"Feet":Slots[random.Next(Slots.Length)];
        var element=elements is null?SeasonLootPreferenceConfig.Elements[random.Next(5)]:elements.Roll(elements.Resolve(preference),random.Next(10000));
        return new(slot,"Red",element,Effects[random.Next(Effects.Length)],slot=="Feet" && random.Next(2)==1?"ForcedEscape":"DrawInterval",
            UniqueAffix:unique,UniqueElement:unique=="Inferno"?element:null,StatsVersion:statsVersion);
    }
}
