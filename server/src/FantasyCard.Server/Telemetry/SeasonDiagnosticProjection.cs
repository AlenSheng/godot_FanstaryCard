using System.Globalization;

namespace FantasyCard.Server.Telemetry;

public sealed record DiagnosticSlice(string Kind,IReadOnlyDictionary<string,string?> Dimensions,IReadOnlyDictionary<string,string> Measures);
public sealed record ChoiceDiagnosticGroup(SeasonEventDimensions Dimensions,string HealthBand,string? OriginalBias,int Selections,int Equipment,int Fragments,int Heal,int ZeroAppliedHeal);
public sealed record ChoiceDiagnosticCoverage(int OfferedSets,int IncompleteOfferSets,int DuplicateOfferRows,int MatchedSelections,int UnmatchedSelections,bool SourceTruncated);

public static class SeasonDiagnosticProjection
{
    public static string HealthBand(int? hp,int? baseMaximum,int effectiveMaximum)
    {
        if(hp is null||baseMaximum is null or <=0)return "MissingOriginal";
        if(hp>effectiveMaximum)return "AboveRecordedEffective";
        if(hp>baseMaximum)return "AboveBaseWithinEffective";
        return (long)hp*100<=(long)baseMaximum*60?"AtOrBelow60PercentBase":"Above60PercentBase";
    }

    public static (IReadOnlyList<ChoiceDiagnosticGroup> Groups,ChoiceDiagnosticCoverage Coverage) Choices(RoomEventTelemetryReport source)
    {
        var offers=source.Events.Where(e=>e.Event.EventName=="loot_generated"&&e.Event.Result=="PotentialChoice"&&e.Event.OptionId is not null).ToArray();
        var byOption=offers.GroupBy(e=>(e.RoomId,e.Event.PlayerId,e.Event.OptionId)).ToDictionary(g=>g.Key,g=>g.OrderBy(e=>e.Event.Sequence).First());
        static string SetId(string option){var at=option.IndexOf(':');return at<0?option:option[(at+1)..];}
        var sets=offers.GroupBy(e=>(e.RoomId,e.Event.PlayerId,Set:SetId(e.Event.OptionId!))).ToArray();
        var matched=new List<(DurableRoomEvent Offer,DurableRoomEvent Selection)>();var unmatched=0;
        foreach(var selection in source.Events.Where(e=>e.Event.EventName=="loot_chosen"&&e.Event.Source=="RewardChoice"))
        {
            if(byOption.TryGetValue((selection.RoomId,selection.Event.PlayerId,selection.Event.OptionId),out var offer)&&offer.Event.Sequence<selection.Event.Sequence)matched.Add((offer,selection));
            else unmatched++;
        }
        var groups=matched.GroupBy(p=>(p.Offer.Dimensions,Health:HealthBand(p.Offer.Event.HpBefore,p.Offer.Event.BaseMaximumHp,p.Offer.Event.EffectiveMaximumHp),Bias:p.Offer.Event.RewardBias))
            .Select(g=>new ChoiceDiagnosticGroup(g.Key.Dimensions,g.Key.Health,g.Key.Bias,g.Count(),g.Count(p=>p.Selection.Event.Result=="Equipment"),
                g.Count(p=>p.Selection.Event.Result=="EquipmentFragments"),g.Count(p=>p.Selection.Event.Result=="ImmediateHeal"),g.Count(p=>p.Selection.Event.Result=="ImmediateHeal"&&p.Selection.Event.AppliedQuantity==0)))
            .OrderBy(g=>g.Dimensions.SeasonId,StringComparer.Ordinal).ThenBy(g=>g.Dimensions.DifficultyId,StringComparer.Ordinal).ThenBy(g=>g.Dimensions.HeroClass,StringComparer.Ordinal).ThenBy(g=>g.HealthBand,StringComparer.Ordinal).ThenBy(g=>g.OriginalBias,StringComparer.Ordinal).ToArray();
        return(groups,new(sets.Length,sets.Count(g=>g.Select(e=>e.Event.OptionId).Distinct(StringComparer.Ordinal).Count()!=3),offers.Length-byOption.Count,matched.Count,unmatched,source.SourceTruncated));
    }
    public static IReadOnlyDictionary<string,string?> Dimensions(string json)=>System.Text.Json.JsonSerializer.Deserialize<Dictionary<string,string?>>(json)??new();
    public static IReadOnlyDictionary<string,string> Measures(string json)=>System.Text.Json.JsonSerializer.Deserialize<Dictionary<string,string>>(json)??new();
}
