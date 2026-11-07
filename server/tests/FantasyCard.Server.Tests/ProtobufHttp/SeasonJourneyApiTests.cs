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
    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task SeasonJourney_ActualAuthenticatedBinaryHttpKeepsOriginalProgressAndNeverOffersAClientExperienceGrant()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);timeout.CancelAfter(TimeSpan.FromSeconds(150));var ct=timeout.Token;
        var port=ReserveLoopbackPort();await using var server=StartServer(db.ConnectionString,port,legacy:false);
        using var client=new HttpClient{BaseAddress=new Uri($"http://127.0.0.1:{port}"),Timeout=TimeSpan.FromSeconds(15)};
        await server.WaitUntilReadyAsync(client,ct);client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));string? token=null;
        async Task<byte[]> Call(string method,string path,IMessage? body=null,HttpStatusCode status=HttpStatusCode.OK)
        {
            using var request=new HttpRequestMessage(new HttpMethod(method),path);if(token is not null)request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",token);
            if(method!="GET")request.Content=PbContent(body??new Wire.Empty());
            using var response=await client.SendAsync(request,ct);var bytes=await response.Content.ReadAsByteArrayAsync(ct);
            Assert.True(response.StatusCode==status,$"{path}: expected {status}, got {response.StatusCode}");
            Assert.Equal(HttpProtocolRegistry.MediaType,response.Content.Headers.ContentType?.MediaType);return bytes;
        }
        await Call("GET","/api/v1/season-journey",status:HttpStatusCode.Unauthorized);
        var login=Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST","/api/v1/auth/local",new Wire.LocalSignInRequest{DeviceId=Guid.NewGuid().ToString(),DisplayName="Journey-"+Guid.NewGuid().ToString("N")[..6]}));
        token=login.AccessToken;var player=Guid.Parse(login.Player.UserId);var config=GameConfigCatalog.Current;
        var today=DateOnly.FromDateTime(DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).DateTime);
        var season=SeasonDefinition.FromCalendarDays("journey-api",today.AddDays(-20),config.Version,"season-equipment-v1");
        var p=await JourneyTestInputs.Existing(db,player,season,new CraftingClock(DateTimeOffset.UtcNow.AddMinutes(1)));
        await JourneyTestInputs.Observe(db,p,await JourneyTestInputs.DeadAfterClears(db,p,"Elite","Boss"));
        var journeyBytes=await Call("GET","/api/v1/season-journey");var journey=Wire.SeasonJourneyResponse.Parser.ParseFrom(journeyBytes);
        Assert.Equal("Active",journey.State);Assert.Equal(season.SeasonId,journey.SeasonId);Assert.Equal(510,journey.Experience);
        Assert.Equal(30,journey.Levels.Count);Assert.Equal(20,journey.MainRewardLevels);Assert.Equal(12525,journey.MaximumExperience);
        Assert.Single(journey.Contracts,row=>row.CompletionKind=="Boss"&&row.State=="Completed");
        var scopedBytes=await Call("GET","/api/v1/season-journey?seasonId="+season.SeasonId+"&limit=1&experience=12525");
        Assert.Equal(510,Wire.SeasonJourneyResponse.Parser.ParseFrom(scopedBytes).Experience);
        using(var write=new HttpRequestMessage(HttpMethod.Post,"/api/v1/season-journey"))
        {
            write.Headers.Authorization=new AuthenticationHeaderValue("Bearer",token);write.Content=PbContent(new Wire.Empty());
            using var rejected=await client.SendAsync(write,ct);Assert.Equal(HttpStatusCode.MethodNotAllowed,rejected.StatusCode);
        }
        var missingBytes=await Call("GET","/api/v1/season-journey?seasonId=unknown-original");var missing=Wire.SeasonJourneyResponse.Parser.ParseFrom(missingBytes);
        Assert.Equal("None",missing.State);Assert.False(missing.HasSeasonId);Assert.Equal(0,missing.Experience);
        await Call("GET","/api/v1/season-journey?limit=101",status:HttpStatusCode.Conflict);
        for(var i=0;i<3;i++)await JourneyTestInputs.Observe(db,p,await JourneyTestInputs.Extract(db,p));
        var updatedBytes=await Call("GET","/api/v1/season-journey");Assert.Equal(1020,Wire.SeasonJourneyResponse.Parser.ParseFrom(updatedBytes).Experience);
        var directory=Environment.GetEnvironmentVariable("FANTASYCARD_JOURNEY_INTEROP_DIR");
        if(!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
            foreach(var pair in new[]{("journey.bin",journeyBytes),("scoped.bin",scopedBytes),("missing.bin",missingBytes),("updated.bin",updatedBytes)})
                await File.WriteAllBytesAsync(Path.Combine(directory,pair.Item1),pair.Item2,ct);
        }
    }
}
