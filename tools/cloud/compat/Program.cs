using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Persistence;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

return await Probe.RunAsync(args);

static class Probe
{
    static readonly JsonSerializerOptions Json = new()
    { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, Converters = { new JsonStringEnumConverter() } };
    static NpgsqlDataSource Db = null!;
    static FrozenClock Clock = null!;
    static ServerMetrics Metrics = null!;
    static JsonObject Fixture = new();
    static readonly Dictionary<string, object?> Evidence = new();
    static readonly CancellationTokenSource Deadline = new(TimeSpan.FromSeconds(90));
    static CancellationToken Ct => Deadline.Token;
    static Guid Id(string name) => Guid.Parse(Fixture[name]!.GetValue<string>());
    static void Put(string name, Guid id) => Fixture[name] = id.ToString("D");
    static void Require(bool condition, string message)
    { if (!condition) throw new InvalidOperationException(message); }
    static string Hash(object? value) => Convert.ToHexString(SHA256.HashData(
        Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value, Json)))).ToLowerInvariant();

    public static async Task<int> RunAsync(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("action and fixture file required");
        var connection = Environment.GetEnvironmentVariable("FANTASYCARD_COMPAT_POSTGRES")
            ?? throw new InvalidOperationException("Private fixture connection missing");
        var settings = new NpgsqlConnectionStringBuilder(connection);
        Require(settings.Host!.StartsWith("/workspace/") || settings.Host.StartsWith("/tmp/"), "Only private Unix socket allowed");
        Require(settings.Database!.StartsWith("fc_compat_") && settings.SearchPath!.StartsWith("fc_compat_"), "Only owned fixture database/schema allowed");
        Fixture = File.Exists(args[1]) ? JsonNode.Parse(await File.ReadAllTextAsync(args[1], Ct))!.AsObject() : new();
        Clock = new(Fixture["clock"] is JsonValue clock ? DateTimeOffset.Parse(clock.GetValue<string>()) : DateTimeOffset.Parse("2026-09-30T18:00:00Z"));
        using var metrics = new ServerMetrics(); Metrics = metrics;
        await using var db = NpgsqlDataSource.Create(connection); Db = db;
        Evidence["action"] = args[0];
        Evidence["version"] = Environment.GetEnvironmentVariable("FANTASYCARD_COMPAT_VERSION");
        Evidence["fixture_schema"] = settings.SearchPath;
        try
        {
            await new DatabaseMigrator(Db, NullLogger<DatabaseMigrator>.Instance).StartAsync(Ct);
            switch (args[0])
            {
                case "migrate": break;
                case "seed-checkpoint": await SeedRoomAsync(complex: true); break;
                case "roundtrip": await RoundtripAsync(); break;
                case "seed-launch": await SeedLaunchAsync(); break;
                case "claim-drop": await ClaimDropAsync(); break;
                case "mark-drop": await MarkDropAsync(); break;
                case "launch-retry": await LaunchRetryAsync(); break;
                case "mark-replay": await MarkReplayAsync(); break;
                case "recover": await RecoverAsync(); break;
                case "seed-terminal": await SeedRoomAsync(); await InstallFaultAsync(); break;
                case "terminal-fail": await TerminalFailAsync(); break;
                case "seed-stale": await SeedRoomAsync(); await SettlePrimaryAsync(); break;
                case "seed-stale-next": await SeedRoomAsync(); await SettlePrimaryAsync(); await SeedNextAsync(); break;
                case "seed-settlement": await SeedRoomAsync(single: true); break;
                case "settlement-drop": await SettlementDropAsync(); break;
                case "settlement-replay": await SettlementReplayAsync(); break;
                case "seed-pending": await SeedPendingAsync(); break;
                case "seed-drain-stale": await SeedRoomAsync(single: true); await SettlePrimaryAsync(); break;
                case "seed-drain-missing": await SeedRoomAsync(single: true, persistCheckpoint: false); await SettlePrimaryAsync(); break;
                case "seed-drain-receipt-state": await SeedReceiptMismatchAsync(false); break;
                case "seed-drain-receipt-pointer": await SeedReceiptMismatchAsync(true); break;
                case "seed-drain-consistent": await SeedConsistentSettlementAsync(); break;
                case "seed-drain-orphan-receipt": await SeedOrphanReceiptAsync(); break;
                case "seed-drain-orphan-member": await SeedOrphanMemberAsync(); break;
                case "seed-drain-wrong-hold-owner": await SeedWrongHoldOwnerAsync(); break;
                case "drain": await DrainAsync(); break;
                default: throw new ArgumentException("Unknown action");
            }
            Evidence["migration_rows"] = JsonNode.Parse(await ScalarAsync<string>("SELECT jsonb_agg(jsonb_build_object('version',version,'name',name,'checksum',checksum) ORDER BY version)::text FROM schema_migrations"));
            Evidence["app_ddl_hash"] = await DdlHashAsync();
            Fixture["clock"] = Clock.GetUtcNow().ToString("O");
            await File.WriteAllTextAsync(args[1], Fixture.ToJsonString(Json), Ct);
            Evidence["probe_completed"] = true;
            Console.WriteLine(JsonSerializer.Serialize(Evidence, Json));
            return 0;
        }
        catch (Exception error)
        {
            Evidence["probe_completed"] = false;
            Evidence["error_type"] = error.GetType().Name;
            Evidence["error"] = error.Message;
            Console.WriteLine(JsonSerializer.Serialize(Evidence, Json));
            Console.Error.WriteLine(error);
            return 1;
        }
    }

    static RoomSnapshotRepository Snapshots() => new(Db, Clock, Metrics);
    static SettlementRepository Settlements(NpgsqlDataSource? db = null) => new(db ?? Db, Clock, Metrics);
    static MatchmakingRepository Matches(NpgsqlDataSource? db = null) => new(db ?? Db, Clock, Metrics);
    static async Task<T> ScalarAsync<T>(string sql, params object[] values)
    {
        await using var command = Db.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        return (T)(await command.ExecuteScalarAsync(Ct) ?? throw new InvalidOperationException("No scalar"));
    }
    static async Task ExecuteAsync(string sql, params object[] values)
    {
        await using var command = Db.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(Ct);
    }
    static async Task<Guid> PlayerAsync()
    {
        var fixtureId = Guid.NewGuid().ToString("N");
        var player = await new IdentityRepository(Db, new PlayerProvisioningService()).SignInLocalAsync(
            "compat-fixture-" + fixtureId, "CF-" + fixtureId[..12], SHA256.HashData(Encoding.UTF8.GetBytes(fixtureId)),
            Clock.GetUtcNow(), Clock.GetUtcNow().AddHours(1), Ct);
        return player.UserId;
    }
    static BattleRoom Room(Guid room, params Guid[] players)
    {
        var result = new BattleRoom(room, "compat-fixture-config", CombatCardCatalog.CreatePrototype(), 73, GameConfigCatalog.Current.Numerics);
        foreach (var player in players)
            result.AddPlayer(new(player, HeroClass.Mage, Enumerable.Range(1,20).Select(x=>$"common-{x:D2}").ToArray(), null));
        return result;
    }
    static async Task MatchAsync(Guid match, Guid room, params Guid[] players)
    {
        await ExecuteAsync("INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',73,'compat-fixture-config','Running',$3)", match, room, Clock.GetUtcNow());
        foreach (var player in players)
            await ExecuteAsync("INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')", match, player);
    }
    static async Task SeedRoomAsync(bool complex = false, bool single = false, bool persistCheckpoint = true)
    {
        Put("player", await PlayerAsync()); Put("teammate", await PlayerAsync()); Put("room", Guid.NewGuid()); Put("match", Guid.NewGuid());
        var players = single ? new[] { Id("player") } : new[] { Id("player"), Id("teammate") };
        var room = Room(Id("room"), players);
        var snapshot = room.Capture();
        if (complex)
        {
            Put("equipment", Guid.NewGuid()); Put("relic_equipment", Guid.NewGuid());
            foreach (var (equipment, owner) in new[] { (Id("equipment"), Id("player")), (Id("relic_equipment"), Id("teammate")) })
                await ExecuteAsync("INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,effect_affix,secondary_trait) VALUES($1,$2,'Feet','White',0,false,'InMatchEquipped',1,$3,'Fire',NULL,'DrawInterval')", equipment, owner, Clock.GetUtcNow());
            var gear = new ExplorationItem(Id("equipment").ToString("D"), ExplorationItemKind.Equipment, Equipment: new("Feet","White","Fire",null,"DrawInterval"));
            var relicGear = gear with { ItemId = Id("relic_equipment").ToString("D") };
            var backpack = GameConfigCatalog.Current.Backpacks.Single(b=>b.Id=="Free");
            room = new BattleRoom(Id("room"), "compat-fixture-config", CombatCardCatalog.CreatePrototype(), 73, GameConfigCatalog.Current.Numerics);
            foreach (var (player, armor) in new[] { (Id("player"), gear), (Id("teammate"), relicGear) })
                room.AddPlayer(new(player, HeroClass.Mage, Enumerable.Range(1,20).Select(x=>$"common-{x:D2}").ToArray(), null,
                    InventoryCapacity: backpack.Capacity, SafeSlots: backpack.SafeSlots, WornArmor: [armor]));
            room.InitializeMap(ChaosMapGenerator.Generate(73, 2));
            Require(room.GetPlayer(Id("player")).Inventory.TryAdd(new("preserved-gold",ExplorationItemKind.Gold,42)), "fixture player inventory");
            Require(room.GetPlayer(Id("teammate")).Inventory.TryAdd(new("relic-gold",ExplorationItemKind.Gold,17)), "fixture victim inventory");
            room.AbandonBattle(Id("teammate")); // Actual domain death creates a distinct victim's relic; no duplicated gear IDs.
            snapshot = room.Capture() with { Revision = 11 };
            Require(snapshot.Players.Single(p=>p.PlayerId==Id("teammate")).Phase == RoomPlayerPhase.Dead, "fixture victim must be terminal");
            Require(snapshot.RelicPiles!.Single().Items.Any(i=>i.ItemId==relicGear.ItemId), "domain relic missing victim equipment");
            Fixture["components"] = JsonSerializer.SerializeToNode(Components(snapshot),Json);
            Fixture["revision"] = snapshot.Revision;
        }
        await MatchAsync(Id("match"),Id("room"),players);
        if (persistCheckpoint) await Snapshots().SaveIfDueAsync(snapshot,Ct);
        if (complex)
        {
            await new SettlementCoordinator(Settlements(),Clock).ObserveAsync(Id("match"),snapshot);
            var receipt = await Settlements().GetForMatchAsync(Id("teammate"),Id("match"),Ct);
            Require(await Settlements().CommitHoldsAsync(receipt.SettlementId,Ct)==1, "fixture death equipment must commit once");
        }
        Fixture["initial_gold"] = await ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1",Id("player"));
        Evidence["seeded"] = true;
    }
    static Dictionary<string,string> Components(BattleRoomSnapshot s) => new()
    { ["rng"] = Hash(new { s.RandomState,s.RandomStreams }), ["configuration"] = Hash(new {s.ConfigVersion,s.Numerics}), ["players"] = Hash(s.Players), ["equipment_and_relics"] = Hash(new{s.RelicPiles,worn=s.Players.Select(p=>p.WornArmor)}) };
    static async Task RoundtripAsync()
    {
        var snapshots = Snapshots(); var s = await snapshots.GetAsync(Id("room"),Ct) ?? throw new InvalidOperationException("checkpoint missing");
        Require(s.Revision==Fixture["revision"]!.GetValue<long>(),"checkpoint revision changed");
        var restored = BattleRoom.Restore(s,CombatCardCatalog.CreatePrototype(),73).Capture();
        Require(Hash(Components(restored))==Hash(Fixture["components"]!.Deserialize<Dictionary<string,string>>(Json)),"RNG/configuration/player/equipment/relic changed");
        restored = restored with { Revision=restored.Revision+10 }; // Force a fresh-version write, retain all state components.
        await snapshots.SaveIfDueAsync(restored,Ct);
        Fixture["revision"]=restored.Revision;
        Evidence["checkpoint_revision"]=restored.Revision; Evidence["components"]=Components(restored);
        Evidence["equipment_location"]=await ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",Id("equipment"));
        Require((string)Evidence["equipment_location"]! == "InMatchEquipped","persisted equipment changed");
        Evidence["relic_equipment_location"]=await ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",Id("relic_equipment"));
        Require((string)Evidence["relic_equipment_location"]! == "RelicPile", "persisted relic equipment changed");
        Evidence["victim_state"]=await ScalarAsync<string>("SELECT state FROM match_players WHERE match_id=$1 AND player_id=$2",Id("match"),Id("teammate"));
        Require((string)Evidence["victim_state"]! == "Settled", "terminal victim must remain settled");
    }
    static async Task SeedLaunchAsync()
    {
        Put("player",await PlayerAsync()); var player=Id("player"); var progression=new ProgressionRepository(Db);
        var deck=(await progression.GetDecksAsync(player,Ct)).Single(d=>d.HeroClass==HeroClassDto.Mage);
        Put("equipment",Guid.NewGuid());
        await ExecuteAsync("INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,effect_affix,secondary_trait) VALUES($1,$2,'Feet','White',0,false,'Equipped',1,$3,'Fire',NULL,'DrawInterval')",Id("equipment"),player,Clock.GetUtcNow());
        await ExecuteAsync("UPDATE player_loadouts SET feet_id=$1,version=version+1 WHERE player_id=$2 AND hero_class=$3",Id("equipment"),player,(short)HeroClass.Mage);
        await ExecuteAsync("UPDATE player_consumables SET health_potion_count=2 WHERE player_id=$1",player);
        var loadout=await progression.GetLoadoutAsync(player,HeroClass.Mage,Ct);
        var prepared=await new PreparationRepository(Db,Clock).CreateAsync(player,"compat-prepare",new(HeroClassDto.Mage,deck.Version,loadout!.EquipmentIds,BackpackTierDto.Free,[],2,"Standard"),Ct);
        await Matches().EnqueueAsync(player,"compat-enqueue",new(prepared.Preparation!.PreparationId),Ct);
        Clock.Advance(TimeSpan.FromSeconds(31)); var pending=await Matches().TryCreateMatchAsync(Ct) ?? throw new InvalidOperationException("match missing");
        Put("match",pending.MatchId); Put("room",pending.RoomId); await Matches().MarkReadyAsync(player,Clock.GetUtcNow(),Ct);
        Evidence["match_status"]=await StatusAsync();
    }
    static Task<string> StatusAsync()=>ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1",Id("match"));
    static async Task AssetsOnceAsync()
    {
        var movements=await ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE request_id=$1 AND reason='match.start'",Id("match").ToString("D"));
        var potions=await ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1",Id("player"));
        Require(movements==1 && potions==0,"asset reservation was duplicated or missing");
        Evidence["asset_reservation_count"]=movements;Evidence["potions_remaining"]=potions;
    }
    static async Task ClaimDropAsync()
    {
        await using var proxy=Proxy("COMMIT"); await using var intercepted=Intercepted(proxy); var failed=false;
        try { await Matches(intercepted).ClaimReadyMatchAsync(Clock.GetUtcNow(),Ct); } catch(NpgsqlException){failed=true;}
        Require(failed && proxy.DroppedCommittedResponse,"launch commit response not actually dropped");
        Require(await StatusAsync()=="Launching","Launching commit not durable"); await AssetsOnceAsync();
        Evidence["committed_response_dropped"]=true; Evidence["match_status"]=await StatusAsync();
    }
    static async Task MarkDropAsync()
    {
        await using var proxy=Proxy("UPDATE matches SET status='Running'");await using var intercepted=Intercepted(proxy);
        await using var rooms=new RoomRegistry(Clock); using var ready=new RoomReadyCoordinator(Matches(intercepted),rooms,Snapshots(),new RealtimeEventStore(Clock),new ConnectionRegistry(),Clock,NullLogger<RoomReadyCoordinator>.Instance);
        var failed=false;try{await ready.ProcessNextAsync(Clock.GetUtcNow(),Ct);}catch(NpgsqlException){failed=true;}
        Require(failed && proxy.DroppedCommittedResponse && await StatusAsync()=="Running","MarkRunning commit loss not injected");
        Require(!rooms.ContainsRoom(Id("room")),"uncertain registration not cleaned");await AssetsOnceAsync();
        Evidence["committed_response_dropped"]=true;Evidence["match_status"]=await StatusAsync();
    }
    static async Task LaunchRetryAsync()
    {
        await using var rooms=new RoomRegistry(Clock);using var ready=new RoomReadyCoordinator(Matches(),rooms,Snapshots(),new RealtimeEventStore(Clock),new ConnectionRegistry(),Clock,NullLogger<RoomReadyCoordinator>.Instance);
        Require(await ready.ProcessNextAsync(Clock.GetUtcNow(),Ct),"launch not retried");
        Require(await StatusAsync()=="Running" && rooms.TryGetForPlayer(Id("player"),out var actor) && actor!.RoomId==Id("room"),"same room not launched");
        await AssetsOnceAsync();Evidence["match_status"]=await StatusAsync();
    }
    static async Task MarkReplayAsync()
    {
        var accepted=true;try{await Matches().MarkRunningAsync(Id("match"),Ct);}catch(InvalidOperationException){accepted=false;}
        Evidence["committed_running_replay_accepted"]=accepted;Evidence["match_status"]=await StatusAsync();
        await AssetsOnceAsync();
    }
    static async Task RecoverAsync()
    {
        var state=new RoomRecoveryState();await using var rooms=new RoomRegistry(Clock);
        await new RoomRecoveryWorker(Snapshots(),rooms,state,Clock,NullLogger<RoomRecoveryWorker>.Instance).StartAsync(Ct);
        var routed=rooms.TryGetForPlayer(Id("player"),out var actor,out var match);
        Evidence["recovery_healthy"]=state.Capture().IsHealthy;
        Evidence["failed_room_ids"]=state.Capture().FailedRoomIds;
        Evidence["registered_room_ids"]=rooms.GetRoomIds();
        Evidence["primary_route_room"]=routed ? actor!.RoomId : null;
        Evidence["primary_route_match"]=routed ? match : null;
        Evidence["ready_http_status"]=await ReadyHttpAsync(state);
        if(routed)Evidence["primary_recovered_phase"]=(await actor!.ExecuteAsync(new GetRoomSnapshotCommand(),Ct)).Players.Single(p=>p.PlayerId==Id("player")).Phase;
        if(Fixture["next_room"] is not null)Evidence["expected_next_room"]=Id("next_room");
        Evidence["durable_player_state"]=await ScalarAsync<string>("SELECT state FROM match_players WHERE match_id=$1 AND player_id=$2",Id("match"),Id("player"));
        if(await ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='match.start' AND request_id=$1",Id("match").ToString("D"))>0)await AssetsOnceAsync();
    }
    static async Task<int> ReadyHttpAsync(RoomRecoveryState state)
    {
        var builder=WebApplication.CreateBuilder();builder.Logging.ClearProviders();
        builder.Services.AddSingleton(state);builder.Services.AddHealthChecks().AddCheck<RoomRecoveryHealthCheck>("room-recovery");
        await using var app=builder.Build();app.Urls.Add("http://127.0.0.1:0");app.MapHealthChecks("/health/ready");await app.StartAsync(Ct);
        using var http=new HttpClient{Timeout=TimeSpan.FromSeconds(10)};var response=await http.GetAsync(app.Urls.Single()+"/health/ready",Ct);await app.StopAsync(Ct);
        return (int)response.StatusCode;
    }
    static async Task InstallFaultAsync()=>await ExecuteAsync("CREATE FUNCTION compat_fail_terminal() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'compatibility fixture terminal checkpoint failure'; END $$; CREATE TRIGGER compat_fail_checkpoint BEFORE UPDATE ON room_snapshots FOR EACH ROW EXECUTE FUNCTION compat_fail_terminal();");
    static async Task TerminalFailAsync()
    {
        var snapshots=Snapshots();var s=await snapshots.GetAsync(Id("room"),Ct) ?? throw new InvalidOperationException("snapshot missing");var persistence=new RoomPersistenceState();
        await using(var rooms=new RoomRegistry(Clock,new SettlementCoordinator(Settlements(),Clock),snapshots,persistence))
        {
            var actor=rooms.Register(BattleRoom.Restore(s,CombatCardCatalog.CreatePrototype(),73),Id("match"),startTicker:false);
            await actor.ExecuteAsync(new SetPlayerConnectionCommand(Id("player"),Connected:false),Ct);
            await actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromSeconds(16),Clock.GetUtcNow()),Ct);
            var terminal=await actor.ExecuteAsync(new GetRoomSnapshotCommand(),Ct);
            Evidence["memory_phase"]=terminal.Players.Single(p=>p.PlayerId==Id("player")).Phase;
            for(var attempt=0;attempt<100 && persistence.CaptureFailures().Count==0;attempt++)await Task.Delay(10,Ct);
            Evidence["snapshot_failure_observed"]=persistence.CaptureFailures().Contains(Id("room"));
        }
        Evidence["durable_player_state"]=await ScalarAsync<string>("SELECT state FROM match_players WHERE match_id=$1 AND player_id=$2",Id("match"),Id("player"));
        Evidence["settlements"]=await ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1",Id("match"));
        Evidence["durable_snapshot_phase"]=(await snapshots.GetAsync(Id("room"),Ct))!.Players.Single(p=>p.PlayerId==Id("player")).Phase;
    }
    static async Task SettlePrimaryAsync(bool gold=false)
    {
        using var details=JsonDocument.Parse("{}");var receipt=await Settlements().SettleAsync(Id("match"),Id("player"),"Extracted",details.RootElement,gold ? [new("Gold","gold",false,23)] : [],Ct);
        Put("receipt",receipt.SettlementId);Evidence["receipt"]=receipt.SettlementId;
    }
    static async Task SeedPendingAsync()
    {
        await SeedRoomAsync(single: true); await SettlePrimaryAsync(gold: true);
        // Construct a consistent completed extraction checkpoint before the
        // read-only drain probe. Pending gold is the only remaining blocker.
        var snapshot = await Snapshots().GetAsync(Id("room"),Ct) ?? throw new InvalidOperationException("fixture checkpoint missing");
        snapshot = snapshot with { Revision = snapshot.Revision + 10,
            Players = snapshot.Players.Select(p=>p with { Phase = RoomPlayerPhase.Extracted }).ToArray() };
        await Snapshots().SaveIfDueAsync(snapshot,Ct);
    }
    static async Task SeedReceiptMismatchAsync(bool retainSettledState)
    {
        await SeedRoomAsync(single: true); await SettlePrimaryAsync();
        var snapshot = await Snapshots().GetAsync(Id("room"),Ct) ?? throw new InvalidOperationException("fixture checkpoint missing");
        await Snapshots().SaveIfDueAsync(snapshot with { Revision=snapshot.Revision+10,
            Players=snapshot.Players.Select(p=>p with {Phase=RoomPlayerPhase.Extracted}).ToArray() },Ct);
        // Explicit corruption injection only in a new owned fixture. Preserve
        // the real receipt and every history row; never delete/restore data.
        await ExecuteAsync("UPDATE match_players SET state=$1,settlement_id=NULL WHERE match_id=$2 AND player_id=$3",
            retainSettledState ? "Settled" : "Active",Id("match"),Id("player"));
        Evidence["receipt_preserved"]=await ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1 AND player_id=$2",Id("match"),Id("player"))==1;
    }
    static async Task SeedConsistentSettlementAsync()
    {
        await SeedPendingAsync();
        Require(await Settlements().CommitHoldsAsync(Id("receipt"),Ct)==1,"consistent fixture hold must commit once");
    }
    static async Task SeedOrphanReceiptAsync()
    {
        await SeedConsistentSettlementAsync();
        await ExecuteAsync("INSERT INTO match_settlements(settlement_id,match_id,player_id,result,details_json,created_at) VALUES($1,$2,$3,'Extracted','{}'::jsonb,$4)",
            Guid.NewGuid(),Id("match"),Id("teammate"),Clock.GetUtcNow());
    }
    static async Task SeedOrphanMemberAsync()
    {
        await SeedConsistentSettlementAsync();
        var snapshot=await Snapshots().GetAsync(Id("room"),Ct) ?? throw new InvalidOperationException("fixture checkpoint missing");
        var orphan=Room(Id("room"),Id("teammate")).Capture().Players.Single();
        await Snapshots().SaveIfDueAsync(snapshot with {Revision=snapshot.Revision+10,Players=[..snapshot.Players,orphan]},Ct);
    }
    static async Task SeedWrongHoldOwnerAsync()
    {
        await SeedConsistentSettlementAsync();
        await ExecuteAsync("UPDATE settlement_asset_holds SET player_id=$1 WHERE settlement_id=$2",Id("teammate"),Id("receipt"));
    }
    static async Task SeedNextAsync()
    {
        Put("next_room",Guid.NewGuid());Put("next_match",Guid.NewGuid());Clock.Advance(TimeSpan.FromSeconds(1));
        await MatchAsync(Id("next_match"),Id("next_room"),Id("player"));await Snapshots().SaveIfDueAsync(Room(Id("next_room"),Id("player")).Capture(),Ct);
    }
    static async Task SettlementDropAsync()
    {
        await using var proxy=Proxy("COMMIT");await using var intercepted=Intercepted(proxy);using var details=JsonDocument.Parse("{}");var failed=false;
        try{await Settlements(intercepted).SettleAsync(Id("match"),Id("player"),"Extracted",details.RootElement,[new("Gold","gold",false,23)],Ct);}catch(NpgsqlException){failed=true;}
        Require(failed && proxy.DroppedCommittedResponse,"settlement response was not actually dropped");
        Put("receipt",(await Settlements().GetForMatchAsync(Id("player"),Id("match"),Ct)).SettlementId);
        Evidence["receipt"]=Id("receipt");Evidence["committed_response_dropped"]=true;
    }
    static async Task SettlementReplayAsync()
    {
        using var details=JsonDocument.Parse("{}");var settlements=Settlements();var receipt=await settlements.SettleAsync(Id("match"),Id("player"),"Extracted",details.RootElement,[new("Gold","gold",false,23)],Ct);
        Require(!receipt.Created && receipt.SettlementId==Id("receipt"),"receipt not replayed");
        Evidence["holds_committed_this_attempt"]=await settlements.CommitHoldsAsync(receipt.SettlementId,Ct);
        Require(await settlements.CommitHoldsAsync(receipt.SettlementId,Ct)==0,"holds committed twice");
        var gold=await ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1",Id("player"));
        var receipts=await ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1",Id("match"));
        var holds=await ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Committed'",receipt.SettlementId);
        var ledger=await ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'",Id("player"));
        Require(gold==Fixture["initial_gold"]!.GetValue<long>()+23 && receipts==1 && holds==1 && ledger==1,"wallet/receipt/hold/ledger duplicated");
        Evidence["wallet_gold"]=gold;Evidence["receipt"]=receipt.SettlementId;Evidence["receipt_count"]=receipts;Evidence["hold_count"]=holds;Evidence["ledger_count"]=ledger;
    }
    static async Task DrainAsync()
    {
        var active=await ScalarAsync<long>("SELECT count(*) FROM matches WHERE status IN ('Starting','Launching','Running')");
        var holds=await ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state IN ('Pending','Held')");
        var legacy=await ScalarAsync<long>("SELECT count(*) FROM matches m JOIN room_snapshots s ON s.room_id=m.room_id CROSS JOIN LATERAL jsonb_array_elements(s.snapshot_json->'players') j JOIN match_players p ON p.match_id=m.match_id AND p.player_id=(j->>'playerId')::uuid LEFT JOIN match_settlements r ON r.settlement_id=p.settlement_id WHERE (p.state='Settled' OR r.settlement_id IS NOT NULL) AND ((j->>'phase') NOT IN ('Dead','Extracted') OR (r.result IN ('Dead','Extracted') AND r.result<>j->>'phase'))");
        var associations=await ScalarAsync<long>("""
            SELECT count(*) FROM match_players p
            FULL OUTER JOIN match_settlements r ON r.match_id=p.match_id AND r.player_id=p.player_id
            LEFT JOIN matches m ON m.match_id=coalesce(p.match_id,r.match_id)
            LEFT JOIN room_snapshots s ON s.room_id=m.room_id
            LEFT JOIN LATERAL (
                SELECT count(*) AS members,min(j->>'phase') AS phase
                FROM jsonb_array_elements(s.snapshot_json->'players') j
                WHERE j->>'playerId'=coalesce(p.player_id,r.player_id)::text
            ) snapshot ON true
            WHERE p.player_id IS NULL
              OR (p.settlement_id IS NOT NULL AND p.settlement_id IS DISTINCT FROM r.settlement_id)
              OR (r.settlement_id IS NOT NULL AND (p.state<>'Settled' OR p.settlement_id IS DISTINCT FROM r.settlement_id))
              OR (p.state='Settled' AND (
                    (NOT p.is_bot AND r.settlement_id IS NULL)
                    OR s.room_id IS NULL OR snapshot.members<>1
                    OR snapshot.phase IS NULL OR snapshot.phase NOT IN ('Dead','Extracted')
                    OR (r.settlement_id IS NOT NULL AND r.result IS DISTINCT FROM snapshot.phase)))
              OR (m.status='Completed' AND p.state NOT IN ('Settled','Removed'))
            """);
        var orphanMembers=await ScalarAsync<long>("""
            SELECT count(*) FROM room_snapshots s JOIN matches m ON m.room_id=s.room_id
            CROSS JOIN LATERAL jsonb_array_elements(s.snapshot_json->'players') j
            LEFT JOIN match_players p ON p.match_id=m.match_id AND p.player_id::text=j->>'playerId'
            WHERE p.player_id IS NULL
            """);
        var wrongHoldOwners=await ScalarAsync<long>("""
            SELECT count(*) FROM settlement_asset_holds h
            LEFT JOIN match_settlements r ON r.settlement_id=h.settlement_id
            WHERE r.settlement_id IS NULL OR h.player_id IS DISTINCT FROM r.player_id
            """);
        var inconsistent=associations+orphanMembers+wrongHoldOwners;
        Evidence["active_match_count"]=active;Evidence["pending_hold_count"]=holds;Evidence["contradictory_snapshot_count"]=inconsistent;
        Evidence["settlement_association_error_count"]=associations;
        Evidence["orphan_snapshot_member_count"]=orphanMembers;Evidence["wrong_hold_owner_count"]=wrongHoldOwners;
        Evidence["legacy_contradictory_snapshot_count"]=legacy;Evidence["legacy_drain_allowed"]=active==0 && holds==0 && legacy==0;
        Evidence["drain_guard_completeness_proven"]=false;
        Evidence["drain_allowed"]=active==0 && holds==0 && inconsistent==0;
    }
    static async Task<string> DdlHashAsync()
    {
        var ddl=await ScalarAsync<string>("""
            SELECT jsonb_build_object(
              'columns',(SELECT jsonb_agg(to_jsonb(c) ORDER BY table_name,ordinal_position) FROM information_schema.columns c WHERE table_schema=current_schema()),
              'constraints',(SELECT jsonb_agg(jsonb_build_object('table',t.relname,'name',c.conname,'definition',pg_get_constraintdef(c.oid)) ORDER BY t.relname,c.conname) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname=current_schema()),
              'indexes',(SELECT jsonb_agg(to_jsonb(i) ORDER BY tablename,indexname) FROM pg_indexes i WHERE schemaname=current_schema()),
              'functions',(SELECT jsonb_agg(pg_get_functiondef(p.oid) ORDER BY p.proname) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=current_schema() AND p.proname NOT LIKE 'compat_fail_%'),
              'triggers',(SELECT jsonb_agg(pg_get_triggerdef(g.oid) ORDER BY t.relname,g.tgname) FROM pg_trigger g JOIN pg_class t ON t.oid=g.tgrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname=current_schema() AND NOT g.tgisinternal AND g.tgname NOT LIKE 'compat_fail_%')
            )::text
            """);
        return Hash(JsonNode.Parse(ddl));
    }
    static CommitResponseDropProxy Proxy(string statement)
    { var s=new NpgsqlConnectionStringBuilder(Db.ConnectionString);return new(s.Host!,s.Port,statement); }
    static NpgsqlDataSource Intercepted(CommitResponseDropProxy proxy)
    { var s=new NpgsqlConnectionStringBuilder(Db.ConnectionString){Host=proxy.SocketDirectory,SslMode=SslMode.Disable};return NpgsqlDataSource.Create(s.ConnectionString); }
}

sealed class FrozenClock(DateTimeOffset now) : TimeProvider
{
    DateTimeOffset _now=now;
    public override DateTimeOffset GetUtcNow()=>_now;
    public void Advance(TimeSpan delta)=>_now+=delta;
    public override ITimer CreateTimer(TimerCallback callback,object? state,TimeSpan dueTime,TimeSpan period)=>new DormantTimer();
    sealed class DormantTimer : ITimer
    { public bool Change(TimeSpan dueTime,TimeSpan period)=>true;public void Dispose(){}public ValueTask DisposeAsync()=>ValueTask.CompletedTask; }
}
