using System.Globalization;
using System.Net;
using System.Net.WebSockets;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Config;
using FantasyCard.Server.Tests.Persistence;
using Npgsql;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    [Fact(Skip = "Requires an owned local PostgreSQL database.", SkipUnless = nameof(HasPrivateDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Full_host_actual17_preparation_READY_and_active_credit_resume_after_abrupt_restart_without_player_casts()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: false);
        Record("SEASON17-schema", new { schema = new NpgsqlConnectionStringBuilder(db.ConnectionString).SearchPath, scope = "new17 actual entry and process recovery" });
        await db.MigrateAsync(); using var deadline = Deadline(90); var ct = deadline.Token;
        var config = GameConfigCatalog.Current;
        var season = SeasonDefinition.FromCalendarDays("process-actual17", DateOnly.FromDateTime(DateTime.UtcNow).AddDays(-7), config.Version, "season-equipment-v1", highestOpenDifficulty:5);
        await new SeasonRepository(db.DataSource, TimeProvider.System).PublishAsync(season, config.ContentHash, ct, config);
        var port = ReservePort(); using var client = Client(port); var sockets = new List<ClientWebSocket>();
        var players = new List<(Guid Id,string Token)>(); var matchId = Guid.Empty; var roomId = Guid.Empty; int firstPid;
        using var metrics = new ServerMetrics(); var snapshots = new RoomSnapshotRepository(db.DataSource,TimeProvider.System,metrics);
        var first = FullHost.Start(db.ConnectionString,port,"season17-actual-entry-before");
        try
        {
            firstPid = first.ProcessId; await first.WaitForHealthAsync(client,"/health/ready",HttpStatusCode.OK,ct);
            for(var i=0;i<4;i++)
            {
                client.DefaultRequestHeaders.Authorization=null;
                var login=Wire.LocalSignInResponse.Parser.ParseFrom(await CallAsync(client,HttpMethod.Post,"/api/v1/auth/local",
                    new Wire.LocalSignInRequest{DeviceId=Guid.NewGuid().ToString("N"),DisplayName="Season17 entry "+i},ct));
                players.Add((Guid.Parse(login.Player.UserId),login.AccessToken));
                client.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",login.AccessToken);
                var bootstrap=Wire.BootstrapResponse.Parser.ParseFrom(await CallAsync(client,HttpMethod.Get,"/api/v1/bootstrap",null,ct));
                var deck=bootstrap.Decks.Single(d=>d.HeroClass=="Mage");
                var loadout=Wire.LoadoutResponse.Parser.ParseFrom(await CallAsync(client,HttpMethod.Get,"/api/v1/loadouts/Mage",null,ct));
                var request=new Wire.CreatePreparationRequest{HeroClass="Mage",DeckVersion=deck.Version,BackpackTier="Free",Difficulty="D0",SeasonId=season.SeasonId,LootPreferenceElement="Water"};
                request.EquipmentIds.Add(loadout.EquipmentIds);
                var preparation=Wire.PreparationResponse.Parser.ParseFrom(await CallAsync(client,HttpMethod.Post,"/api/v1/preparations",request,ct));
                Assert.Equal(config.Version,preparation.Snapshot.ConfigVersion);
                sockets.Add(await ConnectAsync(client,port,ct));
                await CallAsync(client,HttpMethod.Post,"/api/v1/matches/enqueue",new Wire.EnqueueMatchRequest{PreparationId=preparation.PreparationId},ct);
            }
            for(var i=0;i<4;i++)
            {
                var ready=Assert.IsType<RoomReadyRequiredEventPayload>((await EventAsync(sockets[i],"room.ready_required",ct)).Payload);
                if(i==0){matchId=ready.MatchId;roomId=ready.RoomId;}
                Assert.Equal(matchId,ready.MatchId);Assert.Equal(4,ready.RequiredPlayers);
                Assert.IsType<RoomReadyAcceptedEventPayload>((await CommandAsync(sockets[i],new("room.ready","season17-ready-"+i,null,new RoomReadyCommandPayload()),ct,"room.ready_accepted")).Payload);
            }
            for(var i=0;i<4;i++)
            {
                var started=Assert.IsType<RoomStartedEventPayload>((await EventAsync(sockets[i],"room.started",ct)).Payload);
                Assert.Equal(roomId,started.RoomId);Assert.Equal(matchId,started.MatchId);
                var actual=await SnapshotAsync(sockets[i],ct);Assert.Equal(players[i].Id,actual.Player.PlayerId);
                Assert.Equal("SeasonRateBudgetedRhythm",actual.Player.NumericalState!.FenxianPolicy);Assert.Equal(500,actual.Player.NumericalState.FenxianReturnRateBasisPoints);
                Assert.Equal(season.SeasonId,actual.Season!.SeasonId);Assert.Equal("Water",await db.ScalarAsync<string>("SELECT snapshot_json->>'lootPreferenceElement' FROM preparations WHERE preparation_id=(SELECT preparation_id FROM match_players WHERE match_id=$1 AND player_id=$2)",matchId,players[i].Id));
                Record("SEASON17-entry-wire",new{actual,scope="Actual PB login/bootstrap/preparation/enqueue/READY; no player combat commands"});
            }
            await WaitAsync(async()=> (await snapshots.GetAsync(roomId,ct))!.Players.All(p=>p.Combat.FenxianReturnCredit>0),ct);
            Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM match_players WHERE match_id=$1 AND is_bot",matchId));
            await first.KillAsync();
        }
        finally
        {
            await first.DisposeAsync();foreach(var socket in sockets)socket.Dispose();
        }
        var durable=(await snapshots.GetAsync(roomId,ct))!;Assert.All(durable.Players,p=>Assert.Equal(0,p.LastCombatActionSequence));
        await using var second=FullHost.Start(db.ConnectionString,port,"season17-actual-entry-after");Assert.NotEqual(firstPid,second.ProcessId);
        await second.WaitForHealthAsync(client,"/health/ready",HttpStatusCode.OK,ct);
        foreach(var player in players)
        {
            client.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",player.Token);
            using var socket=await ConnectAsync(client,port,ct);var actual=await SnapshotAsync(socket,ct);
            var before=durable.Players.Single(p=>p.PlayerId==player.Id);var credit=double.Parse(actual.Player.NumericalState!.FenxianReturnCredit!,CultureInfo.InvariantCulture);
            Assert.Equal(matchId,actual.MatchId);Assert.Equal(roomId,actual.RoomId);Assert.Equal(config.Version,actual.ConfigVersion);Assert.Equal(500,actual.Player.NumericalState.FenxianReturnRateBasisPoints);
            Assert.True(actual.Player.Combat.Hp>0);Assert.InRange(credit,before.Combat.FenxianReturnCredit!.Value,2);
            Record("SEASON17-active-recovered-wire",new{actual,previousCredit=before.Combat.FenxianReturnCredit,firstPid,secondPid=second.ProcessId});
        }
        var after=(await snapshots.GetAsync(roomId,ct))!;Assert.All(after.Players,p=>Assert.Equal(0,p.LastCombatActionSequence));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM matches"));Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements"));
        Record("SEASON17-real-entry-restart",new{firstPid,secondPid=second.ProcessId,matchId,roomId,players=4,bots=0,successfulPlayerCasts=0,completedEncounters=0,
            scope="Four protocol-controlled account entry routes; not native capacity, combat efficiency, B05 expansion or settlement acceptance"});
    }

    [Theory(Skip = "Requires an owned local PostgreSQL database.", SkipUnless = nameof(HasPrivateDatabase))]
    [Trait("Category", "PostgresIntegration")]
    [InlineData("valid")]
    [InlineData("missing")]
    [InlineData("corrupt")]
    public async Task Full_host_original16_and_current17_credit_survive_abrupt_restart_and_bad_archive_isolation(string archiveState)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: false);
        Record("SEASON17-schema", new { schema = new NpgsqlConnectionStringBuilder(db.ConnectionString).SearchPath, archiveState });
        await db.MigrateAsync();
        using var deadline = Deadline(90); var ct = deadline.Token;
        using var archive = new ConfigArchiveDirectory();
        var originalBytes = File.ReadAllBytes(FindOriginal16());
        var original = GameConfigCatalog.Load(originalBytes); var current = GameConfigCatalog.Current;
        Assert.Equal("season-v1-config-16", original.Version); Assert.Equal("season-v1-config-17", current.Version);
        PublishedConfigTestInputs.Store(archive.Root, original.Version, originalBytes, original.ContentHash);
        var today = DateOnly.FromDateTime(DateTime.UtcNow);
        var oldSeason = SeasonDefinition.FromCalendarDays("process-original16", today.AddDays(-49), original.Version, "season-equipment-v1", highestOpenDifficulty: 5);
        var newSeason = SeasonDefinition.FromCalendarDays("process-current17", today.AddDays(-7), current.Version, "season-equipment-v1", highestOpenDifficulty: 5);
        var seasons = new SeasonRepository(db.DataSource, TimeProvider.System);
        await seasons.PublishAsync(oldSeason, original.ContentHash, ct, original);
        await seasons.PublishAsync(newSeason, current.ContentHash, ct, current);
        var oldPlayer = await SeedPlayerAsync(db, "Original16 credit", ct);
        var newPlayer = await SeedPlayerAsync(db, "Current17 credit", ct);
        var old = await SeedSeasonCreditRoom(db, original, oldSeason, oldPlayer.Id, null, ct);
        var next = await SeedSeasonCreditRoom(db, current, newSeason, newPlayer.Id, .75, ct);
        using var metrics = new ServerMetrics(); var snapshots = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        await snapshots.SaveIfDueAsync(old.Room.Capture(), ct); await snapshots.SaveIfDueAsync(next.Room.Capture(), ct);
        var ledgerBefore = await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger");
        // An ended season legitimately acquires archived_at and a new metadata
        // version. Compare every financial column separately from that transition.
        const string walletQuery = "SELECT jsonb_build_object('wallets',(SELECT jsonb_agg(to_jsonb(w) ORDER BY player_id) FROM player_wallets w),'materials',(SELECT jsonb_agg(to_jsonb(m) ORDER BY player_id) FROM player_materials m),'season',(SELECT jsonb_agg(to_jsonb(s)-'archived_at'-'version' ORDER BY player_id,season_id) FROM player_season_wallets s))::text";
        var walletsBefore = await db.ScalarAsync<string>(walletQuery);
        var port = ReservePort(); using var oldClient = Client(port, oldPlayer.Token); using var newClient = Client(port, newPlayer.Token);
        int firstPid;
        await using (var first = FullHost.Start(db.ConnectionString, port, "season17-" + archiveState + "-before", configArchiveDirectory: archive.Root))
        {
            firstPid = first.ProcessId;
            await first.WaitForHealthAsync(newClient, "/health/ready", HttpStatusCode.OK, ct);
            using var oldSocket = await ConnectAsync(oldClient, port, ct);
            using var newSocket = await ConnectAsync(newClient, port, ct);
            AssertCredit(await SnapshotAsync(oldSocket, ct), old.Room.Capture(), old.Match, null);
            AssertCredit(await SnapshotAsync(newSocket, ct), next.Room.Capture(), next.Match, .75);
            // Keep both sockets live until the OS process is gone. No graceful
            // disconnect checkpoint or expiry is substituted for abrupt death.
            await first.KillAsync();
        }
        var durableOld = await snapshots.GetAsync(old.Room.RoomId, ct); var durableNew = await snapshots.GetAsync(next.Room.RoomId, ct);
        Assert.NotNull(durableOld); Assert.NotNull(durableNew);
        var rawOld = await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", old.Room.RoomId);
        var originalPath = Path.Combine(archive.Root, original.Version, "fantasycard.config.bytes");
        if (archiveState == "missing") File.Delete(originalPath);
        if (archiveState == "corrupt") { var bytes = File.ReadAllBytes(originalPath); bytes[^1] ^= 1; File.WriteAllBytes(originalPath, bytes); }
        int secondPid;
        await using (var second = FullHost.Start(db.ConnectionString, port, "season17-" + archiveState + "-after", configArchiveDirectory: archive.Root))
        {
            secondPid = second.ProcessId; Assert.NotEqual(firstPid, secondPid);
            await second.WaitForHealthAsync(newClient, "/health/ready", archiveState == "valid" ? HttpStatusCode.OK : HttpStatusCode.ServiceUnavailable, ct);
            using var newSocket = await ConnectAsync(newClient, port, ct);
            AssertCredit(await SnapshotAsync(newSocket, ct), durableNew, next.Match, .75);
            if (archiveState == "valid")
            {
                using var oldSocket = await ConnectAsync(oldClient, port, ct);
                AssertCredit(await SnapshotAsync(oldSocket, ct), durableOld, old.Match, null);
            }
            else
            {
                Assert.Equal(rawOld, await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", old.Room.RoomId));
                Assert.Contains(old.Room.RoomId.ToString(), second.CapturedOutput, StringComparison.OrdinalIgnoreCase);
            }
            var savedSnapshot = (await snapshots.GetAsync(next.Room.RoomId, ct))!;
            Assert.Equal(durableNew.RandomStreams, savedSnapshot.RandomStreams);
            var saved = Assert.Single(savedSnapshot.Players);
            Assert.Equal(.75, saved.Combat.FenxianReturnCredit); Assert.Equal(500, saved.Combat.FenxianReturnRateBasisPoints);
            Assert.Equal("Running", await db.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", old.Match));
            Assert.Equal("Running", await db.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", next.Match));
            Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements"));
            Assert.Equal(ledgerBefore, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger"));
            Assert.Equal(walletsBefore, await db.ScalarAsync<string>(walletQuery));
            Assert.True(await db.ScalarAsync<bool>("SELECT archived_at IS NOT NULL FROM player_season_wallets WHERE player_id=$1 AND season_id=$2", oldPlayer.Id, oldSeason.SeasonId));
        }
        Record("SEASON17-credit-restart", new { archiveState, firstPid, secondPid, originalVersion = original.Version, currentVersion = current.Version,
            oldRoom = old.Room.RoomId, newRoom = next.Room.RoomId, credit = .75, rateBasisPoints = 500, originalPolicy = "SeasonBoundedRhythm",
            newPolicy = "SeasonRateBudgetedRhythm", newMatchesSimulated = 0, newB05Encounters = 0, newD03Encounters = 0,
            checkpointScope = "Declared idle ActionBar checkpoints; no battle actions or full entry/settlement acceptance", rawOldAfterFirstKillSha256 = Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(rawOld))).ToLowerInvariant() });
    }

    private static void AssertCredit(RoomSnapshotEventPayload actual, BattleRoomSnapshot expected, Guid match, double? credit)
    {
        var player = Assert.Single(expected.Players);
        Assert.Equal(expected.RoomId, actual.RoomId); Assert.Equal(match, actual.MatchId); Assert.Equal(expected.ConfigVersion, actual.ConfigVersion);
        Assert.Equal(expected.Season!.SeasonId, actual.Season!.SeasonId); Assert.Equal("ActionBar", actual.Player.Phase);
        Assert.Equal(player.Combat.Deck.Hand.Select(c => c.InstanceId), actual.Player.Hand.Select(c => c.InstanceId));
        Assert.Equal(player.Combat.Deck.Library.Count, actual.Player.LibraryCount);
        var numerical = actual.Player.NumericalState!;
        Assert.Equal(credit is null ? "SeasonBoundedRhythm" : "SeasonRateBudgetedRhythm", numerical.FenxianPolicy);
        Assert.Equal(credit?.ToString("R", CultureInfo.InvariantCulture), numerical.FenxianReturnCredit);
        Assert.Equal(credit is null ? (int?)null : 500, numerical.FenxianReturnRateBasisPoints);
        Assert.Equal(70, actual.Player.Combat.MaximumHp); Assert.Equal(player.Combat.Hp, actual.Player.Combat.Hp);
        Record("SEASON17-wire-snapshot", new { actual, expectedCredit = credit, scope = "Real ticket-WebSocket binary snapshot, idle checkpoint" });
    }

    private static async Task<(Guid Match, BattleRoom Room)> SeedSeasonCreditRoom(PostgresTestSchema db, GameConfigCatalog config, SeasonDefinition season, Guid player, double? credit, CancellationToken ct)
    {
        var match = Guid.NewGuid(); var catalog = CombatCardCatalog.Create(config);
        var clock = new SeasonCheckpointClock(season.StartsAtUtc.AddMinutes(1));
        var deckVersion = await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2", player);
        var preparation = await new PreparationRepository(db.DataSource, clock, configurations: new PublishedConfigCatalogs(config)).CreateAsync(player,
            "season-credit-preparation", new(HeroClassDto.Mage, deckVersion, [null,null,null,null,null], BackpackTierDto.Free, [], 0, "D0", season.SeasonId, LootPreferenceElement: "Water"), ct);
        Assert.Equal(CreatePreparationStatus.Created, preparation.Status);
        var source = preparation.Preparation!.Snapshot;
        var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, 73, season: season.ContextFor(0));
        room.AddPlayer(new(player, HeroClass.Mage, source.CardIds, null, WeaponLevel:source.ClassWeaponLevel, CardLevels:source.CardLevels,
            LootPreferenceElement:source.LootPreferenceElement, BorrowedTemplateId:source.BorrowedTemplateId));
        room.InitializeMap(ChaosMapGenerator.Generate(73, 1));
        var snapshot = room.Capture(); var position = snapshot.Map!.Cells.First(c => c.HasEvacuation).Position;
        var self = Assert.Single(snapshot.Players);
        room = BattleRoom.Restore(snapshot with { Players = [self with { Position = position, Phase = RoomPlayerPhase.ActionBar, Pve = null,
            ClearedCells = [position], Combat = self.Combat with { FenxianReturnCredit = credit } }] }, catalog, 73);
        await SqlAsync(db, """
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm','D0',73,$3,'Running',$4,$5,'season-v1','season-equipment-v1')
            """, ct, match, room.RoomId, config.Version, season.StartsAtUtc.AddMinutes(1), season.SeasonId);
        await SqlAsync(db, "INSERT INTO match_players(match_id,player_id,preparation_id,is_bot,state) VALUES($1,$2,$3,false,'Active')", ct, match, player, preparation.Preparation.PreparationId);
        await SqlAsync(db, "UPDATE preparations SET status='Matched' WHERE preparation_id=$1", ct, preparation.Preparation.PreparationId);
        return (match, room);
    }

    private sealed class SeasonCheckpointClock(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }

    private static string FindOriginal16()
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
        {
            var path = Path.Combine(directory.FullName, "server/config/archive/season-v1-config-16/fantasycard.config.bytes");
            if (File.Exists(path)) return path;
        }
        throw new FileNotFoundException("Pinned original16 archive required.");
    }
}
