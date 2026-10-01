using System.Buffers.Binary;
using System.Collections.Concurrent;
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

public sealed class PostgresLifecycleRecoveryTests(ITestOutputHelper output)
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

    [Theory(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [InlineData(false)]
    [InlineData(true)]
    [Trait("Category", "PostgresIntegration")]
    public async Task MarkRunning_commit_response_loss_retries_same_room_and_restart_restores_it(bool forcePriorIdle)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var time = new FixedTimeProvider(DateTimeOffset.UtcNow);
        using var metrics = new ServerMetrics();
        var settings = new NpgsqlConnectionStringBuilder(database.ConnectionString);
        await using var proxy = new CommitResponseDropProxy(settings.Host!, settings.Port, forcePriorIdle: forcePriorIdle);
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
            output.WriteLine(JsonSerializer.Serialize(proxy.ProtocolTrace));
            Assert.True(proxy.DroppedCommittedResponse);
            Assert.Equal("UPDATE 1", proxy.DroppedCommandTag);
            if (forcePriorIdle) Assert.True(proxy.PriorIdleCompleted);
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
        output.WriteLine(JsonSerializer.Serialize(new
        {
            completed = "same-room-retry-and-restart", forcePriorIdle, pending.MatchId, pending.RoomId,
            uniqueRoomAndInventoryMovementVerified = true
        }));
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
        Assert.Equal("COMMIT", proxy.DroppedCommandTag);
        output.WriteLine(JsonSerializer.Serialize(proxy.ProtocolTrace));
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

    // Query/Sync responses are ordered cycles. A pooled DISCARD ALL can precede
    // the target Parse in the same write; its idle ReadyForQuery is not proof
    // that the target committed. Drop only the target cycle after its own
    // CommandComplete and idle ReadyForQuery. The database transaction is real.
    private sealed class CommitResponseDropProxy : IAsyncDisposable
    {
        private readonly Socket _listener = new(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
        private readonly CancellationTokenSource _shutdown = new();
        private readonly Task _acceptor;
        private readonly List<Task> _connections = [];
        private readonly EndPoint _upstream;
        private readonly string _statement;
        private readonly string _expectedTag;
        private readonly bool _forcePriorIdle;
        private readonly ConcurrentQueue<string> _trace = new();
        private int _armed = 1;
        private int _dropped;
        private int _connectionId;
        private int _priorIdleCompleted;
        private string? _droppedCommandTag;

        public CommitResponseDropProxy(string upstreamDirectory, int port, string statement = "UPDATE matches SET status='Running'", bool forcePriorIdle = false)
        {
            SocketDirectory = Path.Combine(Path.GetTempPath(), "fc-launch-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(SocketDirectory);
            _upstream = upstreamDirectory.StartsWith('/')
                ? new UnixDomainSocketEndPoint(Path.Combine(upstreamDirectory, $".s.PGSQL.{port}"))
                : new DnsEndPoint(upstreamDirectory, port);
            _statement = statement;
            _expectedTag = statement == "COMMIT" ? "COMMIT" : "UPDATE 1";
            _forcePriorIdle = forcePriorIdle;
            _listener.Bind(new UnixDomainSocketEndPoint(Path.Combine(SocketDirectory, $".s.PGSQL.{port}")));
            _listener.Listen(8);
            _acceptor = AcceptAsync();
        }

        public string SocketDirectory { get; }
        public bool DroppedCommittedResponse => Volatile.Read(ref _dropped) == 1;
        public string[] ProtocolTrace => _trace.ToArray();
        public string? DroppedCommandTag => _droppedCommandTag;
        public bool PriorIdleCompleted => Volatile.Read(ref _priorIdleCompleted) == 1;

        private sealed class ResponseCycle(int id, bool probe = false)
        {
            public int Id { get; } = id;
            public bool Probe { get; } = probe;
            public bool Target { get; set; }
            public bool Failed { get; set; }
            public List<string> CommandTags { get; } = [];
            public List<(byte[] Header, byte[] Payload)> Buffered { get; } = [];
            public TaskCompletionSource Completion { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        }

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
                using var connectionShutdown = CancellationTokenSource.CreateLinkedTokenSource(_shutdown.Token);
                var cancellationToken = connectionShutdown.Token;
                try
                {
                    await server.ConnectAsync(_upstream, cancellationToken);
                    await using var frontend = new NetworkStream(client, ownsSocket: false);
                    await using var backend = new NetworkStream(server, ownsSocket: false);
                    var startupLength = new byte[4];
                    await frontend.ReadExactlyAsync(startupLength, cancellationToken);
                    var startup = new byte[BinaryPrimitives.ReadInt32BigEndian(startupLength) - 4];
                    await frontend.ReadExactlyAsync(startup, cancellationToken);
                    var connection = Interlocked.Increment(ref _connectionId);
                    var cycles = new ConcurrentQueue<ResponseCycle>();
                    cycles.Enqueue(new ResponseCycle(0));
                    await backend.WriteAsync(startupLength, cancellationToken);
                    await backend.WriteAsync(startup, cancellationToken);
                    var nextCycle = 0;
                    ResponseCycle? extendedCycle = null;
                    var request = ForwardRequestsAsync();
                    var response = ForwardResponsesAsync();
                    await Task.WhenAny(request, response);
                    await connectionShutdown.CancelAsync();
                    client.Close();
                    server.Close();
                    await Task.WhenAll(request, response);

                    async Task ForwardRequestsAsync()
                    {
                        var header = new byte[5];
                        while (true)
                        {
                            await frontend.ReadExactlyAsync(header, cancellationToken);
                            var payload = new byte[BinaryPrimitives.ReadInt32BigEndian(header.AsSpan(1)) - 4];
                            await frontend.ReadExactlyAsync(payload, cancellationToken);
                            var target = (header[0] == 'P' || header[0] == 'Q') &&
                                Encoding.UTF8.GetString(payload).Split('\0').Any(part =>
                                    part.TrimStart().StartsWith(_statement, StringComparison.Ordinal)) &&
                                Interlocked.Exchange(ref _armed, 0) == 1;
                            if (target && _forcePriorIdle)
                            {
                                if (extendedCycle is not null)
                                    throw new InvalidOperationException("Prior-idle probe must precede the target extended cycle.");
                                var priorIdle = new ResponseCycle(++nextCycle, probe: true);
                                cycles.Enqueue(priorIdle);
                                var probe = Encoding.UTF8.GetBytes("SELECT 1\0");
                                var probeHeader = new byte[5];
                                probeHeader[0] = (byte)'Q';
                                BinaryPrimitives.WriteInt32BigEndian(probeHeader.AsSpan(1), probe.Length + 4);
                                Trace(priorIdle, "request-Q:prior-idle-probe-before-target");
                                await backend.WriteAsync(probeHeader, cancellationToken);
                                await backend.WriteAsync(probe, cancellationToken);
                                await priorIdle.Completion.Task.WaitAsync(cancellationToken);
                            }

                            ResponseCycle? cycle = null;
                            if (header[0] == 'Q')
                            {
                                cycle = new ResponseCycle(++nextCycle);
                                cycles.Enqueue(cycle);
                            }
                            else if (header[0] is (byte)'P' or (byte)'B' or (byte)'D' or (byte)'E' or (byte)'C' or (byte)'H' or (byte)'S')
                            {
                                if (extendedCycle is null)
                                {
                                    extendedCycle = new ResponseCycle(++nextCycle);
                                    cycles.Enqueue(extendedCycle);
                                }
                                cycle = extendedCycle;
                                if (header[0] == 'S') extendedCycle = null;
                            }
                            if (cycle is not null)
                            {
                                if (target) cycle.Target = true;
                                Trace(cycle, "request-" + (char)header[0] + (target ? ":target-forwarded" : ""));
                            }
                            await backend.WriteAsync(header, cancellationToken);
                            await backend.WriteAsync(payload, cancellationToken);
                        }
                    }

                    async Task ForwardResponsesAsync()
                    {
                        var header = new byte[5];
                        while (true)
                        {
                            await backend.ReadExactlyAsync(header, cancellationToken);
                            var payload = new byte[BinaryPrimitives.ReadInt32BigEndian(header.AsSpan(1)) - 4];
                            await backend.ReadExactlyAsync(payload, cancellationToken);
                            if (!cycles.TryPeek(out var cycle))
                                throw new InvalidOperationException("Backend response has no matching request cycle.");
                            if (header[0] == 'C')
                            {
                                var tag = Encoding.UTF8.GetString(payload).TrimEnd('\0');
                                cycle.CommandTags.Add(tag);
                                Trace(cycle, "response-C:" + tag);
                            }
                            if (header[0] == 'E') cycle.Failed = true;
                            if (cycle.Target) cycle.Buffered.Add((header.ToArray(), payload));
                            if (header[0] == 'Z')
                            {
                                Trace(cycle, "response-Z:" + (char)payload[0]);
                                if (!cycles.TryDequeue(out var completed) || !ReferenceEquals(completed, cycle))
                                    throw new InvalidOperationException("PostgreSQL response cycle order changed.");
                                if (cycle.Probe)
                                {
                                    if (cycle.Failed || payload[0] != 'I' || !cycle.CommandTags.SequenceEqual(["SELECT 1"]))
                                        throw new InvalidOperationException("Prior-idle probe did not complete normally.");
                                    Interlocked.Exchange(ref _priorIdleCompleted, 1);
                                    cycle.Completion.TrySetResult();
                                }
                                else if (cycle.Target)
                                {
                                    if (!cycle.Failed && payload[0] == 'I' && cycle.CommandTags.SequenceEqual([_expectedTag]))
                                    {
                                        _droppedCommandTag = _expectedTag;
                                        Trace(cycle, "drop-confirmed-target-committed");
                                        Interlocked.Exchange(ref _dropped, 1);
                                        return;
                                    }
                                    // Preserve an unexpected database result; do not claim
                                    // that a failed or still-open transaction committed.
                                    foreach (var frame in cycle.Buffered)
                                    {
                                        await frontend.WriteAsync(frame.Header, cancellationToken);
                                        await frontend.WriteAsync(frame.Payload, cancellationToken);
                                    }
                                }
                            }
                            if (!cycle.Target && !cycle.Probe)
                            {
                                await frontend.WriteAsync(header, cancellationToken);
                                await frontend.WriteAsync(payload, cancellationToken);
                            }
                        }
                    }

                    void Trace(ResponseCycle cycle, string message) =>
                        _trace.Enqueue($"connection={connection},cycle={cycle.Id},target={cycle.Target},probe={cycle.Probe},{message}");
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
