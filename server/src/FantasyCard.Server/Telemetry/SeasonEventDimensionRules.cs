using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Telemetry;

public static class SeasonEventDimensionRules
{
    private static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web){Converters={new JsonStringEnumConverter()}};

    public static (SeasonEventDimensions Dimensions,string Basis,RoomBuildProfile? Profile) Room(string config,SeasonContext? season,string difficulty,
        RoomEventObservation row,IReadOnlyDictionary<string,RoomBuildProfile> profiles)
    {
        var battle=row.EventName=="battle_finished";var id=battle?row.BattleBuildProfileId:row.BuildProfileId;
        var profile=id is null?null:profiles.GetValueOrDefault(id);
        var dimensions=new SeasonEventDimensions(season?.SeasonId,season?.DifficultyId??difficulty,row.HeroClass.ToString(),profile?.BuildType,
            profile?.GrowthStage,row.IsBot?"Bot":"Human",row.CellType,season?.RulesetId,config,season?.StatsVersion,row.Result);
        return(dimensions,profile is null?"MissingOriginal":battle?"BattleStart":"EventState",profile);
    }

    public static RoomBuildProfile? StoredProfile(string? json)
    {
        if(json is null||json.Length>65536)return null;
        try
        {
            var profile=JsonSerializer.Deserialize<RoomBuildProfile>(json,Json);profile?.RequireValid();return profile;
        }
        catch(Exception error)when(error is JsonException or DomainValidationException){return null;}
    }

    public static IReadOnlyDictionary<string,int> UnknownCounts(IEnumerable<SeasonEventDimensions> source)
    {
        var counts=new Dictionary<string,int>(StringComparer.Ordinal){["season"]=0,["difficulty"]=0,["class"]=0,["build"]=0,["growth"]=0,["playerKind"]=0,["cell"]=0,["rulesetVersion"]=0,["configVersion"]=0,["statsVersion"]=0,["result"]=0};
        foreach(var d in source)
        {
            if(d.SeasonId is null)counts["season"]++;
            if(d.DifficultyId is null)counts["difficulty"]++;
            if(d.HeroClass is null)counts["class"]++;
            if(d.BuildType is null)counts["build"]++;
            if(d.GrowthStage is null)counts["growth"]++;
            if(d.PlayerKind=="Unknown")counts["playerKind"]++;
            if(d.CellType is not("Normal" or "Elite" or "Boss" or "Treasure" or "RunSummary" or "Lobby" or "Archive"))counts["cell"]++;
            if(d.RulesetId is null)counts["rulesetVersion"]++;
            if(d.ConfigVersion is null)counts["configVersion"]++;
            if(d.StatsVersion is null)counts["statsVersion"]++;
            if(string.IsNullOrEmpty(d.Result))counts["result"]++;
        }
        return counts;
    }
}
