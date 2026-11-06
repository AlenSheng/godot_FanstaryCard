using System.Security.Cryptography;
using System.Text;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Configuration;

/// <summary>A small, unscaled victory award independent of a bot's projected combat gear.</summary>
public sealed record SeasonBotRewardConfig(string RuleId, int Gold, int Fragments, int EquipmentChanceBasisPoints,
    string EquipmentQuality, int EquipmentLevel, int MaximumPerHuman, bool MortalPve)
{
    private static readonly string[] Slots=["Head","Chest","Hands","Legs","Feet"];

    public void Validate()
    {
        if(RuleId!="season-bot-reward-v1" || Gold is <0 or >5 || Fragments is <0 or >1 ||
            EquipmentChanceBasisPoints is <0 or >1000 || EquipmentQuality is not ("White" or "Green" or "Blue") ||
            EquipmentLevel!=0 || MaximumPerHuman!=1 || !MortalPve)
            throw new InvalidDataException("Invalid season bot reward/projection budget.");
    }

    public Guid EquipmentId(Guid roomId,Guid humanId) =>
        new(SHA256.HashData(Encoding.UTF8.GetBytes($"{RuleId}:{roomId:D}:{humanId:D}")).AsSpan(0,16));

    public EquipmentRewardData CreateEquipment(SeasonContext season,Guid humanId,Guid botId,Random random) =>
        new(Slots[random.Next(Slots.Length)],
            EquipmentQuality,SeasonLootPreferenceConfig.Elements[random.Next(5)],null,"DrawInterval",EquipmentLevel,
            SeasonOrigin:new(season,"BotVictory",RuleId,"bot",EquipmentQuality,false,humanId,botId),StatsVersion:season.StatsVersion);

    public void RequireOrigin(EquipmentRewardData item,SeasonContext season)
    {
        if(item.SeasonOrigin is not {Source:"BotVictory",Promoted:false} origin || origin.Season!=season ||
            origin.LootRuleId!=RuleId || origin.LayerId!="bot" || origin.BaseQuality!=EquipmentQuality ||
            origin.BotRewardOwnerId is null || origin.BotRewardOwnerId==Guid.Empty || origin.DefeatedBotId is null ||
            origin.DefeatedBotId==Guid.Empty || origin.BotRewardOwnerId==origin.DefeatedBotId ||
            item.Quality!=EquipmentQuality || item.Level!=0 || item.EffectAffix is not null || item.IsBound ||
            item.UniqueAffix is not null || item.UniqueElement is not null || item.SecondaryTrait!="DrawInterval" ||
            item.StatsVersion!=season.StatsVersion || !EquipmentRewardRules.IsValid(item))
            throw new DomainValidationException("Generated bot victory equipment differs from its separate reward budget.");
    }
}
