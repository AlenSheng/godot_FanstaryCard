using System.Security.Cryptography;
using System.Text;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Rooms;

public sealed record RedDropEvaluation(Guid AttemptId,MapPosition Position,string Source,int Roll,int EquipmentSeed,DateTimeOffset OccurredAt);
public sealed record RedDropReceipt(Guid AttemptId,string Status,ExplorationItem? Equipment);

public sealed partial class BattleRoom
{
    private readonly CombatRandom _redRandom;
    internal bool RedStateNeedsPersistence { get; private set; }
    public SeasonRedConfig? RedPolicy => Season is not null && _catalog.UsesPublishedConfiguration?_catalog.Configuration.SeasonRed:null;
    public bool HasRedWork => RedStateNeedsPersistence || _players.Values.Any(player=>player.PendingRedEvaluation is not null);
    public void MarkRedStatePersisted() => RedStateNeedsPersistence=false;

    private void QueueBossRed(RoomPlayerState player,ChaosMapCell cell,bool alreadyCleared,DateTimeOffset now)
    {
        if(RedPolicy is not { } policy || player.IsBot || alreadyCleared || player.RedReward is not null ||
            player.PendingRedEvaluation is not null || Season!.Difficulty<policy.MinimumDifficulty ||
            !cell.IsBoss || cell.Layer!=ChaosMapLayer.Core)return;
        var id=RedAttemptId(player.PlayerId,cell.Position);
        player.PendingRedEvaluation=new(id,cell.Position,"ChaosBoss",_redRandom.Next(10000),_redRandom.Next(),now.ToUniversalTime());
        RedStateNeedsPersistence=true;
    }

    private Guid RedAttemptId(Guid playerId,MapPosition position) =>
        new(SHA256.HashData(Encoding.UTF8.GetBytes($"red-boss:{RoomId:D}:{playerId:D}:{position.Row}:{position.Column}")).AsSpan(0,16));

    public void ApplyRedDrop(Guid playerId,RedDropReceipt result)
    {
        if(RedPolicy is null)throw new DomainValidationException("The room has no red drop policy.");
        var player=GetPlayer(playerId);
        if(player.RedReward is { } prior && prior.AttemptId==result.AttemptId)
        {
            if(prior!=result)throw new DomainValidationException("Red drop replay differs from its original receipt.");
            return;
        }
        if(player.PendingRedEvaluation?.AttemptId!=result.AttemptId || result.Status is not ("Miss" or "Exhausted" or "Closed" or "Minted") ||
            (result.Status=="Minted")!=(result.Equipment is not null))
            throw new DomainValidationException("Red drop resolution has no matching pending event.");
        if(result.Equipment is { } item)
        {
            if(player.Phase==RoomPlayerPhase.Extracted)throw new DomainValidationException("An extracted player cannot receive a new red mint.");
            if(item.Kind!=ExplorationItemKind.Equipment || item.Quantity!=1 || item.IsGenerated!=false || item.IsCombatProjection || item.Equipment is not {Quality:"Red",Level:0,UniqueAffix:not null} gear ||
                !EquipmentRewardRules.IsValid(gear) || gear.StatsVersion!=Season!.StatsVersion || !Guid.TryParse(item.ItemId,out _))
                throw new DomainValidationException("Red delivery must be one already minted real item.");
            if(player.Phase==RoomPlayerPhase.Dead)
            {
                var pile=_relicPiles.Values.SingleOrDefault(value=>value.VictimId==playerId.ToString("D"));
                if(pile is null && player.Position is { } position)
                {
                    pile=new(Guid.NewGuid(),playerId.ToString("D"),position,player.DisplayName);_relicPiles.Add(pile.PileId,pile);
                }
                if(pile is null)throw new DomainValidationException("A dead red recipient requires its original map position.");
                pile.Add(item);
            }
            else if(!player.Inventory.TryAdd(item))player.PendingRedItem=item;
        }
        player.RedReward=result;player.PendingRedEvaluation=null;RedStateNeedsPersistence=true;Revision++;
        if(result.Equipment is { } delivered)
        {
            ObserveRoomEvent(player,"loot_generated","IndependentRed","AlreadyMintedDelivery",[delivered]);
            if(player.Phase==RoomPlayerPhase.Dead)ObserveRoomEvent(player,"loot_lost","IndependentRed","RelicCustodyPendingSettlement",[delivered]);
        }
    }

