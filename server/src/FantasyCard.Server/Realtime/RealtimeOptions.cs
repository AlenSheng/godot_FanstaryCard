namespace FantasyCard.Server.Realtime;

public sealed class RealtimeOptions
{
    public const string SectionName = "Realtime";

    public int EventStreamIdleRetentionMinutes { get; init; } = 60;
    public int CleanupIntervalMinutes { get; init; } = 10;
}
