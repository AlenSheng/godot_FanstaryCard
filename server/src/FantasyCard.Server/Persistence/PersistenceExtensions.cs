using Npgsql;
using FantasyCard.Server.Common;

namespace FantasyCard.Server.Persistence;

public sealed class PersistenceOptions
{
    public const string SectionName = "Persistence";

    // This service is deployed with two logical CPUs. Keep the default pool
    // small enough to avoid making PostgreSQL and the .NET scheduler compete
    // with an unbounded number of concurrent commands.
    public int MaxPoolSize { get; init; } = 16;
    public int MinPoolSize { get; init; } = 1;
    public int ConnectionTimeoutSeconds { get; init; } = 5;
    public int CommandTimeoutSeconds { get; init; } = 10;
    public int KeepAliveSeconds { get; init; } = 30;
}

public static class PersistenceExtensions
{
    public static IServiceCollection AddFantasyCardPersistence(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        var connectionString = configuration.GetConnectionString("Postgres")
            ?? throw new InvalidOperationException("ConnectionStrings:Postgres is required.");

        var persistence = configuration
            .GetSection(PersistenceOptions.SectionName)
            .Get<PersistenceOptions>() ?? new PersistenceOptions();
        Validate(persistence);
        var testBypass = configuration.GetValue<bool>("RequestLimits:OwnedTestBypass");

        services.AddSingleton(_ =>
        {
            var connection = new NpgsqlConnectionStringBuilder(connectionString)
            {
                // The owned test profile also removes the application pool's
                // concurrent connection ceiling. PostgreSQL/resource limits remain.
                Pooling = !testBypass,
                MaxPoolSize = persistence.MaxPoolSize,
                MinPoolSize = persistence.MinPoolSize,
                Timeout = persistence.ConnectionTimeoutSeconds,
                CommandTimeout = persistence.CommandTimeoutSeconds,
                KeepAlive = persistence.KeepAliveSeconds
            };
            var dataSourceBuilder = new NpgsqlDataSourceBuilder(connection.ConnectionString)
            {
                Name = "FantasyCard.Postgres"
            };
            return dataSourceBuilder.Build();
        });
        services.AddHostedService<DatabaseMigrator>();
        services.AddSingleton<TimeProvider>(TimeProvider.System);
        return services;
    }

    private static void Validate(PersistenceOptions options)
    {
        if (options.MinPoolSize < 0 || options.MaxPoolSize < options.MinPoolSize || options.MaxPoolSize > 256)
            throw new InvalidOperationException("Persistence pool size is outside the supported range.");
        if (options.ConnectionTimeoutSeconds is < 1 or > 60 ||
            options.CommandTimeoutSeconds is < 1 or > 120 ||
            options.KeepAliveSeconds is < 0 or > 3600)
            throw new InvalidOperationException("Persistence timeout settings are outside the supported range.");
    }
}