    public long ClaimPendingRed(Guid playerId,string? replaceItemId=null)
    {
        var player=GetPlayer(playerId);
        if(player.Phase!=RoomPlayerPhase.Choice || player.PendingRedEvaluation is not null || player.PendingRedItem is not { } item)
            throw new DomainValidationException("There is no available pending red item.");
        var staged=player.Inventory.Clone();ExplorationItem? replaced=null;
        if(replaceItemId is not null && !staged.TryRemove(replaceItemId,out replaced))
            throw new DomainValidationException("The explicit red replacement item is not available.");
        if(!staged.TryAdd(item with {SlotIndex=replaced?.SlotIndex??-1,IsSafe=false}))
            throw new DomainValidationException("Choose an inventory item to replace before taking the pending red.");
        player.Inventory.Apply(staged);if(replaced is not null)TrackRecycled(player,replaced);
        player.PendingRedItem=null;RedStateNeedsPersistence=true;
        ObserveRoomEvent(player,"loot_chosen","IndependentRed","CarriedPendingSettlement",[item],1);
        return ++Revision;
    }

    private static void RequireRedChoiceResolved(RoomPlayerState player)
    {
        if(player.PendingRedEvaluation is not null || player.PendingRedItem is not null)
            throw new DomainValidationException("Resolve the independent red drop before continuing normal rewards.");
    }

    private void ValidateRedState(RoomRandomStreamsSnapshot? streams)
    {
        if(RedPolicy is null)
        {
            if(streams?.Red is not null || _players.Values.Any(player=>player.PendingRedEvaluation is not null || player.PendingRedItem is not null || player.RedReward is not null))
                throw new DomainValidationException("Red delivery state is not enabled by the frozen configuration.");
            return;
        }
        if(streams?.Red is not { } state)throw new DomainValidationException("Red random stream is missing.");
        _redRandom.Restore(state);
        foreach(var player in _players.Values)
        {
            if(player.IsBot && (player.PendingRedEvaluation is not null || player.RedReward is not null || player.PendingRedItem is not null))
                throw new DomainValidationException("Bots cannot own an independent red generation event.");
            if(player.PendingRedEvaluation is { } pending && (pending.Roll is <0 or >=10000 || pending.EquipmentSeed<0 || pending.Source!="ChaosBoss" ||
                pending.AttemptId!=RedAttemptId(player.PlayerId,pending.Position) || pending.OccurredAt.Offset!=TimeSpan.Zero ||
                Map?.GetCell(pending.Position) is not {IsBoss:true,Layer:ChaosMapLayer.Core} || !player.ClearedCells.Contains(pending.Position) ||
                Season!.Difficulty<RedPolicy.MinimumDifficulty || player.RedReward is not null))
                throw new DomainValidationException("Pending red event differs from its original Boss source.");
            if(player.RedReward is { } reward && (reward.Status is not ("Miss" or "Exhausted" or "Closed" or "Minted") ||
                (reward.Status=="Minted")!=(reward.Equipment is not null) ||
                Map?.Capture().Cells.Any(cell=>cell.IsBoss && cell.Layer==ChaosMapLayer.Core && RedAttemptId(player.PlayerId,cell.Position)==reward.AttemptId)!=true ||
                reward.Equipment is { } red && (red.Kind!=ExplorationItemKind.Equipment || red.Quantity!=1 || red.IsGenerated!=false || red.IsCombatProjection || !Guid.TryParse(red.ItemId,out _) ||
                    red.Equipment is not {Quality:"Red",Level:0,UniqueAffix:not null} gear || !EquipmentRewardRules.IsValid(gear) || gear.StatsVersion!=Season!.StatsVersion)))
                throw new DomainValidationException("Red receipt differs from its original Boss delivery contract.");
            if(player.PendingRedItem is { } item && (player.RedReward is not {Status:"Minted"} receipt || receipt.Equipment!=item || item.IsGenerated!=false))
                throw new DomainValidationException("Pending red selection differs from the original minted item.");
        }
    }
}
