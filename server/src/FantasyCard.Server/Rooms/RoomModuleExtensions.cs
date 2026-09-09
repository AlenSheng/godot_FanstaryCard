namespace FantasyCard.Server.Rooms;

public static class RoomModuleExtensions
{
    public static IServiceCollection AddRoomsModule(this IServiceCollection services)
    {
        services.AddSingleton<RoomRegistry>();
        services.AddSingleton<RoomSnapshotRepository>();
        services.AddSingleton<RoomRecoveryState>();
        services.AddSingleton<RoomPersistenceState>();
        services.AddHealthChecks().AddCheck<RoomRecoveryHealthCheck>("room-recovery", tags: ["ready"]);
        services.AddHealthChecks().AddCheck<RoomPersistenceHealthCheck>("room-persistence", tags: ["ready"]);
        services.AddHostedService<RoomRecoveryWorker>();
        return services;
    }
}
