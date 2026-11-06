using System.Net;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;
using FantasyCard.Server.Tests.Config;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Npgsql;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    [Theory(Skip = "Requires an owned local PostgreSQL database.", SkipUnless = nameof(HasPrivateDatabase))]
    [Trait("Category", "PostgresIntegration")]
    [MemberData(nameof(SeasonAssetFaultModes))]
    public async Task Full_host_season_asset_fault_boundaries_preserve_domains_and_once_only_receipts(string mode)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:false);
        Record("SEASON-ASSET-schema",new{schema=new NpgsqlConnectionStringBuilder(db.ConnectionString).SearchPath,mode});
        await db.MigrateAsync();using var deadline=Deadline(100);var ct=deadline.Token;
        using var archive=new ConfigArchiveDirectory();var oldBytes=File.ReadAllBytes(FindOriginal16());
        var oldConfig=GameConfigCatalog.Load(oldBytes);var current=GameConfigCatalog.Current;
        PublishedConfigTestInputs.Store(archive.Root,oldConfig.Version,oldBytes,oldConfig.ContentHash);
        var today=DateOnly.FromDateTime(DateTime.UtcNow);
        var oldSeason=SeasonDefinition.FromCalendarDays("fault-old16",today.AddDays(-49),oldConfig.Version,"season-equipment-v1",highestOpenDifficulty:5);
        var newSeason=SeasonDefinition.FromCalendarDays("fault-current17",today.AddDays(-7),current.Version,"season-equipment-v1",highestOpenDifficulty:5);
        var seasons=new SeasonRepository(db.DataSource,TimeProvider.System);
        await seasons.PublishAsync(oldSeason,oldConfig.ContentHash,ct,oldConfig);await seasons.PublishAsync(newSeason,current.ContentHash,ct,current);
        var sourceConfig=mode=="hold-before-commit"?oldConfig:current;var sourceSeason=mode=="hold-before-commit"?oldSeason:newSeason;
        var player=await SeedPlayerAsync(db,"Season asset fault",ct);
        var fixture=await SeedSeasonCreditRoom(db,sourceConfig,sourceSeason,player.Id,sourceConfig==oldConfig?null:.75,ct);
        await seasons.EnsurePlayerAsync(player.Id,newSeason.ContextFor(0),ct);
        using var metrics=new ServerMetrics();var snapshots=new RoomSnapshotRepository(db.DataSource,TimeProvider.System,metrics);
        var state=fixture.Room.Capture();state=state with{Players=state.Players.Select(p=>p with{Phase=RoomPlayerPhase.Extracted,Pve=null}).ToArray()};
        await snapshots.SaveIfDueAsync(state,ct);
        var reward=RewardChoiceState.Create(ChaosMapLayer.Outer,new CombatRandom(73),configuration:sourceConfig,
            season:new SeasonRewardContext(sourceSeason.ContextFor(0),SeasonRewardBias.None),roomId:fixture.Room.RoomId)
            .Options.Single(o=>o.Kind==RewardChoiceKind.Equipment).Item!;
        var generated=Guid.Parse(reward.ItemId);var assets=new SettlementAsset[]{new("Gold","gold",false,23),new("EquipmentFragments","equipment_fragments",false,7),
            new("WarriorSoul","warrior_soul",false,3),new("ClassSoul","class_soul:Mage",false,4),
            new("Equipment",generated.ToString("D"),false,Equipment:reward.Equipment)};
        var repository=new SettlementRepository(db.DataSource,TimeProvider.System,metrics,new PublishedConfigCatalogs(current,archive.Root));
        var before=await SeasonFaultBalances(db,player.Id,sourceSeason.SeasonId,newSeason.SeasonId);
        var receipt=await repository.SettleAsync(fixture.Match,player.Id,"Extracted",JsonSerializer.SerializeToElement(new{roomId=fixture.Room.RoomId,heroClass="Mage"}),assets,ct,
            sourceSeason.ContextFor(0),sourceConfig.Version);
        Assert.Equal(5L,await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'",receipt.SettlementId));
        Assert.Empty(await repository.GetReadyNotificationsAsync(player.Id,ct));
        var gate=RandomNumberGenerator.GetInt32(1,int.MaxValue);await using var keeper=await db.DataSource.OpenConnectionAsync(ct);var gateHeld=false;
        if(mode!="ack-committed-response-lost")
        {
            await using(var acquire=new NpgsqlCommand("SELECT pg_advisory_lock($1::bigint)",keeper)){acquire.Parameters.AddWithValue(gate);await acquire.ExecuteNonQueryAsync(ct);}
            gateHeld=true;
            var table=mode=="hold-before-commit"?"economy_ledger":"settlement_notification_outbox";
            var clause=mode=="hold-before-commit"?"BEFORE INSERT":"BEFORE UPDATE OF published_at";
            var condition=mode=="hold-before-commit"?"NEW.reason='settlement.commit'":"OLD.published_at IS NULL AND NEW.published_at IS NOT NULL";
            await SqlAsync(db,$"CREATE FUNCTION fc_season_crash_gate() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_advisory_xact_lock({gate}::bigint); RETURN NEW; END $$",ct);
            await SqlAsync(db,$"CREATE TRIGGER fc_season_crash_gate {clause} ON {table} FOR EACH ROW WHEN ({condition}) EXECUTE FUNCTION fc_season_crash_gate()",ct);
        }
        var port=ReservePort();using var client=Client(port,player.Token);var pids=new List<int>();FullHost? first=null,second=null,third=null;var mustRedeliver=true;
        var firstHostConnection=db.ConnectionString;
        if(mode=="notification-mark-rollback")
            firstHostConnection=new NpgsqlConnectionStringBuilder(db.ConnectionString){ApplicationName="fc-f02-notify-"+Guid.NewGuid().ToString("N")}.ConnectionString;
        try
        {
            first=FullHost.Start(firstHostConnection,port,"season-asset-"+mode+"-first",configArchiveDirectory:archive.Root);pids.Add(first.ProcessId);
            await first.WaitForHealthAsync(client,"/health/live",HttpStatusCode.OK,ct);
            if(mode=="hold-before-commit")
            {
                await WaitSeasonGate(db,gate,ct);
                Assert.Equal(before,await SeasonFaultBalances(db,player.Id,sourceSeason.SeasonId,newSeason.SeasonId));
                Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'",player.Id));
                Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1",generated));
                Assert.Empty(await repository.GetReadyNotificationsAsync(player.Id,ct));
                using var earlyAck=new HttpRequestMessage(HttpMethod.Post,$"/api/v1/settlements/{receipt.SettlementId:D}/acknowledge");
                earlyAck.Headers.Add("Idempotency-Key","fault-before-ready");earlyAck.Content=new ByteArrayContent(new Wire.Empty().ToByteArray());earlyAck.Content.Headers.ContentType=new(HttpProtocolRegistry.MediaType);
                using var rejected=await client.SendAsync(earlyAck,ct);Assert.Equal(HttpStatusCode.Conflict,rejected.StatusCode);
                Record("SEASON-ASSET-uncommitted-gate",new{mode,first.ProcessId,gate,receipt.SettlementId,pending=5,visibleWalletsUnchanged=true,earlyAckStatus=(int)rejected.StatusCode});
            }
            else
            {
                await first.WaitForHealthAsync(client,"/health/ready",HttpStatusCode.OK,ct);
                await WaitAsync(async()=>await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'",receipt.SettlementId)==0,ct);
                await AssertSeasonFaultAssets(db,player.Id,sourceSeason,newSeason,fixture.Match,receipt.SettlementId,generated,before);
                if(mode is "notification-before-mark" or "notification-mark-rollback")
                {
                    using var socket=await ConnectAsync(client,port,ct);
                    var ready=Assert.IsType<SettlementReadyEventPayload>((await EventAsync(socket,"settlement.ready",ct)).Payload);
                    Assert.Equal(receipt.SettlementId,ready.SettlementId);await WaitSeasonGate(db,gate,ct);
                    Assert.True(await db.ScalarAsync<bool>("SELECT published_at IS NULL FROM settlement_notification_outbox WHERE settlement_id=$1",receipt.SettlementId));
                    Record("SEASON-ASSET-notification-before-mark",new{mode,first.ProcessId,gate,ready,published=false});
                    await first.KillAsync(); // before disposing the live socket
                }
            }
            await first.KillAsync();
            if(gateHeld)
            {
                if(mode=="notification-mark-rollback")
                {
                    // A separate declared fault exercises the rollback branch
                    // of the notification's autocommit statement. Select only
                    // this job's gate waiters after its app process is dead.
                    var settings=new NpgsqlConnectionStringBuilder(firstHostConnection);var gateBackends=new List<int>();var ownedBackends=new List<int>();
                    var ownedApp=settings.ApplicationName??throw new InvalidOperationException("Owned ApplicationName is required.");
                    var ownedDatabase=settings.Database??throw new InvalidOperationException("Owned database is required.");
                    var ownedUser=settings.Username??throw new InvalidOperationException("Owned database role is required.");
                    await using(var waiters=db.DataSource.CreateCommand("SELECT l.pid,a.usename,a.application_name FROM pg_locks l JOIN pg_stat_activity a USING(pid) WHERE l.locktype='advisory' AND l.classid::bigint=0 AND l.objid::bigint=$1 AND l.objsubid=1 AND NOT l.granted"))
                    {
                        waiters.Parameters.AddWithValue((long)gate);await using var reader=await waiters.ExecuteReaderAsync(ct);
                        while(await reader.ReadAsync(ct)){Assert.Equal(settings.Username,reader.GetString(1));Assert.Equal(settings.ApplicationName,reader.GetString(2));gateBackends.Add(reader.GetInt32(0));}
                    }
                    Assert.NotEmpty(gateBackends);
                    Assert.NotEqual(new NpgsqlConnectionStringBuilder(db.ConnectionString).ApplicationName,settings.ApplicationName);
                    await using(var sessions=db.DataSource.CreateCommand("SELECT pid,usename FROM pg_stat_activity WHERE application_name=$1 AND datname=$2"))
                    {
                        sessions.Parameters.AddWithValue(ownedApp);sessions.Parameters.AddWithValue(ownedDatabase);
                        await using var reader=await sessions.ExecuteReaderAsync(ct);while(await reader.ReadAsync(ct)){Assert.Equal(settings.Username,reader.GetString(1));ownedBackends.Add(reader.GetInt32(0));}
                    }
                    Assert.All(gateBackends,pid=>Assert.Contains(pid,ownedBackends));
                    var signaledBackends=new List<int>();
                    foreach(var backend in ownedBackends)
                    {
                        await using var stop=db.DataSource.CreateCommand("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid=$1 AND application_name=$2 AND datname=$3 AND usename=$4");
                        stop.Parameters.AddWithValue(backend);stop.Parameters.AddWithValue(ownedApp);stop.Parameters.AddWithValue(ownedDatabase);stop.Parameters.AddWithValue(ownedUser);
                        if(await stop.ExecuteScalarAsync(ct) is true)signaledBackends.Add(backend);
                        else Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM pg_stat_activity WHERE pid=$1 AND application_name=$2",backend,ownedApp));
                    }
                    Assert.NotEmpty(signaledBackends);
                    Record("SEASON-ASSET-owned-notification-backends-stopped",new{mode,gate,gateBackends,ownedBackends,signaledBackends,settings.ApplicationName,appAlreadyKilled=true,onlyUniqueOwnedGateAndApplicationNameMatched=true});
                }
                // PostgreSQL may not notice the closed socket while waiting
                // inside a statement. Release our artificial gate first, then
                // wait until the dead client's transaction has drained.
                await using(var release=new NpgsqlCommand("SELECT pg_advisory_unlock($1::bigint)",keeper)){release.Parameters.AddWithValue(gate);Assert.True((bool)(await release.ExecuteScalarAsync(ct))!);}
                gateHeld=false;
                await WaitAsync(async()=>await db.ScalarAsync<long>("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid::bigint=0 AND objid::bigint=$1 AND objsubid=1",(long)gate)==0,ct);
                if(mode=="hold-before-commit")
                {
                    Assert.Equal(before,await SeasonFaultBalances(db,player.Id,sourceSeason.SeasonId,newSeason.SeasonId));
                    Assert.Equal(5L,await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'",receipt.SettlementId));
                }
                if(mode is "notification-before-mark" or "notification-mark-rollback")
                {
                    // This marker is an autocommit statement, unlike the
                    // explicit mixed-asset transaction. It may commit after
                    // process death; the actual frame was already observed.
                    mustRedeliver=await db.ScalarAsync<bool>("SELECT published_at IS NULL FROM settlement_notification_outbox WHERE settlement_id=$1",receipt.SettlementId);
                    if(mode=="notification-mark-rollback")Assert.True(mustRedeliver);
                    Record("SEASON-ASSET-notification-drained",new{mode,receipt.SettlementId,publishedAfterDeadClientDrain=!mustRedeliver,priorActualFrameObserved=true});
                }
                var table=mode=="hold-before-commit"?"economy_ledger":"settlement_notification_outbox";
                await SqlAsync(db,$"DROP TRIGGER fc_season_crash_gate ON {table}",ct);await SqlAsync(db,"DROP FUNCTION fc_season_crash_gate()",ct);
            }
            second=FullHost.Start(db.ConnectionString,port,"season-asset-"+mode+"-second",configArchiveDirectory:archive.Root);pids.Add(second.ProcessId);
            await second.WaitForHealthAsync(client,"/health/ready",HttpStatusCode.OK,ct);
            await AssertSeasonFaultAssets(db,player.Id,sourceSeason,newSeason,fixture.Match,receipt.SettlementId,generated,before);
            using var recoveredSocket=await ConnectAsync(client,port,ct);
            if(mustRedeliver)
            {
                var delivered=Assert.IsType<SettlementReadyEventPayload>((await EventAsync(recoveredSocket,"settlement.ready",ct)).Payload);
                Assert.Equal(receipt.SettlementId,delivered.SettlementId);Assert.Equal(fixture.Match,delivered.MatchId);
                Record("SEASON-ASSET-ready-recovered",new{mode,delivered});
            }
            await WaitAsync(async()=>await db.ScalarAsync<bool>("SELECT published_at IS NOT NULL FROM settlement_notification_outbox WHERE settlement_id=$1",receipt.SettlementId),ct);
            var fetched=Wire.SettlementResponse.Parser.ParseFrom(await CallAsync(client,HttpMethod.Get,$"/api/v1/settlements/{receipt.SettlementId:D}",null,ct));
            Assert.Equal(sourceSeason.SeasonId,fetched.Season.SeasonId);Assert.Equal(sourceConfig.Version,fetched.Season.ConfigVersion);
            Wire.SettlementAcknowledgementResponse ack;
            if(mode=="ack-committed-response-lost")
            {
                async Task RestartAfterAck()
                {
                    Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE settlement_id=$1 AND acknowledged_at IS NOT NULL",receipt.SettlementId));
                    await second.KillAsync();third=FullHost.Start(db.ConnectionString,port,"season-asset-ack-third",configArchiveDirectory:archive.Root);pids.Add(third.ProcessId);
                    await third.WaitForHealthAsync(client,"/health/ready",HttpStatusCode.OK,ct);
                }
                await using var proxy=new AckFaultProxy(port,"drop-first-committed-restart",restartAfterDroppedCommit:RestartAfterAck);
                using var proxyClient=Client(proxy.Port,player.Token);
                // Observe the lost response on a fresh HTTP/1.1 connection;
                // this first request has no application retry.
                using var request=new HttpRequestMessage(HttpMethod.Post,$"/api/v1/settlements/{receipt.SettlementId:D}/acknowledge"){Version=HttpVersion.Version11,VersionPolicy=HttpVersionPolicy.RequestVersionExact};
                request.Headers.ConnectionClose=true;request.Headers.Add("Idempotency-Key","season-fault-ack");
                request.Content=new ByteArrayContent(new Wire.Empty().ToByteArray());request.Content.Headers.ContentType=new(HttpProtocolRegistry.MediaType);
                await Assert.ThrowsAsync<HttpRequestException>(()=>proxyClient.SendAsync(request,ct));
                ack=Wire.SettlementAcknowledgementResponse.Parser.ParseFrom(await CallAsync(proxyClient,HttpMethod.Post,$"/api/v1/settlements/{receipt.SettlementId:D}/acknowledge",new Wire.Empty(),ct,"season-fault-ack"));
                Assert.Equal(2,proxy.Attempts.Count);Assert.All(proxy.Attempts,a=>Assert.Equal(200,a.BackendStatus));Assert.Empty(proxy.Errors);
                Assert.Equal(proxy.Attempts.First().ResponseSha256,proxy.Attempts.Last().ResponseSha256);
                Record("SEASON-ASSET-ACK-lost-response",new{mode,attempts=proxy.Attempts.ToArray(),receipt.SettlementId,ack});
            }
            else
            {
                ack=Wire.SettlementAcknowledgementResponse.Parser.ParseFrom(await CallAsync(client,HttpMethod.Post,$"/api/v1/settlements/{receipt.SettlementId:D}/acknowledge",new Wire.Empty(),ct,"season-fault-ack"));
                await second.KillAsync();third=FullHost.Start(db.ConnectionString,port,"season-asset-"+mode+"-third",configArchiveDirectory:archive.Root);pids.Add(third.ProcessId);
                await third.WaitForHealthAsync(client,"/health/ready",HttpStatusCode.OK,ct);
            }
            var replay=Wire.SettlementAcknowledgementResponse.Parser.ParseFrom(await CallAsync(client,HttpMethod.Post,$"/api/v1/settlements/{receipt.SettlementId:D}/acknowledge",new Wire.Empty(),ct,"season-fault-ack"));Assert.Equal(ack,replay);
            await AssertSeasonFaultAssets(db,player.Id,sourceSeason,newSeason,fixture.Match,receipt.SettlementId,generated,before);
            Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE settlement_id=$1 AND acknowledged_at IS NOT NULL",receipt.SettlementId));
            Assert.Equal(3,pids.Distinct().Count());
            Record("SEASON-ASSET-final",new{mode,pids,fixture.Match,fixture.Room.RoomId,receipt.SettlementId,generated,sourceSeason=sourceSeason.SeasonId,sourceConfig=sourceConfig.Version,
                gold=23,fragments=7,warriorSoul=3,mageSoul=4,ledgerRows=4,physicalItems=1,duplicateAckSameReceipt=true,successfulPlayerCasts=0,completedEncounters=0,
                scope="Fault-specific durable Pending checkpoint and actual Program/PG/HTTP/WS, no normal gameplay or capacity rerun"});
        }
        finally
        {
            if(first is not null)await first.DisposeAsync();if(second is not null)await second.DisposeAsync();if(third is not null)await third.DisposeAsync();
            if(gateHeld){await using var release=new NpgsqlCommand("SELECT pg_advisory_unlock($1::bigint)",keeper);release.Parameters.AddWithValue(gate);await release.ExecuteScalarAsync(CancellationToken.None);}
        }
    }

    public static IEnumerable<object[]> SeasonAssetFaultModes()
    {
        var all=new[]{"hold-before-commit","notification-before-mark","notification-mark-rollback","ack-committed-response-lost"};
        var selected=Environment.GetEnvironmentVariable("FANTASYCARD_F02_ASSET_MODES")?.Split(',',StringSplitOptions.RemoveEmptyEntries)??all;
        if(selected.Length==0||selected.Distinct().Count()!=selected.Length||selected.Any(mode=>!all.Contains(mode,StringComparer.Ordinal)))
            throw new InvalidOperationException("The declared asset fault selection is invalid.");
        return selected.Select(mode=>new object[]{mode});
    }

    private static async Task WaitSeasonGate(PostgresTestSchema db,int gate,CancellationToken ct)=>
        await WaitAsync(async()=>await db.ScalarAsync<long>("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid::bigint=0 AND objid::bigint=$1 AND objsubid=1 AND NOT granted",(long)gate)>0,ct);

    private static async Task<string> SeasonFaultBalances(PostgresTestSchema db,Guid player,string source,string current)=>await db.ScalarAsync<string>("""
        SELECT jsonb_build_object('gold',w.gold,'diamond',w.diamond,'fragments',m.equipment_fragments,'warrior',m.warrior_soul,'mage',m.mage_soul,
            'sourceGold',(SELECT gold FROM player_season_wallets WHERE player_id=$1 AND season_id=$2),
            'sourceFragments',(SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1 AND season_id=$2),
            'currentGold',(SELECT gold FROM player_season_wallets WHERE player_id=$1 AND season_id=$3),
            'currentFragments',(SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1 AND season_id=$3))::text
        FROM player_wallets w JOIN player_materials m USING(player_id) WHERE w.player_id=$1
        """,player,source,current);

    private static async Task AssertSeasonFaultAssets(PostgresTestSchema db,Guid player,SeasonDefinition source,SeasonDefinition current,Guid match,Guid settlement,Guid item,string before)
    {
        using var baseline=JsonDocument.Parse(before);using var now=JsonDocument.Parse(await SeasonFaultBalances(db,player,source.SeasonId,current.SeasonId));var b=baseline.RootElement;var n=now.RootElement;
        Assert.Equal(b.GetProperty("gold").GetInt64(),n.GetProperty("gold").GetInt64());Assert.Equal(b.GetProperty("diamond").GetInt64(),n.GetProperty("diamond").GetInt64());
        Assert.Equal(b.GetProperty("fragments").GetInt64(),n.GetProperty("fragments").GetInt64());Assert.Equal(b.GetProperty("warrior").GetInt64()+3,n.GetProperty("warrior").GetInt64());Assert.Equal(b.GetProperty("mage").GetInt64()+4,n.GetProperty("mage").GetInt64());
        Assert.Equal(b.GetProperty("sourceGold").GetInt64()+23,n.GetProperty("sourceGold").GetInt64());Assert.Equal(b.GetProperty("sourceFragments").GetInt64()+7,n.GetProperty("sourceFragments").GetInt64());
        if(source.SeasonId!=current.SeasonId){Assert.Equal(b.GetProperty("currentGold").GetInt64(),n.GetProperty("currentGold").GetInt64());Assert.Equal(b.GetProperty("currentFragments").GetInt64(),n.GetProperty("currentFragments").GetInt64());}
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'",settlement));
        Assert.Equal(5L,await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Committed'",settlement));
        Assert.Equal(4L,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit' AND season_id=$2 AND config_version=$3 AND difficulty_id='D0' AND stats_version=$4",player,source.SeasonId,source.ConfigVersion,source.StatsVersion));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND owner_id=$2 AND origin_season_id=$3 AND source_match_id=$4 AND source_kind='NaturalDrop' AND stats_version=$5",item,player,source.SeasonId,match,source.StatsVersion));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1 AND player_id=$2 AND season_id=$3 AND config_version=$4",item,player,source.SeasonId,source.ConfigVersion));
    }
}
