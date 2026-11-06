using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Rooms;

public sealed record RoomLootObservation(string ItemId,string Kind,int Quantity,string? Quality,bool? Generated,bool Safe,bool CombatProjection);
public sealed record RoomEventObservation(long Sequence,Guid PlayerId,HeroClass HeroClass,bool IsBot,string EventName,string Source,
    string Result,TimeSpan RoomElapsed,DateTimeOffset? OccurredAtUtc,Guid? BattleId,MapPosition? Position,string CellType,
    IReadOnlyList<RoomLootObservation> Items,int OmittedItems,int Hp,int EffectiveMaximumHp,int? AppliedQuantity=null,
    string? OptionId=null,int? HealPercent=null,int? HpBefore=null);
public sealed record RoomObservationOwner(Guid PlayerId,HeroClass HeroClass,bool IsBot);
public sealed record RoomObservationSnapshot(int SchemaVersion,long LastSequence,long DroppedEvents,IReadOnlyList<RoomEventObservation> Events)
{
    public void RequireValid(IReadOnlyList<RoomObservationOwner> owners,TimeSpan elapsed,DateTimeOffset? started)
        =>RoomObservationJournal.Restore(this,owners,elapsed,started);
}

/// <summary>Bounded cumulative observations survive coalesced checkpoints; never consume gameplay RNG.</summary>
internal sealed class RoomObservationJournal
{
    internal const int MaximumEvents=4096;
    internal const int MaximumItemsPerEvent=128;
    private readonly List<RoomEventObservation> _events=[];
    private long _lastSequence;
    internal bool HasFinished(Guid player,Guid battle)=>_events.Any(e=>e.PlayerId==player&&e.BattleId==battle&&e.EventName=="battle_finished");

    internal void Append(RoomPlayerState player,string name,string source,string result,TimeSpan elapsed,DateTimeOffset? started,
        Guid? battleId,string cell,IEnumerable<ExplorationItem>? items=null,int? applied=null,string? optionId=null,int? healPercent=null,int? hpBefore=null)
    {
        if(_lastSequence<long.MaxValue)_lastSequence++;
        if(_events.Count>=MaximumEvents)return;
        var all=(items??[]).ToArray();var kept=all.Take(MaximumItemsPerEvent).Select(item=>new RoomLootObservation(item.ItemId,item.Kind.ToString(),item.Quantity,
            item.Equipment?.Quality,item.IsGenerated,item.IsSafe,item.IsCombatProjection)).ToArray();
        DateTimeOffset? at=started is { } start&&elapsed>=TimeSpan.Zero&&elapsed.Ticks<=DateTimeOffset.MaxValue.UtcTicks-start.UtcTicks
            ?new DateTimeOffset(start.UtcTicks+elapsed.Ticks,TimeSpan.Zero):null;
        _events.Add(new(_lastSequence,player.PlayerId,player.HeroClass,player.IsBot,name,source,result,elapsed,at,battleId,player.Position,cell,kept,all.Length-kept.Length,
            player.Combat.Hp,player.Combat.EffectiveMaximumHp,applied,optionId,healPercent,hpBefore));
    }

    internal RoomObservationSnapshot Capture()=>new(1,_lastSequence,_lastSequence-_events.Count,_events.ToArray());

    internal static RoomObservationJournal Restore(RoomObservationSnapshot snapshot,IReadOnlyList<RoomObservationOwner> players,TimeSpan elapsed,DateTimeOffset? started)
    {
        if(snapshot.SchemaVersion!=1||snapshot.Events is null||snapshot.Events.Count>MaximumEvents||snapshot.LastSequence<snapshot.Events.Count||
            snapshot.DroppedEvents!=snapshot.LastSequence-snapshot.Events.Count||snapshot.DroppedEvents<0||
            snapshot.DroppedEvents>0&&snapshot.Events.Count!=MaximumEvents||started is null||
            players.Select(p=>p.PlayerId).Distinct().Count()!=players.Count)
            throw new DomainValidationException("Saved room observations have an invalid version, size or sequence.");
        long prior=0;
        foreach(var row in snapshot.Events)
        {
            var owner=players.SingleOrDefault(p=>p.PlayerId==row.PlayerId);
            if(row.Sequence!=++prior||owner is null||owner.HeroClass!=row.HeroClass||owner.IsBot!=row.IsBot||!Enum.IsDefined(row.HeroClass)||
                row.EventName is not("battle_finished" or "loot_generated" or "loot_chosen" or "loot_extracted" or "loot_lost")||
                string.IsNullOrEmpty(row.Source)||row.Source.Length>80||string.IsNullOrEmpty(row.Result)||row.Result.Length>80||
                string.IsNullOrEmpty(row.CellType)||row.CellType.Length>80||row.OptionId?.Length>160||
                row.RoomElapsed<TimeSpan.Zero||row.RoomElapsed>elapsed||row.Items is null||row.Items.Count>MaximumItemsPerEvent||row.OmittedItems<0||
                row.Items.Any(item=>string.IsNullOrEmpty(item.ItemId)||item.ItemId.Length>160||item.Quantity<0||!Enum.TryParse<ExplorationItemKind>(item.Kind,out _))||
                row.OccurredAtUtc is { } at&&(at.Offset!=TimeSpan.Zero||row.RoomElapsed.Ticks>DateTimeOffset.MaxValue.UtcTicks-started.Value.UtcTicks||at.UtcTicks!=started.Value.UtcTicks+row.RoomElapsed.Ticks))
                throw new DomainValidationException("Saved room observation disagrees with its original room.");
        }
        var journal=new RoomObservationJournal{_lastSequence=snapshot.LastSequence};journal._events.AddRange(snapshot.Events);return journal;
    }
}

public sealed partial class BattleRoom
{
    private RoomObservationJournal? _observations;
    private void ObserveRoomEvent(RoomPlayerState player,string name,string source,string result,IEnumerable<ExplorationItem>? items=null,
        int? applied=null,Guid? battleId=null,TimeSpan? at=null,string? optionId=null,int? healPercent=null,int? hpBefore=null)
    {
        if(_observations is null)return;
        var cell=player.Position is { } position&&Map is not null?Map.GetCell(position):null;
        var kind=cell is null?"Unknown":cell.IsBoss||cell.MonsterGroupId=="BOSS"?"Boss":cell.MonsterGroupId=="BOX"?"Treasure":cell.MonsterGroupId.StartsWith('E')?"Elite":"Normal";
        _observations.Append(player,name,source,result,at??Elapsed,StartedAtUtc,battleId??player.Pve?.BattleId??player.CurrentDuelId,kind,items,applied,optionId,healPercent,hpBefore);
    }

    private void ObserveRewardOptions(RoomPlayerState player,string source)
    {
        if(player.RewardChoice is not { } choice)return;
        // These are potential alternatives, never three minted/credited rewards.
        foreach(var option in choice.Options)
            ObserveRoomEvent(player,"loot_generated",source,"PotentialChoice",option.Item is null?[]:[option.Item],
                optionId:option.OptionId,healPercent:option.HealPercent,hpBefore:player.Combat.Hp);
    }

    private void ObservePveFinished(RoomPlayerState player,string result,TimeSpan? at=null)
    {
        if(player.Pve is not { } pve||_observations?.HasFinished(player.PlayerId,pve.BattleId)==true)return;
        ObserveRoomEvent(player,"battle_finished","Pve",result,battleId:pve.BattleId,at:at);
    }
}
