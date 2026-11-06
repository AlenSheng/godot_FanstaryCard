using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using System.Text.Json.Serialization;

namespace FantasyCard.Domain.Rooms;

public sealed record RoomLootObservation(string ItemId,string Kind,int Quantity,string? Quality,bool? Generated,bool Safe,bool CombatProjection);
public sealed record RoomEventObservation(long Sequence,Guid PlayerId,HeroClass HeroClass,bool IsBot,string EventName,string Source,
    string Result,TimeSpan RoomElapsed,DateTimeOffset? OccurredAtUtc,Guid? BattleId,MapPosition? Position,string CellType,
    IReadOnlyList<RoomLootObservation> Items,int OmittedItems,int Hp,int EffectiveMaximumHp,int? AppliedQuantity=null,
    string? OptionId=null,int? HealPercent=null,int? HpBefore=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] string? BuildProfileId=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] string? BattleBuildProfileId=null);
public sealed record RoomBattleBuildBinding(Guid PlayerId,Guid BattleId,string ProfileId);
public sealed record RoomObservationOwner(Guid PlayerId,HeroClass HeroClass,bool IsBot);
public sealed record RoomObservationSnapshot(int SchemaVersion,long LastSequence,long DroppedEvents,IReadOnlyList<RoomEventObservation> Events,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] IReadOnlyList<RoomBuildProfile>? Profiles=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] IReadOnlyList<RoomBattleBuildBinding>? BattleBuilds=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] RoomCombatObservationSnapshot? Combat=null)
{
    public void RequireValid(IReadOnlyList<RoomObservationOwner> owners,TimeSpan elapsed,DateTimeOffset? started)
        =>RoomObservationJournal.Restore(this,owners,elapsed,started);
}

/// <summary>Bounded cumulative observations survive coalesced checkpoints; never consume gameplay RNG.</summary>
internal sealed class RoomObservationJournal
{
    internal RoomCombatObservations Combat { get; private set; }=new();
    internal const int MaximumEvents=4096;
    internal const int MaximumItemsPerEvent=128;
    private readonly List<RoomEventObservation> _events=[];
    private readonly Dictionary<string,RoomBuildProfile> _profiles=new(StringComparer.Ordinal);
    private readonly Dictionary<(Guid Player,Guid Battle),string> _battleBuilds=[];
    private long _lastSequence;
    internal bool HasFinished(Guid player,Guid battle)=>_events.Any(e=>e.PlayerId==player&&e.BattleId==battle&&e.EventName=="battle_finished");

    internal void Append(RoomPlayerState player,string name,string source,string result,TimeSpan elapsed,DateTimeOffset? started,
        Guid? battleId,string cell,CombatCardCatalog catalog,IEnumerable<ExplorationItem>? items=null,int? applied=null,string? optionId=null,int? healPercent=null,int? hpBefore=null)
    {
        if(_lastSequence<long.MaxValue)_lastSequence++;
        if(_events.Count>=MaximumEvents)return;
        var profileId=CaptureProfile(player,catalog);
        var battleProfile=battleId is { } battle?_battleBuilds.GetValueOrDefault((player.PlayerId,battle)):null;
        var all=(items??[]).ToArray();var kept=all.Take(MaximumItemsPerEvent).Select(item=>new RoomLootObservation(item.ItemId,item.Kind.ToString(),item.Quantity,
            item.Equipment?.Quality,item.IsGenerated,item.IsSafe,item.IsCombatProjection)).ToArray();
        DateTimeOffset? at=started is { } start&&elapsed>=TimeSpan.Zero&&elapsed.Ticks<=DateTimeOffset.MaxValue.UtcTicks-start.UtcTicks
            ?new DateTimeOffset(start.UtcTicks+elapsed.Ticks,TimeSpan.Zero):null;
        _events.Add(new(_lastSequence,player.PlayerId,player.HeroClass,player.IsBot,name,source,result,elapsed,at,battleId,player.Position,cell,kept,all.Length-kept.Length,
            player.Combat.Hp,player.Combat.EffectiveMaximumHp,applied,optionId,healPercent,hpBefore,profileId,battleProfile));
    }

