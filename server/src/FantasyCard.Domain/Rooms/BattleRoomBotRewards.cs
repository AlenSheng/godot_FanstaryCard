using System.Text.Json.Serialization;
using FantasyCard.Domain.Bots;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Rooms;

public sealed record BotVictoryRewardReceipt(Guid BotId,int Gold,int Fragments,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] ExplorationItem? Equipment,
    bool GoldRetained,bool FragmentsRetained,bool EquipmentRetained);

public sealed partial class BattleRoom
{
    private readonly CombatRandom _botRewardRandom;
    public SeasonBotRewardConfig? BotRewardPolicy => Season is not null && _catalog.UsesPublishedConfiguration
        ? _catalog.Configuration.SeasonBotRewards : null;

    private IReadOnlyList<ExplorationItem>? InitialBotArmor(BattleRoomPlayerSetup setup,bool restoring)
    {
        if(!setup.IsBot || BotRewardPolicy is null || restoring)return setup.WornArmor;
        return (setup.WornArmor??[]).Select(item=>item with
        {
            IsCombatProjection=true,IsGenerated=true,
            Equipment=item.Equipment is { } gear ? gear with
            {
                StatsVersion=Season!.StatsVersion,
                SeasonOrigin=new(Season,"BotProjection",BotRewardPolicy.RuleId,"projection",gear.Quality,false)
            }:throw new DomainValidationException("Bot combat projection requires complete equipment attributes.")
        }).ToArray();
    }

    private void AwardBotVictory(RoomPlayerState winner,RoomPlayerState loser)
    {
        if(BotRewardPolicy is not { } policy || winner.IsBot || !loser.IsBot || winner.BotVictoryReward is not null)return;
        ExplorationItem? equipment=null;
        if(_botRewardRandom.Next(10000)<policy.EquipmentChanceBasisPoints)
            equipment=new(policy.EquipmentId(RoomId,winner.PlayerId).ToString("D"),ExplorationItemKind.Equipment,
                Equipment:policy.CreateEquipment(Season!,winner.PlayerId,loser.PlayerId,_botRewardRandom),IsGenerated:true);
        // Match the normal base-drop overflow rule: an unavailable new stack is
        // recycled. The once-only receipt is still retained, so a full bag cannot reroll.
        var gold=policy.Gold==0 || winner.Inventory.TryAdd(new("gold",ExplorationItemKind.Gold,policy.Gold));
        var fragments=policy.Fragments==0 || winner.Inventory.TryAdd(new("equipment_fragments",ExplorationItemKind.EquipmentFragments,policy.Fragments));
        var kept=equipment is null || winner.Inventory.TryAdd(equipment);
        if(!kept)TrackRecycled(winner,equipment!);
        winner.BotVictoryReward=new(loser.PlayerId,policy.Gold,policy.Fragments,equipment,gold,fragments,kept);
        ObserveRoomEvent(winner,"loot_generated","BotVictory",gold?"CarriedPendingSettlement":"OverflowRecycled",[new("gold",ExplorationItemKind.Gold,policy.Gold)]);
        ObserveRoomEvent(winner,"loot_generated","BotVictory",fragments?"CarriedPendingSettlement":"OverflowRecycled",[new("equipment_fragments",ExplorationItemKind.EquipmentFragments,policy.Fragments)]);
        if(equipment is not null)ObserveRoomEvent(winner,"loot_generated","BotVictory",kept?"CarriedPendingSettlement":"OverflowRecycled",[equipment]);
    }

    private void ValidateBotRewardState(RoomRandomStreamsSnapshot? streams)
    {
        var all=_players.Values.SelectMany(player=>player.Inventory.Items.Concat(player.WornArmor)
            .Concat(player.RecycledEquipment).Concat(player.BotLoot)).Concat(_relicPiles.Values.SelectMany(pile=>pile.Items)).ToArray();
        if(BotRewardPolicy is not { } policy)
        {
            if(streams?.BotReward is not null || _players.Values.Any(player=>player.BotVictoryReward is not null) || all.Any(item=>item.IsCombatProjection))
                throw new DomainValidationException("Saved bot reward policy is absent from this frozen configuration.");
            return;
        }
        if(streams?.BotReward is not { } state)throw new DomainValidationException("Saved bot reward random stream is missing.");
        _botRewardRandom.Restore(state);
        var issued=new Dictionary<string,EquipmentRewardData>(StringComparer.Ordinal);
        foreach(var player in _players.Values)
        {
            if(player.IsBot && (player.BotLoot.Count!=0 || player.RewardChoice is not null || player.BotVictoryReward is not null))
                throw new DomainValidationException("Bot projections cannot retain normal reward choices or mint budgets.");
            var projections=player.Inventory.Items.Where(item=>item.IsCombatProjection).ToArray();
            if(projections.Length>BotRules.StartingPotions || projections.Any(item=>!player.IsBot || item.Kind!=ExplorationItemKind.HealthPotion || item.Quantity!=1 || item.Equipment is not null))
                throw new DomainValidationException("Bot projected consumables differ from their starting budget.");
            foreach(var item in player.WornArmor.Where(item=>item.IsCombatProjection))
            {
                if(!player.IsBot || item.IsGenerated!=true || item.Equipment is not { } gear ||
                    gear.SeasonOrigin is not {Source:"BotProjection",Promoted:false} origin || origin.Season!=Season ||
                    origin.LootRuleId!=policy.RuleId || origin.LayerId!="projection" || origin.BaseQuality!=gear.Quality ||
                    gear.StatsVersion!=Season!.StatsVersion || !EquipmentRewardRules.IsValid(gear))
                    throw new DomainValidationException("Bot combat projection differs from its frozen room policy.");
            }
            if(player.RecycledEquipment.Concat(player.BotLoot).Any(item=>item.IsCombatProjection))
                throw new DomainValidationException("Combat projections cannot be recycled as assets.");
            if(player.BotVictoryReward is not { } receipt)continue;
            if(player.IsBot || !_players.TryGetValue(receipt.BotId,out var bot) || !bot.IsBot || bot.Phase!=RoomPlayerPhase.Dead ||
                receipt.Gold!=policy.Gold || receipt.Fragments!=policy.Fragments)
                throw new DomainValidationException("Bot victory receipt has no matching human/bot outcome.");
            if(receipt.Equipment is { } issuedItem)
            {
                if(issuedItem.IsCombatProjection || issuedItem.IsGenerated!=true || issuedItem.Kind!=ExplorationItemKind.Equipment || issuedItem.Quantity!=1 ||
                    issuedItem.ItemId!=policy.EquipmentId(RoomId,player.PlayerId).ToString("D") || issuedItem.Equipment is not { } issuedGear ||
                    issuedGear.SeasonOrigin?.BotRewardOwnerId!=player.PlayerId || issuedGear.SeasonOrigin.DefeatedBotId!=receipt.BotId)
                    throw new DomainValidationException("Bot victory receipt equipment identity is invalid.");
                policy.RequireOrigin(issuedGear,Season!);issued.Add(issuedItem.ItemId,issuedGear);
            }
        }
        if(_relicPiles.Values.Any(pile=>pile.Items.Any(item=>item.IsCombatProjection)))
            throw new DomainValidationException("A relic pile cannot contain combat projections.");
        foreach(var group in all.Where(item=>item.IsGenerated==true && item.Equipment?.SeasonOrigin?.Source=="BotVictory").GroupBy(item=>item.ItemId))
            if(group.Count()!=1 || !issued.TryGetValue(group.Key,out var gear) || group.Single().Equipment!=gear)
                throw new DomainValidationException("Bot victory asset has no unique issued receipt.");
    }
}
