using Npgsql;

namespace FantasyCard.Server.Persistence;

public static class PersistenceExtensions
{
    public static IServiceCollection AddFantasyCardPersistence(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        var connectionString = configuration.GetConnectionString("Postgres")
            ?? throw new InvalidOperationException("ConnectionStrings:Postgres is required.");

        services.AddSingleton(_ =>
        {
            var dataSourceBuilder = new NpgsqlDataSourceBuilder(connectionString)
            {
                Name = "FantasyCard.Postgres"
            };
            return dataSourceBuilder.Build();
        });
        services.AddHostedService<DatabaseMigrator>();
        services.AddSingleton<TimeProvider>(TimeProvider.System);
        return services;
    }
}
