using System.Net;
using System.Net.Http.Headers;
using FantasyCard.Contracts.Http;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task SeasonActivity_ActualBinaryHttpReservesSharedTokensAndClaimsTheSameEntitlementOnce()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);timeout.CancelAfter(TimeSpan.FromSeconds(150));var ct=timeout.Token;
        var port=ReserveLoopbackPort();await using var server=StartServer(db.ConnectionString,port,legacy:false);
        using var client=new HttpClient{BaseAddress=new Uri($"http://127.0.0.1:{port}"),Timeout=TimeSpan.FromSeconds(15)};
        await server.WaitUntilReadyAsync(client,ct);client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));string? token=null;
        async Task<byte[]> Call(string method,string path,IMessage? body=null,string? key=null,HttpStatusCode status=HttpStatusCode.OK)
        {
            using var request=new HttpRequestMessage(new HttpMethod(method),path);if(token is not null)request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",token);
            if(method!="GET")request.Content=PbContent(body??new Wire.Empty());if(key is not null)request.Headers.Add("Idempotency-Key",key);
            using var response=await client.SendAsync(request,ct);var bytes=await response.Content.ReadAsByteArrayAsync(ct);
            Assert.True(response.StatusCode==status,$"{path}: expected {status}, got {response.StatusCode}");Assert.Equal(HttpProtocolRegistry.MediaType,response.Content.Headers.ContentType?.MediaType);return bytes;
        }
        await Call("GET","/api/v1/season-activities",status:HttpStatusCode.Unauthorized);
        var login=Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST","/api/v1/auth/local",new Wire.LocalSignInRequest{DeviceId=Guid.NewGuid().ToString(),DisplayName="Event-"+Guid.NewGuid().ToString("N")[..6]}));
        token=login.AccessToken;var player=Guid.Parse(login.Player.UserId);var config=GameConfigCatalog.Current;
        var today=DateOnly.FromDateTime(DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).DateTime);
        var season=SeasonDefinition.FromCalendarDays("activity-api",today.AddDays(-12),config.Version,"season-equipment-v1");
        var p=await ActivityTestInputs.ForExistingPlayer(db,player,season,new CraftingClock(DateTimeOffset.UtcNow.AddMinutes(-5)));await ActivityTestInputs.Earn(db,p);
        var eventsBytes=await Call("GET","/api/v1/season-activities");var events=Wire.SeasonActivitiesResponse.Parser.ParseFrom(eventsBytes);
        var active=Assert.Single(events.Events,e=>e.State=="Active");Assert.Equal(12,active.Earned);Assert.Equal(12,active.Available);Assert.Equal(4,active.Options.Count);
        var invalid=new Wire.ActivityExchangeRequest{SeasonId=season.SeasonId,RuleId="red-material",ExpectedAccountVersion=active.AccountVersion,Quantity=1};
        await Call("POST",$"/api/v1/season-activities/{active.EventId}/exchanges",invalid,"activity-invalid-red",HttpStatusCode.Conflict);
        var request=new Wire.ActivityExchangeRequest{SeasonId=season.SeasonId,RuleId="event-fragments",ExpectedAccountVersion=active.AccountVersion,Quantity=4};
        var exchangeBytes=await Call("POST",$"/api/v1/season-activities/{active.EventId}/exchanges",request,"activity-reserve-all");
        Assert.Equal(exchangeBytes,await Call("POST",$"/api/v1/season-activities/{active.EventId}/exchanges",request,"activity-reserve-all"));
        var exchange=Wire.ActivityExchangeResponse.Parser.ParseFrom(exchangeBytes);Assert.Equal(0,exchange.TokensRemaining);Assert.Equal(40,exchange.Reward.RewardAmount);Assert.Equal("Pending",exchange.Reward.State);
        var claimBytes=await Call("POST",$"/api/v1/season-activities/rewards/{exchange.Reward.RewardId}/claim",key:"activity-claim-first");
        Assert.Equal(claimBytes,await Call("POST",$"/api/v1/season-activities/rewards/{exchange.Reward.RewardId}/claim",key:"activity-claim-again"));
        var claim=Wire.ActivityClaimResponse.Parser.ParseFrom(claimBytes);Assert.Equal(40,claim.BalanceAfter);Assert.Equal(season.SeasonId,claim.Reward.SeasonId);Assert.Equal("Claimed",claim.Reward.State);
        var updatedBytes=await Call("GET","/api/v1/season-activities");
        var directory=Environment.GetEnvironmentVariable("FANTASYCARD_ACTIVITY_INTEROP_DIR");
        if(!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
            foreach(var pair in new[]{("events.bin",eventsBytes),("exchange.bin",exchangeBytes),("claim.bin",claimBytes),("updated.bin",updatedBytes)})
                await File.WriteAllBytesAsync(Path.Combine(directory,pair.Item1),pair.Item2,ct);
        }
    }
}
