using FantasyCard.Server.Progression;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresRedEquipmentQuotaTests
{
    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(
        Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Concurrent_red_drops_allow_only_one_claim_per_server_week()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var now = new DateTimeOffset(2026, 9, 6, 20, 0, 0, TimeSpan.Zero);
        var attempts = Enumerable.Range(0, 8).Select(async index =>
        {
            await using var connection = await database.DataSource.OpenConnectionAsync(cancellationToken);
            await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
            var claimed = await RedEquipmentQuotaRepository.TryClaimAsync(
                connection, transaction, now, RedEquipmentDropSource.ChaosBoss,
                Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid(), cancellationToken);
            await transaction.CommitAsync(cancellationToken);
            return claimed;
        });

        var results = await Task.WhenAll(attempts);

        Assert.Single(results, value => value);
        await using var command = database.DataSource.CreateCommand(
            "SELECT count(*) FROM red_equipment_weekly_quotas WHERE week_key='2026-09-07' AND red_dropped_this_week=1");
        Assert.Equal(1L, await command.ExecuteScalarAsync(cancellationToken));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task New_server_week_can_claim_again_and_exposes_audit_snapshot()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var playerId = Guid.NewGuid();
        var equipmentId = Guid.NewGuid();
        var now = new DateTimeOffset(2026, 9, 13, 20, 0, 0, TimeSpan.Zero);
        await using (var connection = await database.DataSource.OpenConnectionAsync(cancellationToken))
        await using (var transaction = await connection.BeginTransactionAsync(cancellationToken))
        {
            Assert.True(await RedEquipmentQuotaRepository.TryClaimAsync(
                connection, transaction, now, RedEquipmentDropSource.ChaosBoss,
                playerId, Guid.NewGuid(), equipmentId, cancellationToken));
            await transaction.CommitAsync(cancellationToken);
        }

        var repository = new RedEquipmentQuotaRepository(database.DataSource, new FixedTimeProvider(now));
        var snapshot = await repository.GetCurrentAsync(cancellationToken);

        Assert.True(snapshot.IsClaimed);
        Assert.Equal("2026-09-14", snapshot.WeekKey);
        Assert.Equal(RedEquipmentDropSource.ChaosBoss, snapshot.Source);
        Assert.Equal(playerId, snapshot.PlayerId);
        Assert.Equal(equipmentId, snapshot.EquipmentId);
    }

    private sealed class FixedTimeProvider(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }
}