    private string? CaptureProfile(RoomPlayerState player,CombatCardCatalog catalog)
    {
        var profile=RoomBuildProfiles.Capture(player,catalog);
        if(profile is null||!_profiles.ContainsKey(profile.ProfileId)&&_profiles.Count>=512)return null;
        _profiles.TryAdd(profile.ProfileId,profile);return profile.ProfileId;
    }

    internal void BeginBattle(RoomPlayerState player,CombatCardCatalog catalog,Guid battleId)
    {
        var key=(player.PlayerId,battleId);
        if(_battleBuilds.ContainsKey(key)||_battleBuilds.Count>=1024)return;
        if(CaptureProfile(player,catalog) is { } id)_battleBuilds.Add(key,id);
    }

    internal RoomObservationSnapshot Capture()=>new(1,_lastSequence,_lastSequence-_events.Count,_events.ToArray(),_profiles.Values.ToArray(),
        _battleBuilds.Select(pair=>new RoomBattleBuildBinding(pair.Key.Player,pair.Key.Battle,pair.Value)).ToArray(),Combat.Capture());

    internal static RoomObservationJournal Restore(RoomObservationSnapshot snapshot,IReadOnlyList<RoomObservationOwner> players,TimeSpan elapsed,DateTimeOffset? started)
    {
        if(snapshot.SchemaVersion!=1||snapshot.Events is null||snapshot.Events.Count>MaximumEvents||snapshot.LastSequence<snapshot.Events.Count||
            snapshot.DroppedEvents!=snapshot.LastSequence-snapshot.Events.Count||snapshot.DroppedEvents<0||
            snapshot.DroppedEvents>0&&snapshot.Events.Count!=MaximumEvents||started is null||
            players.Select(p=>p.PlayerId).Distinct().Count()!=players.Count)
            throw new DomainValidationException("Saved room observations have an invalid version, size or sequence.");
        var profiles=snapshot.Profiles??[];
        if(profiles.Count>512||profiles.Select(p=>p.ProfileId).Distinct(StringComparer.Ordinal).Count()!=profiles.Count)
            throw new DomainValidationException("Saved build observation index is oversized or duplicated.");
        foreach(var profile in profiles)profile.RequireValid();
        var profileIds=profiles.Select(p=>p.ProfileId).ToHashSet(StringComparer.Ordinal);
        var bindings=snapshot.BattleBuilds??[];
        if(bindings.Count>1024||bindings.Select(b=>(b.PlayerId,b.BattleId)).Distinct().Count()!=bindings.Count||
            bindings.Any(b=>b.BattleId==Guid.Empty||!players.Any(p=>p.PlayerId==b.PlayerId)||!profileIds.Contains(b.ProfileId)))
            throw new DomainValidationException("Saved battle build bindings disagree with their bounded original index.");
        long prior=0;
        foreach(var row in snapshot.Events)
        {
            var owner=players.SingleOrDefault(p=>p.PlayerId==row.PlayerId);
            if(row.Sequence!=++prior||owner is null||owner.HeroClass!=row.HeroClass||owner.IsBot!=row.IsBot||!Enum.IsDefined(row.HeroClass)||
                row.EventName is not("battle_finished" or "loot_generated" or "loot_chosen" or "loot_extracted" or "loot_lost")||
                string.IsNullOrEmpty(row.Source)||row.Source.Length>80||string.IsNullOrEmpty(row.Result)||row.Result.Length>80||
                string.IsNullOrEmpty(row.CellType)||row.CellType.Length>80||row.OptionId?.Length>160||
                row.BuildProfileId is { } profileId&&!profileIds.Contains(profileId)||
                row.BattleBuildProfileId is { } battleProfile&&
                    (row.BattleId is null||!bindings.Any(b=>b.PlayerId==row.PlayerId&&b.BattleId==row.BattleId&&b.ProfileId==battleProfile))||
                row.RoomElapsed<TimeSpan.Zero||row.RoomElapsed>elapsed||row.Items is null||row.Items.Count>MaximumItemsPerEvent||row.OmittedItems<0||
                row.Items.Any(item=>string.IsNullOrEmpty(item.ItemId)||item.ItemId.Length>160||item.Quantity<0||!Enum.TryParse<ExplorationItemKind>(item.Kind,out _))||
                row.OccurredAtUtc is { } at&&(at.Offset!=TimeSpan.Zero||row.RoomElapsed.Ticks>DateTimeOffset.MaxValue.UtcTicks-started.Value.UtcTicks||at.UtcTicks!=started.Value.UtcTicks+row.RoomElapsed.Ticks))
                throw new DomainValidationException("Saved room observation disagrees with its original room.");
        }
        var journal=new RoomObservationJournal{_lastSequence=snapshot.LastSequence};journal._events.AddRange(snapshot.Events);
        journal.Combat=RoomCombatObservations.Restore(snapshot.Combat,players,elapsed);
        foreach(var profile in profiles)journal._profiles.Add(profile.ProfileId,profile);
        foreach(var binding in bindings)journal._battleBuilds.Add((binding.PlayerId,binding.BattleId),binding.ProfileId);
        return journal;
    }
}

