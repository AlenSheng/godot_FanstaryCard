using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using System.Text.Json.Serialization;

namespace FantasyCard.Domain.Rooms;

public sealed record RoomCombatObservation(Guid PlayerId,Guid? BattleId,string Mode,string CellType,bool Partial,TimeSpan ObservedFromRoomElapsed,TimeSpan ObservedThroughRoomElapsed,
    IReadOnlyDictionary<string,long> Counters,double? NaturalIntervalMinimum,double? NaturalIntervalMaximum,
    double? EffectiveIntervalMinimum,double? EffectiveIntervalMaximum,double DiscardedFractionalCharge,bool Saturated);
public sealed record RoomCombatObservationSnapshot(int SchemaVersion,IReadOnlyList<RoomCombatObservation> Rows,long OmittedMeasurements,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingDefault)] bool HistoryMissing=false);

internal sealed class RoomCombatObservations
{
    private sealed class Row(Guid player,Guid? battle,string mode,string cell,bool partial,TimeSpan from)
    {
        internal readonly Guid Player=player;
        internal readonly Guid? Battle=battle;
        internal readonly string Mode=mode;
        internal readonly string Cell=cell;
        internal readonly bool Partial=partial;
        internal readonly TimeSpan From=from;
        internal TimeSpan Through=from;
        internal readonly Dictionary<string,long> Counters=new(StringComparer.Ordinal);
        internal double? NaturalMin,NaturalMax,EffectiveMin,EffectiveMax;
        internal double Fraction;
        internal bool Saturated;
        internal bool Dirty=true;
        private RoomCombatObservation? _snapshot;
        internal RoomCombatObservation Capture()
        {
            if(!Dirty&&_snapshot is not null)return _snapshot;
            _snapshot=new(Player,Battle,Mode,Cell,Partial,From,Through,Counters.OrderBy(p=>p.Key,StringComparer.Ordinal).ToDictionary(p=>p.Key,p=>p.Value,StringComparer.Ordinal),NaturalMin,NaturalMax,EffectiveMin,EffectiveMax,Fraction,Saturated);
            Dirty=false;return _snapshot;
        }
    }
    private readonly Dictionary<(Guid Player,Guid? Battle),Row> _rows=[];
    private readonly Dictionary<Guid,Guid?> _active=[];
    private long _omitted;
    private bool _historyMissing;

    internal bool Select(Guid player,Guid? battle,string mode,string cell,TimeSpan from,bool partial=false,int hand=0)
    {
        if((mode=="OutOfCombat")!=(battle is null)){_active.Remove(player);if(_omitted<long.MaxValue)_omitted++;return false;}
        _active[player]=battle;var key=(player,battle);
        if(!_rows.ContainsKey(key)&&_rows.Count<1024)
        {
            var row=new Row(player,battle,mode,cell,partial,from);row.Counters.Add(nameof(CombatMetric.EntryHandObserved),hand);_rows.Add(key,row);return true;
        }
        return false;
    }
    internal void End(Guid player)=>_active.Remove(player);
    internal void Record(Guid player,CombatMeasurement value,TimeSpan at)
    {
        if(_active.TryGetValue(player,out var battle))Record(player,battle,value,at);
    }
    internal void Record(Guid player,Guid? battle,CombatMeasurement value,TimeSpan at)
    {
        if(!_rows.TryGetValue((player,battle),out var row)){if(_omitted<long.MaxValue)_omitted++;return;}
        row.Dirty=true;
        if(at>row.Through)row.Through=at;
        if(value.Sample is { } sample)
        {
            if(!double.IsFinite(sample)||sample<0){row.Saturated=true;return;}
            switch(value.Metric)
            {
                case CombatMetric.NaturalIntervalSample:row.NaturalMin=Math.Min(row.NaturalMin??sample,sample);row.NaturalMax=Math.Max(row.NaturalMax??sample,sample);break;
                case CombatMetric.EffectiveIntervalSample:row.EffectiveMin=Math.Min(row.EffectiveMin??sample,sample);row.EffectiveMax=Math.Max(row.EffectiveMax??sample,sample);break;
                case CombatMetric.DiscardedFractionSample:
                    if(double.IsFinite(row.Fraction+sample))row.Fraction+=sample;else row.Saturated=true;
                    break;
            }
            return;
        }
        if(value.Amount<=0)return;
        var key=value.Metric.ToString();var previous=row.Counters.GetValueOrDefault(key);
        if(value.Amount>long.MaxValue-previous){row.Counters[key]=long.MaxValue;row.Saturated=true;}else row.Counters[key]=previous+value.Amount;
    }
    internal RoomCombatObservationSnapshot Capture()=>new(1,_rows.Values.Select(r=>r.Capture()).ToArray(),_omitted,_historyMissing);

    internal static RoomCombatObservations Restore(RoomCombatObservationSnapshot? snapshot,IReadOnlyList<RoomObservationOwner> owners,TimeSpan elapsed)
    {
        var result=new RoomCombatObservations();if(snapshot is null){result._historyMissing=true;return result;}
        if(snapshot.SchemaVersion!=1||snapshot.Rows is null||snapshot.Rows.Count>1024||snapshot.OmittedMeasurements<0||
            snapshot.Rows.Select(r=>(r.PlayerId,r.BattleId)).Distinct().Count()!=snapshot.Rows.Count)
            throw new DomainValidationException("Saved combat observations have invalid bounds or identity.");
        foreach(var r in snapshot.Rows)
        {
            if(!owners.Any(p=>p.PlayerId==r.PlayerId)||r.BattleId==Guid.Empty||r.Mode is not("Pve" or "Pvp" or "OutOfCombat")||
                r.ObservedFromRoomElapsed<TimeSpan.Zero||r.ObservedFromRoomElapsed>elapsed||r.ObservedThroughRoomElapsed<r.ObservedFromRoomElapsed||r.ObservedThroughRoomElapsed>elapsed||
                (r.Mode=="OutOfCombat")!=(r.BattleId is null)||string.IsNullOrEmpty(r.CellType)||r.CellType.Length>80||r.Counters is null||r.Counters.Count>Enum.GetValues<CombatMetric>().Length||
                r.Counters.Any(p=>p.Value<0||!Enum.TryParse<CombatMetric>(p.Key,out var metric)||!Enum.IsDefined(metric)||metric.ToString()!=p.Key)||
                new[]{r.NaturalIntervalMinimum,r.NaturalIntervalMaximum,r.EffectiveIntervalMinimum,r.EffectiveIntervalMaximum}.Any(v=>v is { } x&&(!double.IsFinite(x)||x<0))||
                !double.IsFinite(r.DiscardedFractionalCharge)||r.DiscardedFractionalCharge<0)
                throw new DomainValidationException("Saved combat measurements disagree with their original room.");
            var row=new Row(r.PlayerId,r.BattleId,r.Mode,r.CellType,r.Partial,r.ObservedFromRoomElapsed){Through=r.ObservedThroughRoomElapsed,NaturalMin=r.NaturalIntervalMinimum,NaturalMax=r.NaturalIntervalMaximum,EffectiveMin=r.EffectiveIntervalMinimum,EffectiveMax=r.EffectiveIntervalMaximum,Fraction=r.DiscardedFractionalCharge,Saturated=r.Saturated};
            foreach(var pair in r.Counters)row.Counters.Add(pair.Key,pair.Value);result._rows.Add((r.PlayerId,r.BattleId),row);
        }
        result._omitted=snapshot.OmittedMeasurements;result._historyMissing=snapshot.HistoryMissing;return result;
    }
}
