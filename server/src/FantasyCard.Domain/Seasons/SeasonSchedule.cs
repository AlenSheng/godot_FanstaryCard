using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Seasons;

public enum SeasonLifecycleStage { Legacy, Upcoming, Active, Closed }
public sealed record SeasonScheduleSnapshot(
    SeasonLifecycleStage Stage, SeasonDefinition? Current, SeasonDefinition? Next, bool LegacyAllowed);

public static class SeasonSchedule
{
    public static SeasonScheduleSnapshot Resolve(IEnumerable<SeasonDefinition> definitions, DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(definitions);
        var ordered = definitions.OrderBy(definition => definition.StartsAtUtc).ToArray();
        for (var index = 1; index < ordered.Length; index++)
            if (ordered[index].StartsAtUtc < ordered[index - 1].EndsAtUtc)
                throw new DomainValidationException("Season calendar periods cannot overlap.");
        if (ordered.Length == 0)
            return new(SeasonLifecycleStage.Legacy, null, null, true);
        var current = ordered.SingleOrDefault(definition => definition.Contains(now));
        var next = ordered.FirstOrDefault(definition => definition.StartsAtUtc > now);
        if (current is not null)
            return new(SeasonLifecycleStage.Active, current, next, false);
        if (ordered[0].StartsAtUtc > now)
            return new(SeasonLifecycleStage.Upcoming, null, next, true);
        // Once seasons start, a gap or final closure must never reactivate the legacy economy.
        return new(SeasonLifecycleStage.Closed, null, next, false);
    }
}
