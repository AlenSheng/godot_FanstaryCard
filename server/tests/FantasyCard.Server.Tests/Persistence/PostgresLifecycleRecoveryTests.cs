using System.Buffers.Binary;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresLifecycleRecoveryTests
{
    public static bool HasTestDatabase => PostgresRuntimeIntegrationTests.HasTestDatabase;

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task MarkRunning_retry_accepts_the_committed_result_without_reopening_terminal_matches()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var matchId = Guid.NewGuid();
        await InsertMatchAsync(database, matchId, Guid.NewGuid(), "Launching");
        using var metrics = new ServerMetrics();
        var repository = new MatchmakingRepository(database.DataSource, TimeProvider.System, metrics);

        await repository.MarkRunningAsync(matchId, cancellationToken);
        await repository.MarkRunningAsync(matchId, cancellationToken);
        Assert.Equal("Running", await database.ScalarAsync<string>(
            "SELECT status FROM matches WHERE match_id=$1", matchId));
        await database.ExecuteAsync($"UPDATE matches SET status='Completed' WHERE match_id='{matchId:D}'");
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.MarkRunningAsync(matchId, cancellationToken));
        Assert.Equal("Completed", await database.ScalarAsync<string>(
            "SELECT status FROM matches WHERE match_id=$1", matchId));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task MarkRunning_commit_response_loss_retries_same_room_and_restart_restores_it()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var time = new FixedTimeProvider(DateTimeOffset.UtcNow);
        using var metrics = new ServerMetrics();
        var settings = new NpgsqlConnectionStringBuilder(database.ConnectionString);
        await using var proxy = new CommitResponseDropProxy(settings.Host!, settings.Port);
        settings.Host = proxy.SocketDirectory;
        settings.SslMode = SslMode.Disable;
        await using var intercepted = NpgsqlDataSource.Create(settings.ConnectionString);
        var repository = new MatchmakingRepository(intercepted, time, metrics);
        var (playerId, pending) = await PrepareReadyMatchAsync(database, time, repository);

        var snapshots = new RoomSnapshotRepository(database.DataSource, time, metrics);
        await using (var rooms = new RoomRegistry(time))
        {
            using var coordinator = new RoomReadyCoordinator(repository, rooms, snapshots,
                new RealtimeEventStore(time), new ConnectionRegistry(), time,
                NullLogger<RoomReadyCoordinator>.Instance);
            await Assert.ThrowsAnyAsync<NpgsqlException>(() => coordinator.ProcessNextAsync(time.GetUtcNow(), cancellationToken));
            Assert.True(proxy.DroppedCommittedResponse);
            Assert.Equal("Running", await database.ScalarAsync<string>(
                "SELECT status FROM matches WHERE match_id=$1", pending.MatchId));
            Assert.False(rooms.ContainsRoom(pending.RoomId));

            Assert.True(await coordinator.ProcessNextAsync(time.GetUtcNow(), cancellationToken));
            Assert.True(rooms.TryGetForPlayer(playerId, out var actor, out var matchId));
            Assert.Equal(pending.RoomId, actor!.RoomId);
            Assert.Equal(pending.MatchId, matchId);
            Assert.Single(rooms.GetRoomIds());
            Assert.False(await coordinator.ProcessNextAsync(time.GetUtcNow(), cancellationToken));
        }

        var recoveryState = new RoomRecoveryState();
        await using var recovered = new RoomRegistry(time);
        await new RoomRecoveryWorker(snapshots, recovered, recoveryState, time,
            NullLogger<RoomRecoveryWorker>.Instance).StartAsync(cancellationToken);
        Assert.True(recoveryState.Capture().IsHealthy);
        Assert.True(recovered.TryGetForPlayer(playerId, out var restored, out var restoredMatch));
        Assert.Equal(pending.RoomId, restored!.RoomId);
        Assert.Equal(pending.MatchId, restoredMatch);
        Assert.Equal(0, await database.ScalarAsync<int>(
            "SELECT health_potion_count FROM player_consumables WHERE player_id=$1", playerId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE request_id=$1 AND reason='match.start'", pending.MatchId.ToString("D")));
        RecordCanonicalLaunch("mark-running-response-loss", new
        {
            faultObserved = proxy.DroppedCommittedResponse,
            durableStatus = await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", pending.MatchId),
            restoredSameRoom = restored!.RoomId == pending.RoomId,
            restoredSameMatch = restoredMatch == pending.MatchId,
            roomCount = recovered.GetRoomIds().Count,
            potionCount = await database.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", playerId),
            startMovementCount = await database.ScalarAsync<long>(
                "SELECT count(*) FROM inventory_movements WHERE request_id=$1 AND reason='match.start'", pending.MatchId.ToString("D"))
        });
    }

    [Theory(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [InlineData("snapshot")]
    [InlineData("registry")]
    [Trait("Category", "PostgresIntegration")]
    public async Task Launch_failure_retries_without_duplicate_room_or_asset_reservation(string fault)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var time = new FixedTimeProvider(DateTimeOffset.UtcNow);
        using var metrics = new ServerMetrics();
        var repository = new MatchmakingRepository(database.DataSource, time, metrics);
        var (playerId, pending) = await PrepareReadyMatchAsync(database, time, repository);
        var snapshots = new RoomSnapshotRepository(database.DataSource, time, metrics);
        await using var rooms = new RoomRegistry(time);
        var conflictingRoom = CreateRoom(Guid.NewGuid(), playerId);
        if (fault == "snapshot")
            await database.ExecuteAsync("""
                CREATE FUNCTION fail_launch_checkpoint() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'injected launch checkpoint failure'; END $$;
                CREATE TRIGGER reject_launch_checkpoint BEFORE INSERT ON room_snapshots
                FOR EACH ROW EXECUTE FUNCTION fail_launch_checkpoint();
                """);
        else
            rooms.Register(conflictingRoom, startTicker: false);
        using var coordinator = new RoomReadyCoordinator(repository, rooms, snapshots,
            new RealtimeEventStore(time), new ConnectionRegistry(), time,
            NullLogger<RoomReadyCoordinator>.Instance);

        if (fault == "snapshot")
            await Assert.ThrowsAsync<PostgresException>(() => coordinator.ProcessNextAsync(time.GetUtcNow(), cancellationToken));
        else
            await Assert.ThrowsAsync<InvalidOperationException>(() => coordinator.ProcessNextAsync(time.GetUtcNow(), cancellationToken));
        Assert.Equal("Launching", await database.ScalarAsync<string>(
            "SELECT status FROM matches WHERE match_id=$1", pending.MatchId));
        Assert.False(rooms.ContainsRoom(pending.RoomId));
        var failedStatus = await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", pending.MatchId);
        var failedRoomPresent = rooms.ContainsRoom(pending.RoomId);
        if (fault == "snapshot")
            await database.ExecuteAsync("DROP TRIGGER reject_launch_checkpoint ON room_snapshots");
        else
            await rooms.RemoveAsync(conflictingRoom.RoomId);

        Assert.True(await coordinator.ProcessNextAsync(time.GetUtcNow(), cancellationToken));
        Assert.Single(rooms.GetRoomIds());
        Assert.True(rooms.TryGetForPlayer(playerId, out var actor, out var matchId));
        Assert.Equal(pending.RoomId, actor!.RoomId);
        Assert.Equal(pending.MatchId, matchId);
        Assert.Equal("Running", await database.ScalarAsync<string>(
            "SELECT status FROM matches WHERE match_id=$1", pending.MatchId));
        Assert.Equal(0, await database.ScalarAsync<int>(
            "SELECT health_potion_count FROM player_consumables WHERE player_id=$1", playerId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE request_id=$1 AND reason='match.start'", pending.MatchId.ToString("D")));
        RecordCanonicalLaunch(fault, new
        {
            failedStatus,
            failedRoomPresent,
            durableStatus = await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", pending.MatchId),
            roomCount = rooms.GetRoomIds().Count,
            sameRoom = actor!.RoomId == pending.RoomId,
            sameMatch = matchId == pending.MatchId,
            potionCount = await database.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", playerId),
            startMovementCount = await database.ScalarAsync<long>(
                "SELECT count(*) FROM inventory_movements WHERE request_id=$1 AND reason='match.start'", pending.MatchId.ToString("D"))
        });
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Snapshot_write_failure_withholds_settlement_until_terminal_checkpoint_retry()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var matchId = Guid.NewGuid();
        var playerId = await CreatePlayerAsync(database);
        var room = CreateRoom(Guid.NewGuid(), playerId);
        await InsertMatchAsync(database, matchId, room.RoomId, "Running", playerId);
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics);
        await snapshots.SaveIfDueAsync(room.Capture(), cancellationToken);
        await database.ExecuteAsync("""
            CREATE FUNCTION fail_terminal_checkpoint() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'injected terminal checkpoint failure'; END $$;
            CREATE TRIGGER reject_checkpoint BEFORE UPDATE ON room_snapshots
            FOR EACH ROW EXECUTE FUNCTION fail_terminal_checkpoint();
            """);
        var settlements = new SettlementRepository(database.DataSource, TimeProvider.System, metrics);
        BattleRoomSnapshot terminal;
        await using (var rooms = new RoomRegistry(TimeProvider.System, new SettlementCoordinator(settlements), snapshots))
        {
            var actor = rooms.Register(room, matchId, startTicker: false);
            await actor.ExecuteAsync(new SetPlayerConnectionCommand(playerId, Connected: false), cancellationToken);
            await actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromSeconds(16), DateTimeOffset.UtcNow), cancellationToken);
            terminal = await actor.ExecuteAsync(new GetRoomSnapshotCommand(), cancellationToken);
            Assert.Equal(RoomPlayerPhase.Dead, Assert.Single(terminal.Players).Phase);
        }
        Assert.Equal("Active", await database.ScalarAsync<string>(
            "SELECT state FROM match_players WHERE match_id=$1 AND player_id=$2", matchId, playerId));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", matchId));
        Assert.Empty(await settlements.GetReadyNotificationsAsync(playerId, cancellationToken));
        Assert.Equal(RoomPlayerPhase.ActionBar, Assert.Single((await snapshots.GetAsync(room.RoomId, cancellationToken))!.Players).Phase);

        await database.ExecuteAsync("DROP TRIGGER reject_checkpoint ON room_snapshots");
        await using (var rooms = new RoomRegistry(TimeProvider.System, new SettlementCoordinator(settlements), snapshots))
        {
            var actor = rooms.Register(BattleRoom.Restore(terminal, CombatCardCatalog.CreatePrototype(), 73), matchId, startTicker: false);
            await actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromMilliseconds(100), DateTimeOffset.UtcNow), cancellationToken);
        }
        Assert.Equal("Settled", await database.ScalarAsync<string>(
            "SELECT state FROM match_players WHERE match_id=$1 AND player_id=$2", matchId, playerId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", matchId));
        Assert.Equal(RoomPlayerPhase.Dead, Assert.Single((await snapshots.GetAsync(room.RoomId, cancellationToken))!.Players).Phase);
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Settlement_commit_response_loss_recovers_same_receipt_and_credits_assets_once()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var playerId = await CreatePlayerAsync(database);
        var matchId = Guid.NewGuid();
        await InsertMatchAsync(database, matchId, Guid.NewGuid(), "Running", playerId);
        var before = await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", playerId);
        var settings = new NpgsqlConnectionStringBuilder(database.ConnectionString);
        await using var proxy = new CommitResponseDropProxy(settings.Host!, settings.Port, "COMMIT");
        settings.Host = proxy.SocketDirectory;
        settings.SslMode = SslMode.Disable;
        await using var intercepted = NpgsqlDataSource.Create(settings.ConnectionString);
        using var metrics = new ServerMetrics();
        using var details = JsonDocument.Parse("{}");
        SettlementAsset[] assets = [new("Gold", "gold", false, 23)];
        var failedRepository = new SettlementRepository(intercepted, TimeProvider.System, metrics);
        await Assert.ThrowsAnyAsync<NpgsqlException>(() => failedRepository.SettleAsync(
            matchId, playerId, "Extracted", details.RootElement, assets, cancellationToken));
        Assert.True(proxy.DroppedCommittedResponse);
        Assert.Equal("Settled", await database.ScalarAsync<string>(
            "SELECT state FROM match_players WHERE match_id=$1 AND player_id=$2", matchId, playerId));

        // Recreate the repository as a process restart would, without relying
        // on coordinator memory or deleting any durable settlement state.
        var recovered = new SettlementRepository(database.DataSource, TimeProvider.System, metrics);
        var durable = await recovered.GetForMatchAsync(playerId, matchId, cancellationToken);
        Assert.Empty(await recovered.GetReadyNotificationsAsync(playerId, cancellationToken));
        var replay = await recovered.SettleAsync(matchId, playerId, "Extracted", details.RootElement, assets, cancellationToken);
        Assert.False(replay.Created);
        Assert.Equal(durable.SettlementId, replay.SettlementId);
        Assert.Equal(1, await recovered.CommitHoldsAsync(durable.SettlementId, cancellationToken));
        Assert.Equal(0, await recovered.CommitHoldsAsync(durable.SettlementId, cancellationToken));
        Assert.Equal(before + 23, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", playerId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", matchId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'", playerId));
        Assert.Equal(durable.SettlementId, Assert.Single(await recovered.GetReadyNotificationsAsync(playerId, cancellationToken)).SettlementId);
    }

    [Theory(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [InlineData(true)]
    [InlineData(false)]
    [Trait("Category", "PostgresIntegration")]
    public async Task Recovery_validates_durable_terminal_checkpoint_and_preserves_next_route(bool staleCheckpoint)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var playerId = await CreatePlayerAsync(database);
        var teammateId = await CreatePlayerAsync(database);
        var former = CreateRoom(Guid.NewGuid(), playerId, teammateId);
        var next = CreateRoom(Guid.NewGuid(), playerId);
        var formerMatch = Guid.NewGuid();
        var nextMatch = Guid.NewGuid();
        await InsertMatchAsync(database, formerMatch, former.RoomId, "Running", playerId, teammateId);
        await InsertMatchAsync(database, nextMatch, next.RoomId, "Running", playerId);
        using var metrics = new ServerMetrics();
        var time = new FixedTimeProvider(DateTimeOffset.UtcNow);
        var snapshots = new RoomSnapshotRepository(database.DataSource, time, metrics);
        var formerSnapshot = former.Capture();
        if (!staleCheckpoint)
            formerSnapshot = formerSnapshot with
            {
                Players = formerSnapshot.Players.Select(player => player.PlayerId == playerId
                    ? player with { Phase = RoomPlayerPhase.Extracted } : player).ToArray()
            };
        await snapshots.SaveIfDueAsync(formerSnapshot, cancellationToken);
        using var details = JsonDocument.Parse("{}");
        var settlements = new SettlementRepository(database.DataSource, time, metrics);
        await settlements.SettleAsync(
            formerMatch, playerId, "Extracted", details.RootElement, [], cancellationToken);
        time.Advance(TimeSpan.FromSeconds(1));
        await snapshots.SaveIfDueAsync(next.Capture(), cancellationToken);

        var state = new RoomRecoveryState();
        await using var rooms = new RoomRegistry(time, new SettlementCoordinator(settlements), snapshots);
        await new RoomRecoveryWorker(snapshots, rooms, state, time,
            NullLogger<RoomRecoveryWorker>.Instance).StartAsync(cancellationToken);
        Assert.Equal(!staleCheckpoint, state.Capture().IsHealthy);
        Assert.Equal(staleCheckpoint ? [former.RoomId] : [], state.Capture().FailedRoomIds);
        Assert.Equal(!staleCheckpoint, rooms.ContainsRoom(former.RoomId));
        if (!staleCheckpoint)
        {
            Assert.True(rooms.TryGetForPlayer(teammateId, out var teammate));
            Assert.Equal(former.RoomId, teammate!.RoomId);
            // Drain the former room's settlement observer and its route cleanup.
            await rooms.RemoveAsync(former.RoomId);
        }
        Assert.True(rooms.TryGetForPlayer(playerId, out var actor, out var matchId));
        Assert.Equal(next.RoomId, actor!.RoomId);
        Assert.Equal(nextMatch, matchId);
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", formerMatch));
    }

    private static readonly object CanonicalEvidenceGate = new();

    private static void RecordCanonicalLaunch(string fault, object actual)
    {
        var directory = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_PG_LAUNCH_EVIDENCE");
        if (string.IsNullOrWhiteSpace(directory))
            return;
        var sourceSha = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_SOURCE_SHA");
        var row = JsonSerializer.Serialize(new
        {
            schemaVersion = 1,
            sourceSha,
            fault,
            status = "Passed",
            scope = "Actual disposable PostgreSQL fixture and native coordinator/recovery; real player LIVE layer remains separate",
            actual
        });
        lock (CanonicalEvidenceGate)
        {
            Directory.CreateDirectory(directory);
            File.AppendAllText(Path.Combine(directory, "launch-receipts.jsonl"), row + Environment.NewLine);
        }
    }

    private static BattleRoom CreateRoom(Guid roomId, params Guid[] playerIds)
    {
        var room = new BattleRoom(roomId, "test", CombatCardCatalog.CreatePrototype(), 73);
        foreach (var playerId in playerIds)
            room.AddPlayer(new(playerId, HeroClass.Mage,
                Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));
        return room;
    }

    private static async Task<Guid> CreatePlayerAsync(PostgresTestSchema database)
    {
        var key = Guid.NewGuid().ToString("N");
        var now = DateTimeOffset.UtcNow;
        var player = await new IdentityRepository(database.DataSource, new PlayerProvisioningService())
            .SignInLocalAsync("lifecycle-" + key, "Lifecycle " + key[..8],
                SHA256.HashData(Encoding.UTF8.GetBytes(key)), now, now.AddHours(1), TestContext.Current.CancellationToken);
        return player.UserId;
    }

    private static async Task<(Guid PlayerId, PendingMatch Match)> PrepareReadyMatchAsync(
        PostgresTestSchema database, FixedTimeProvider time, MatchmakingRepository repository)
    {
        var cancellationToken = TestContext.Current.CancellationToken;
        var playerId = await CreatePlayerAsync(database);
        var progression = new ProgressionRepository(database.DataSource);
        var deck = Assert.Single(await progression.GetDecksAsync(playerId, cancellationToken),
            value => value.HeroClass == HeroClassDto.Mage);
        await database.InsertWornFeetAsync(playerId, HeroClass.Mage, cancellationToken);
        var loadout = await progression.GetLoadoutAsync(playerId, HeroClass.Mage, cancellationToken);
        await database.ExecuteAsync($"UPDATE player_consumables SET health_potion_count=2 WHERE player_id='{playerId:D}'");
        var prepared = await new PreparationRepository(database.DataSource, time).CreateAsync(playerId,
            "prepare-launch", new(HeroClassDto.Mage, deck.Version, loadout!.EquipmentIds,
                BackpackTierDto.Free, [], 2, "Standard"), cancellationToken);
        await repository.EnqueueAsync(playerId, "enqueue-launch",
            new(prepared.Preparation!.PreparationId), cancellationToken);
        time.Advance(TimeSpan.FromSeconds(31));
        var pending = Assert.IsType<PendingMatch>(await repository.TryCreateMatchAsync(cancellationToken));
        await repository.MarkReadyAsync(playerId, time.GetUtcNow(), cancellationToken);
        return (playerId, pending);
    }

    private static async Task InsertMatchAsync(PostgresTestSchema database, Guid matchId, Guid roomId, string status, params Guid[] playerIds)
    {
        await using var match = database.DataSource.CreateCommand(
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',73,'test',$3,CURRENT_TIMESTAMP)");
        match.Parameters.AddWithValue(matchId);
        match.Parameters.AddWithValue(roomId);
        match.Parameters.AddWithValue(status);
        await match.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
        foreach (var playerId in playerIds)
        {
            await using var player = database.DataSource.CreateCommand(
                "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')");
            player.Parameters.AddWithValue(matchId);
            player.Parameters.AddWithValue(playerId);
            await player.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
        }
    }

    private sealed class FixedTimeProvider(DateTimeOffset now) : TimeProvider
    {
        private DateTimeOffset _now = now;
        public override DateTimeOffset GetUtcNow() => _now;
        public void Advance(TimeSpan elapsed) => _now += elapsed;
    }

    // Read PostgreSQL frames, wait for ReadyForQuery after commit, and then
    // drop only the selected response. The database transaction is real.
    private sealed class CommitResponseDropProxy : IAsyncDisposable
    {
        private readonly Socket _listener = new(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
        private readonly CancellationTokenSource _shutdown = new();
        private readonly Task _acceptor;
        private readonly List<Task> _connections = [];
        private readonly EndPoint _upstream;
        private readonly string _statement;
        private int _armed = 1;
        private int _dropped;

        public CommitResponseDropProxy(string upstreamDirectory, int port, string statement = "UPDATE matches SET status='Running'")
        {
            SocketDirectory = Path.Combine(Path.GetTempPath(), "fc-launch-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(SocketDirectory);
            _upstream = upstreamDirectory.StartsWith('/')
                ? new UnixDomainSocketEndPoint(Path.Combine(upstreamDirectory, $".s.PGSQL.{port}"))
                : new DnsEndPoint(upstreamDirectory, port);
            _statement = statement;
            _listener.Bind(new UnixDomainSocketEndPoint(Path.Combine(SocketDirectory, $".s.PGSQL.{port}")));
            _listener.Listen(8);
            _acceptor = AcceptAsync();
        }

        public string SocketDirectory { get; }
        public bool DroppedCommittedResponse => Volatile.Read(ref _dropped) == 1;

        private async Task AcceptAsync()
        {
            try
            {
                while (!_shutdown.IsCancellationRequested)
                {
                    var client = await _listener.AcceptAsync(_shutdown.Token);
                    _connections.Add(RelayAsync(client));
                }
            }
            catch (OperationCanceledException) when (_shutdown.IsCancellationRequested) { }
        }

        private async Task RelayAsync(Socket client)
        {
            using (client)
            using (var server = _upstream is UnixDomainSocketEndPoint
                ? new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified)
                : new Socket(SocketType.Stream, ProtocolType.Tcp))
            {
                try
                {
                    if (_upstream is not UnixDomainSocketEndPoint) server.NoDelay = true;
                    await server.ConnectAsync(_upstream, _shutdown.Token);
                    await using var frontend = new NetworkStream(client, ownsSocket: false);
                    await using var backend = new NetworkStream(server, ownsSocket: false);
                    var startupLength = new byte[4];
                    await frontend.ReadExactlyAsync(startupLength, _shutdown.Token);
                    var startup = new byte[BinaryPrimitives.ReadInt32BigEndian(startupLength) - 4];
                    await frontend.ReadExactlyAsync(startup, _shutdown.Token);
                    await backend.WriteAsync(startupLength, _shutdown.Token);
                    await backend.WriteAsync(startup, _shutdown.Token);
                    var dropResponse = 0;
                    var request = ForwardAsync(frontend, backend, inspectRequest: true);
                    var response = ForwardAsync(backend, frontend, inspectRequest: false);
                    await Task.WhenAny(request, response);
                    client.Close();
                    server.Close();
                    await Task.WhenAll(request, response);

                    async Task ForwardAsync(Stream source, Stream destination, bool inspectRequest)
                    {
                        var header = new byte[5];
                        while (true)
                        {
                            await source.ReadExactlyAsync(header, _shutdown.Token);
                            var payload = new byte[BinaryPrimitives.ReadInt32BigEndian(header.AsSpan(1)) - 4];
                            await source.ReadExactlyAsync(payload, _shutdown.Token);
                            if (inspectRequest && (header[0] == 'P' || header[0] == 'Q') &&
                                Encoding.UTF8.GetString(payload).Split('\0').Any(part =>
                                    part.TrimStart().StartsWith(_statement, StringComparison.Ordinal)) &&
                                Interlocked.Exchange(ref _armed, 0) == 1)
                                Volatile.Write(ref dropResponse, 1);
                            if (!inspectRequest && Volatile.Read(ref dropResponse) == 1 && header[0] == 'C')
                            {
                                // Connector reset traffic may still have an Idle Z queued
                                // when the next Parse is observed. Only the selected command's
                                // completion can arm the following durable Idle boundary.
                                var completed = Encoding.UTF8.GetString(payload).TrimEnd('\0');
                                if (completed == (_statement == "COMMIT" ? "COMMIT" : "UPDATE 1"))
                                    Volatile.Write(ref dropResponse, 2);
                            }
                            if (!inspectRequest && Volatile.Read(ref dropResponse) == 2)
                            {
                                if (header[0] == 'Z')
                                {
                                    if (payload[0] == 'I') Interlocked.Exchange(ref _dropped, 1);
                                    return;
                                }
                                continue;
                            }
                            await destination.WriteAsync(header, _shutdown.Token);
                            await destination.WriteAsync(payload, _shutdown.Token);
                        }
                    }
                }
                catch (Exception exception) when (exception is IOException or SocketException or OperationCanceledException or ObjectDisposedException) { }
            }
        }

        public async ValueTask DisposeAsync()
        {
            await _shutdown.CancelAsync();
            await _acceptor;
            await Task.WhenAll(_connections);
            _listener.Dispose();
            _shutdown.Dispose();
            Directory.Delete(SocketDirectory, recursive: true);
        }
    }
}