public sealed partial class BattleRoom
{
    private RoomObservationJournal? _observations;
    private void SelectCombatObservation(RoomPlayerState player,Guid? battle,string mode,bool partial=false)
    {
        if(_observations is null)return;
        var created=_observations.Combat.Select(player.PlayerId,battle,mode,battle is null?"OutOfCombat":ObservationCellKind(player),Elapsed,partial,player.Combat.Deck.Hand.Count);
        if(created)_observations.Combat.Record(player.PlayerId,new(CombatMetric.NaturalIntervalSample,Sample:player.Combat.NaturalDrawIntervalSeconds),Elapsed);
        player.Combat.SetObservation(value=>
        {
            if(!_combatPreview)_observations.Combat.Record(player.PlayerId,value,Elapsed);
        });
    }

    private void ResumeCombatObservation(RoomPlayerState player,bool partial=false)
    {
        if(player.Phase is RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted){player.Combat.SetObservation(null);_observations?.Combat.End(player.PlayerId);return;}
        var pvp=player.Phase==RoomPlayerPhase.Pvp;
        SelectCombatObservation(player,pvp?player.CurrentDuelId:player.Phase==RoomPlayerPhase.Pve?player.Pve?.BattleId:null,pvp?"Pvp":player.Phase==RoomPlayerPhase.Pve?"Pve":"OutOfCombat",partial);
    }

    private void MeasureCombat(RoomPlayerState player,Guid? battle,CombatMetric metric,long amount)
    {
        if(!_combatPreview)_observations?.Combat.Record(player.PlayerId,battle,new(metric,amount),Elapsed);
    }
    private void ObserveRoomEvent(RoomPlayerState player,string name,string source,string result,IEnumerable<ExplorationItem>? items=null,
        int? applied=null,Guid? battleId=null,TimeSpan? at=null,string? optionId=null,int? healPercent=null,int? hpBefore=null)
    {
        if(_observations is null)return;
        var kind=ObservationCellKind(player);
        _observations.Append(player,name,source,result,at??Elapsed,StartedAtUtc,battleId??player.Pve?.BattleId??player.CurrentDuelId,kind,_catalog,items,applied,optionId,healPercent,hpBefore);
    }

    private string ObservationCellKind(RoomPlayerState player)
    {
        var cell=player.Position is { } position&&Map is not null?Map.GetCell(position):null;
        return cell is null?"Unknown":cell.IsBoss||cell.MonsterGroupId=="BOSS"?"Boss":cell.MonsterGroupId=="BOX"?"Treasure":cell.MonsterGroupId.StartsWith('E')?"Elite":"Normal";
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
