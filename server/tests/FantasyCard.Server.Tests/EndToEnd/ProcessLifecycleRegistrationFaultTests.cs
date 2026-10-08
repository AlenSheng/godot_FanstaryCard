using System.Buffers.Binary;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Tests.Persistence;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    [Fact(Skip = "Requires an owned local PostgreSQL database.", SkipUnless = nameof(HasPrivateDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Full_host_MarkRunning_committed_response_loss_recovers_one_room_and_actual_client_routes()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        using var deadline = Deadline(90);
        var ct = deadline.Token;
        var settings = new NpgsqlConnectionStringBuilder(database.ConnectionString);
        await using var proxy = new RegistrationCommitProxy(settings.Host!, settings.Port);
        settings.Host = proxy.SocketDirectory;
        settings.SslMode = SslMode.Disable;
        var port = ReservePort();
        using var client = Client(port);
        var players = new List<(Guid Id, string Token)>();
        var tickets = new List<Guid>();
        var sockets = new List<ClientWebSocket>();
        var matchId = Guid.Empty;
        var roomId = Guid.Empty;
        Guid equipmentId = Guid.Empty;
        var host = FullHost.Start(settings.ConnectionString, port, "register-committed-loss");
        try
        {
            await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            for (var index = 0; index < 4; index++)
            {
                client.DefaultRequestHeaders.Authorization = null;
                var login = Wire.LocalSignInResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Post,
                    "/api/v1/auth/local", new Wire.LocalSignInRequest
                    { DeviceId = Guid.NewGuid().ToString("N"), DisplayName = $"Register Fault {index}" }, ct));
                players.Add((Guid.Parse(login.Player.UserId), login.AccessToken));
            }
            // Supply belongs only to this disposable schema. Preparation,
            // enqueue, READY and routing all use the real production endpoints.
            equipmentId = await database.InsertWornFeetAsync(players[0].Id, HeroClass.Priest, ct);
            await SqlAsync(database, "UPDATE player_consumables SET health_potion_count=2 WHERE player_id=$1", ct, players[0].Id);
            foreach (var player in players)
            {
                client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", player.Token);
                var bootstrap = Wire.BootstrapResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, "/api/v1/bootstrap", null, ct));
                Assert.Null(bootstrap.UnfinishedMatch);
                var deck = bootstrap.Decks.First(value => value.HeroClass == "Priest");
                var loadout = Wire.LoadoutResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, "/api/v1/loadouts/Priest", null, ct));
                var request = new Wire.CreatePreparationRequest
                { HeroClass = "Priest", DeckVersion = deck.Version, BackpackTier = "Free", Difficulty = "Standard", PotionCount = player.Id == players[0].Id ? 2 : 0 };
                request.EquipmentIds.Add(loadout.EquipmentIds);
                var preparation = Wire.PreparationResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Post, "/api/v1/preparations", request, ct));
                sockets.Add(await ConnectAsync(client, port, ct));
                var ticket = Wire.MatchTicketResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Post, "/api/v1/matches/enqueue",
                    new Wire.EnqueueMatchRequest { PreparationId = preparation.PreparationId }, ct));
                tickets.Add(Guid.Parse(ticket.TicketId));
            }
            for (var index = 0; index < sockets.Count; index++)
            {
                var required = Assert.IsType<RoomReadyRequiredEventPayload>((await EventAsync(sockets[index], "room.ready_required", ct)).Payload);
                if (index == 0) { matchId = required.MatchId; roomId = required.RoomId; }
                Assert.Equal(matchId, required.MatchId);
                Assert.Equal(roomId, required.RoomId);
                Assert.Equal(4, required.RequiredPlayers);
                var accepted = await CommandAsync(sockets[index], new ClientCommand("room.ready", $"register-ready-{index}", null,
                    new RoomReadyCommandPayload()), ct, "room.ready_accepted");
                Assert.IsType<RoomReadyAcceptedEventPayload>(accepted.Payload);
            }
            await WaitAsync(() => Task.FromResult(proxy.Attempts.Any(attempt => attempt.Dropped)), ct);
            var dropped = Assert.Single(proxy.Attempts, attempt => attempt.Dropped);
            Assert.Equal("UPDATE 1", dropped.CommandTag);
            Assert.Equal("I", dropped.ReadyState);
            Assert.Equal("Running", await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", matchId));
            Record("LOAD-04.4-T02-MarkRunning-committed-response-lost", new
            { host.ProcessId, matchId, roomId, dropped, durableStatus = "Running", responseDelivered = false });

            for (var index = 0; index < sockets.Count; index++)
            {
                var started = Assert.IsType<RoomStartedEventPayload>((await EventAsync(sockets[index], "room.started", ct)).Payload);
                Assert.Equal(matchId, started.MatchId);
                Assert.Equal(roomId, started.RoomId);
                var snapshot = await SnapshotAsync(sockets[index], ct);
                Assert.Equal(matchId, snapshot.MatchId);
                Assert.Equal(roomId, snapshot.RoomId);
                Assert.Equal(players[index].Id, snapshot.Player.PlayerId);
                client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", players[index].Token);
                var ticket = Wire.MatchTicketResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get,
                    $"/api/v1/matches/tickets/{tickets[index]:D}", null, ct));
                Assert.Equal(matchId.ToString("D"), ticket.MatchId);
                Assert.Equal("Matched", ticket.Status);
            }
            var attempts = proxy.Attempts.ToArray();
            Record("LOAD-04.4-T02-MarkRunning-observed-operations", new { host.ProcessId, matchId, roomId, attempts });
            Assert.Equal(2, attempts.Length);
            Assert.Equal("UPDATE 0", attempts[1].CommandTag);
            Assert.False(attempts[1].Dropped);
            Assert.Empty(proxy.Errors);
            Assert.Contains("Ready-match launch iteration failed.", host.CapturedOutput, StringComparison.Ordinal);
            await AssertRegistrationDatabaseAsync(database, matchId, roomId, players[0].Id, equipmentId);
            Record("LOAD-04.4-T02-MarkRunning-recovered", new
            { host.ProcessId, matchId, roomId, players = players.Select(player => player.Id), tickets, attempts,
                expected = "same durable match/room, all four actual PB ticket-WS routes; one equipment reservation and potion debit",
                actual = "matched", scope = "FullProgram OFFLINE+POSTGRES using protocol clients; production Godot, LIVE and three gameplay cycles remain separate" });
        }
        finally
        {
            await host.DisposeAsync();
            foreach (var socket in sockets) socket.Dispose();
        }
        // A second real OS process consumes the same durable initial snapshot.
        // Reconnect promptly within the unchanged 15-second grace period.
        await using var restarted = FullHost.Start(database.ConnectionString, port, "register-committed-loss-restart");
        Assert.NotEqual(host.ProcessId, restarted.ProcessId);
        await restarted.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
        foreach (var player in players)
        {
            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", player.Token);
            using var socket = await ConnectAsync(client, port, ct);
            var snapshot = await SnapshotAsync(socket, ct);
            Assert.Equal(matchId, snapshot.MatchId);
            Assert.Equal(roomId, snapshot.RoomId);
            Assert.Equal(player.Id, snapshot.Player.PlayerId);
        }
        await AssertRegistrationDatabaseAsync(database, matchId, roomId, players[0].Id, equipmentId);
        Record("LOAD-04.4-T02-MarkRunning-process-restart", new
        { previousPid = host.ProcessId, restarted.ProcessId, matchId, roomId, expected = "same four authoritative routes and once-only reservation after actual OS restart", actual = "matched" });
    }

    private static async Task AssertRegistrationDatabaseAsync(PostgresTestSchema database, Guid matchId, Guid roomId, Guid playerId, Guid equipmentId)
    {
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM matches"));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(DISTINCT room_id) FROM matches"));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM room_snapshots"));
        Assert.Equal(roomId, await database.ScalarAsync<Guid>("SELECT room_id FROM matches WHERE match_id=$1", matchId));
        Assert.Equal("Running", await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", matchId));
        Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM match_players WHERE match_id=$1 AND is_bot=false AND state='Active'", matchId));
        Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE status='Matched'"));
        Assert.Equal(0, await database.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", playerId));
        Assert.Equal("InMatchEquipped", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1 AND request_id=$2 AND reason='match.start'", equipmentId, matchId.ToString("D")));
    }

    [Theory(Skip = "Requires an owned local PostgreSQL database.", SkipUnless = nameof(HasPrivateDatabase))]
    [InlineData("player-route")]
    [InlineData("room-id")]
    [Trait("Category", "PostgresIntegration")]
    public async Task SupportOnly_actual_Register_conflict_retries_same_launch_without_partial_room_or_second_reservation(string conflict)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(30);
        var ct = deadline.Token;
        var time = new RegistrationTime(DateTimeOffset.UtcNow);
        using var metrics = new ServerMetrics();
        var repository = new MatchmakingRepository(database.DataSource, time, metrics);
        var player = await SeedPlayerAsync(database, "Registry " + Guid.NewGuid().ToString("N")[..8], ct);
        var equipmentId = await database.InsertWornFeetAsync(player.Id, HeroClass.Mage, ct);
        await SqlAsync(database, "UPDATE player_consumables SET health_potion_count=2 WHERE player_id=$1", ct, player.Id);
        var progression = new ProgressionRepository(database.DataSource);
        var deck = Assert.Single(await progression.GetDecksAsync(player.Id, ct), value => value.HeroClass == HeroClassDto.Mage);
        var loadout = await progression.GetLoadoutAsync(player.Id, HeroClass.Mage, ct);
        var preparation = await new PreparationRepository(database.DataSource, time).CreateAsync(player.Id, "register-preparation",
            new(HeroClassDto.Mage, deck.Version, loadout!.EquipmentIds, BackpackTierDto.Free, [], 2, "Standard"), ct);
        await repository.EnqueueAsync(player.Id, "register-enqueue", new(preparation.Preparation!.PreparationId), ct);
        time.Advance(TimeSpan.FromSeconds(31));
        var pending = Assert.IsType<PendingMatch>(await repository.TryCreateMatchAsync(ct));
        await repository.MarkReadyAsync(player.Id, time.GetUtcNow(), ct);
        var snapshots = new RoomSnapshotRepository(database.DataSource, time, metrics);
        await using var rooms = new RoomRegistry(time);
        var conflictingId = conflict == "room-id" ? pending.RoomId : Guid.NewGuid();
        var occupantId = conflict == "player-route" ? player.Id : Guid.NewGuid();
        var occupied = new BattleRoom(conflictingId, "test", CombatCardCatalog.CreatePrototype(), 73);
        occupied.AddPlayer(new(occupantId, HeroClass.Mage, Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));
        var original = rooms.Register(occupied, startTicker: false);
        using var coordinator = new RoomReadyCoordinator(repository, rooms, snapshots, new RealtimeEventStore(time),
            new ConnectionRegistry(), time, NullLogger<RoomReadyCoordinator>.Instance, metrics);
        // Repeat the actual Register rejection before removing the conflicting
        // actor. No fake exception or alternate Registry implementation is used.
        for (var attempt = 0; attempt < 2; attempt++)
        {
            var error = await Assert.ThrowsAsync<InvalidOperationException>(() => coordinator.ProcessNextAsync(time.GetUtcNow(), ct));
            Assert.Contains(conflict == "room-id" ? "already registered" : "already assigned", error.Message, StringComparison.Ordinal);
            Assert.Equal("Launching", await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", pending.MatchId));
            Assert.Equal(conflictingId, Assert.Single(rooms.GetRoomIds()));
            Assert.True(rooms.TryGetForPlayer(occupantId, out var unchanged));
            Assert.Same(original, unchanged);
            if (conflict == "room-id") Assert.False(rooms.TryGetForPlayer(player.Id, out _));
            Record("LOAD-04.4-T02-Register-failure-" + conflict, new
            { attempt = attempt + 1, pending.MatchId, pending.RoomId, conflictingId, registeredRooms = rooms.GetRoomIds(), error = error.Message, scope = "SupportOnly: actual component + PG; no full Program process" });
        }
        Assert.True(await rooms.RemoveAsync(conflictingId));
        Assert.False(rooms.TryGetForPlayer(occupantId, out _));
        Assert.True(await coordinator.ProcessNextAsync(time.GetUtcNow(), ct));
        Assert.Equal(pending.RoomId, Assert.Single(rooms.GetRoomIds()));
        Assert.True(rooms.TryGetForPlayer(player.Id, out var actor, out var matchId));
        Assert.Equal(pending.RoomId, actor!.RoomId);
        Assert.Equal(pending.MatchId, matchId);
        Assert.False(await coordinator.ProcessNextAsync(time.GetUtcNow(), ct));
        Assert.Equal("Running", await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", pending.MatchId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM matches"));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM room_snapshots"));
        Assert.Equal(0, await database.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", player.Id));
        Assert.Equal("InMatchEquipped", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1 AND reason='match.start'", equipmentId));
        Record("LOAD-04.4-T02-Register-recovered-" + conflict, new
        { pending.MatchId, pending.RoomId, registeredRooms = rooms.GetRoomIds(), expected = "one room/route after repeated real Register failures; one asset reservation", actual = "matched", scope = "SupportOnly OFFLINE+POSTGRES" });
    }

    private sealed class RegistrationTime(DateTimeOffset now) : TimeProvider
    {
        private DateTimeOffset _now = now;
        public override DateTimeOffset GetUtcNow() => _now;
        public void Advance(TimeSpan duration) => _now += duration;
    }

    private sealed record RegistrationCommitAttempt(int Index, string StatementSha256, string? CommandTag,
        string ReadyState, bool Dropped, DateTimeOffset CommittedAt);

    // Observe real PostgreSQL extended/simple protocol frames. The selected
    // UPDATE response is withheld through idle ReadyForQuery, then the socket
    // is closed. Neither database result nor HTTP/WS payload is synthesized.
    private sealed class RegistrationCommitProxy : IAsyncDisposable
    {
        private const string Statement = "UPDATE matches SET status='Running'";
        private readonly Socket _listener = new(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
        private readonly CancellationTokenSource _shutdown = new();
        private readonly Task _acceptor;
        private readonly List<Task> _connections = [];
        private readonly EndPoint _upstream;
        private readonly AddressFamily _upstreamFamily;
        private int _attemptIndex;
        public string SocketDirectory { get; }
        public ConcurrentQueue<RegistrationCommitAttempt> Attempts { get; } = new();
        public ConcurrentQueue<string> Errors { get; } = new();

        public RegistrationCommitProxy(string upstreamHost, int port)
        {
            Assert.True(IsLocalDatabase(upstreamHost), "Fault relay accepts only an owned Unix socket or loopback PostgreSQL service.");
            SocketDirectory = Path.Combine(Path.GetTempPath(), "fc-register-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(SocketDirectory);
            if (upstreamHost.StartsWith('/'))
            {
                _upstream = new UnixDomainSocketEndPoint(Path.Combine(upstreamHost, $".s.PGSQL.{port}"));
                _upstreamFamily = AddressFamily.Unix;
            }
            else
            {
                var address = string.Equals(upstreamHost, "localhost", StringComparison.OrdinalIgnoreCase)
                    ? IPAddress.Loopback : IPAddress.Parse(upstreamHost);
                Assert.True(IPAddress.IsLoopback(address));
                _upstream = new IPEndPoint(address, port);
                _upstreamFamily = address.AddressFamily;
            }
            _listener.Bind(new UnixDomainSocketEndPoint(Path.Combine(SocketDirectory, $".s.PGSQL.{port}")));
            _listener.Listen(40);
            _acceptor = AcceptAsync();
        }

        private async Task AcceptAsync()
        {
            try
            {
                while (!_shutdown.IsCancellationRequested)
                    _connections.Add(RelayAsync(await _listener.AcceptAsync(_shutdown.Token)));
            }
            catch (OperationCanceledException) when (_shutdown.IsCancellationRequested) { }
        }

        private async Task RelayAsync(Socket client)
        {
            using (client)
            using (var server = new Socket(_upstreamFamily, SocketType.Stream, ProtocolType.Unspecified))
            {
                try
                {
                    // The relay writes frame headers and payloads separately.
                    // Match Npgsql's TCP_NODELAY so that this test transport
                    // does not add a delayed-ACK pause to every SQL message.
                    if (_upstreamFamily != AddressFamily.Unix) server.NoDelay = true;
                    await server.ConnectAsync(_upstream, _shutdown.Token);
                    await using var frontend = new NetworkStream(client, ownsSocket: false);
                    await using var backend = new NetworkStream(server, ownsSocket: false);
                    var startupLength = new byte[4];
                    await frontend.ReadExactlyAsync(startupLength, _shutdown.Token);
                    var length = BinaryPrimitives.ReadInt32BigEndian(startupLength);
                    if (length is < 8 or > 65536) throw new InvalidDataException("Invalid PG startup length.");
                    var startup = new byte[length - 4];
                    await frontend.ReadExactlyAsync(startup, _shutdown.Token);
                    await backend.WriteAsync(startupLength, _shutdown.Token);
                    await backend.WriteAsync(startup, _shutdown.Token);
                    RegistrationSelectedCommand? selected = null;
                    var request = ForwardAsync(frontend, backend, inspectRequest: true);
                    var response = ForwardAsync(backend, frontend, inspectRequest: false);
                    await Task.WhenAny(request, response);
                    client.Close(); server.Close();
                    await Task.WhenAll(request, response);

                    async Task ForwardAsync(Stream source, Stream destination, bool inspectRequest)
                    {
                        var header = new byte[5];
                        while (true)
                        {
                            await source.ReadExactlyAsync(header, _shutdown.Token);
                            var payloadLength = BinaryPrimitives.ReadInt32BigEndian(header.AsSpan(1)) - 4;
                            if (payloadLength is < 0 or > 16 * 1024 * 1024) throw new InvalidDataException("Invalid PG frame length.");
                            var payload = new byte[payloadLength];
                            await source.ReadExactlyAsync(payload, _shutdown.Token);
                            if (inspectRequest && header[0] is (byte)'P' or (byte)'Q')
                            {
                                var sql = Encoding.UTF8.GetString(payload).Split('\0').FirstOrDefault(part => part.TrimStart().StartsWith(Statement, StringComparison.Ordinal));
                                if (sql is not null)
                                {
                                    var index = Interlocked.Increment(ref _attemptIndex);
                                    Volatile.Write(ref selected, new RegistrationSelectedCommand(index,
                                        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(sql))), index == 1));
                                }
                            }
                            var current = Volatile.Read(ref selected);
                            if (!inspectRequest && current is not null)
                            {
                                if (header[0] == 'C')
                                {
                                    var tag = Encoding.UTF8.GetString(payload).TrimEnd('\0');
                                    if (tag.StartsWith("UPDATE ", StringComparison.Ordinal)) current.CommandTag = tag;
                                }
                                // Npgsql can prepend a pool reset to the next
                                // command. Its DISCARD ALL/SET CommandComplete
                                // and idle ReadyForQuery precede our UPDATE.
                                if (header[0] == 'Z' && current.CommandTag is not null)
                                {
                                    Attempts.Enqueue(new(current.Index, current.StatementSha256, current.CommandTag,
                                        Encoding.ASCII.GetString(payload), current.Dropped, DateTimeOffset.UtcNow));
                                    Volatile.Write(ref selected, null);
                                    if (current.Dropped) return;
                                }
                                if (current.Dropped) continue;
                            }
                            await destination.WriteAsync(header, _shutdown.Token);
                            await destination.WriteAsync(payload, _shutdown.Token);
                        }
                    }
                }
                catch (Exception exception) when (exception is IOException or SocketException or OperationCanceledException or ObjectDisposedException) { }
                catch (Exception exception) { Errors.Enqueue(exception.ToString()); }
            }
        }

        public async ValueTask DisposeAsync()
        {
            await _shutdown.CancelAsync();
            await _acceptor;
            await Task.WhenAll(_connections);
            _listener.Dispose(); _shutdown.Dispose();
            Directory.Delete(SocketDirectory, recursive: true);
        }

        private sealed class RegistrationSelectedCommand(int index, string statementSha256, bool dropped)
        {
            public int Index { get; } = index;
            public string StatementSha256 { get; } = statementSha256;
            public bool Dropped { get; } = dropped;
            public string? CommandTag { get; set; }
        }
    }
}
