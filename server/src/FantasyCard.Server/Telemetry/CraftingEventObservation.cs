using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Telemetry;

/// <summary>Immutable lobby facts stored with the original business receipt, never current player state.</summary>
public sealed record SeasonEventDimensions(string? SeasonId,string? DifficultyId,string? HeroClass,string? BuildType,
    string? GrowthStage,string PlayerKind,string CellType,string? RulesetId,string? ConfigVersion,string? StatsVersion,string Result);
public sealed record CraftingEventObservation(int SchemaVersion,SeasonEventDimensions Dimensions,IReadOnlyList<string> EventNames,
    Guid ItemId,string Quality,string Operation,string PhysicalFlow,string AvailabilityDifficultyId,
    int? WishFailuresBefore,int? WishFailuresAfter,bool? PityTriggered,bool? AlreadyLearned,
    long BlueprintsSpent,long OrangeBlueprintsSpent,long FragmentsSpent);
public sealed record DurableCraftingEvent(string EventId,Guid SourceActionId,DateTimeOffset OccurredAtUtc,Guid PlayerId,
    string EventName,CraftingEventObservation Observation);

public static class CraftingEventObservations
{
    public static CraftingEventObservation Create(SeasonContext season,int maximumDifficulty,Guid itemId,string quality,
        string operation,int? failuresBefore=null,int? failuresAfter=null,bool? guaranteed=null,bool? alreadyLearned=null,
        long blueprints=0,long orangeBlueprints=0,long fragments=0)
    {
        var names=operation switch
        {
            "equipment.craft" when guaranteed is true => new[]{"craft_completed","pity_triggered"},
            "equipment.craft" or "equipment.reforge" => ["craft_completed"],
            "recipe.learn" when alreadyLearned is false => ["recipe_learned"],
            "recipe.learn" when alreadyLearned is true => [],
            _ => throw new ArgumentException("Unknown completed crafting operation.",nameof(operation))
        };
        // Lobby actions have no played difficulty, hero, build, growth or match
        // participant. Do not label realm.Context's D0 or latest loadout as fact.
        var dimensions=new SeasonEventDimensions(season.SeasonId,null,null,null,null,"Unknown","Lobby",season.RulesetId,
            season.ConfigVersion,season.StatsVersion,"Completed");
        var flow=operation switch{"equipment.craft"=>"Mint","equipment.reforge"=>"Mutation",_=>"RetainedSample"};
        return new(1,dimensions,names,itemId,quality,operation,flow,$"D{maximumDifficulty}",failuresBefore,failuresAfter,
            guaranteed,alreadyLearned,blueprints,orangeBlueprints,fragments);
    }

    public static IReadOnlyList<DurableCraftingEvent> Expand(Guid actionId,Guid playerId,DateTimeOffset at,CraftingEventObservation observation)
        => observation.EventNames.Select(name=>new DurableCraftingEvent($"{actionId:N}:{name}",actionId,at.ToUniversalTime(),playerId,name,observation)).ToArray();
}
