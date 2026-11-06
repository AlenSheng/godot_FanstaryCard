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
    public async Task JourneyRewards_ActualBinaryHttpClaimsFrozenCopiesAndSelectsOwnedCosmetics()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);timeout.CancelAfter(TimeSpan.FromSeconds(150));var ct=timeout.Token;
        var port=ReserveLoopbackPort();await using var server=StartServer(db.ConnectionString,port,legacy:false);
        using var client=new HttpClient{BaseAddress=new Uri($"http://127.0.0.1:{port}"),Timeout=TimeSpan.FromSeconds(15)};
        await server.WaitUntilReadyAsync(client,ct);client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));string? token=null;
        async Task<byte[]> Call(string method,string path,IMessage? body=null,string? key=null,HttpStatusCode expected=HttpStatusCode.OK)
        {
            using var request=new HttpRequestMessage(new HttpMethod(method),path);
            if(token is not null)request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",token);
            if(method!="GET")request.Content=PbContent(body??new Wire.Empty());if(key is not null)request.Headers.Add("Idempotency-Key",key);
            using var response=await client.SendAsync(request,ct);var bytes=await response.Content.ReadAsByteArrayAsync(ct);
            Assert.True(response.StatusCode==expected,$"{path}: expected {expected}, got {response.StatusCode}");
            Assert.Equal(HttpProtocolRegistry.MediaType,response.Content.Headers.ContentType?.MediaType);return bytes;
        }
        await Call("GET","/api/v1/cosmetics",expected:HttpStatusCode.Unauthorized);
        await Call("GET","/api/v1/season-journey/rewards?seasonId=unknown",expected:HttpStatusCode.Unauthorized);
        var login=Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST","/api/v1/auth/local",new Wire.LocalSignInRequest{DeviceId=Guid.NewGuid().ToString(),DisplayName="Reward-"+Guid.NewGuid().ToString("N")[..6]}));
        token=login.AccessToken;var player=Guid.Parse(login.Player.UserId);var config=GameConfigCatalog.Current;
        var today=DateOnly.FromDateTime(DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).DateTime);
        var season=SeasonDefinition.FromCalendarDays("journey-reward-api",today.AddDays(-20),config.Version,"season-equipment-v1");
        var p=await JourneyTestInputs.Existing(db,player,season,new CraftingClock(DateTimeOffset.UtcNow.AddMinutes(-1)));
        // Declared high-level storage fixture, not a completed level-30 route.
        await PostgresJourneyRewardEntitlementTests.SeedExperience(db,p,12525);await PostgresJourneyRewardEntitlementTests.Unlock(db,p,_=>0);
        await Call("GET","/api/v1/season-journey/rewards",expected:HttpStatusCode.Conflict);
        var missingBytes=await Call("GET","/api/v1/season-journey/rewards?seasonId=missing-original");
        Assert.Equal("None",Wire.JourneyRewardsResponse.Parser.ParseFrom(missingBytes).State);
        var beforeBytes=await Call("GET","/api/v1/season-journey/rewards?seasonId="+season.SeasonId);var rewards=Wire.JourneyRewardsResponse.Parser.ParseFrom(beforeBytes);Assert.Equal(30,rewards.Rewards.Count);
        var pack=rewards.Rewards.Single(r=>r.Level==5);var packPath="/api/v1/season-journey/rewards/"+pack.RewardId+"/claim";
        await Call("POST",packPath,new Wire.JourneyClaimRequest{SeasonId=season.SeasonId},expected:HttpStatusCode.BadRequest);
        var packBytes=await Call("POST",packPath,new Wire.JourneyClaimRequest{SeasonId=season.SeasonId},"real-pack");
        Assert.Equal(packBytes,await Call("POST",packPath,new Wire.JourneyClaimRequest{SeasonId=season.SeasonId},"real-pack"));
        Assert.Equal(3,Wire.JourneyClaimResponse.Parser.ParseFrom(packBytes).Grants.Sum(g=>g.Amount));
        var soul=rewards.Rewards.Single(r=>r.Level==3);var soulPath="/api/v1/season-journey/rewards/"+soul.RewardId+"/claim";
        await Call("POST",soulPath,new Wire.JourneyClaimRequest{SeasonId=season.SeasonId},"missing-choice",HttpStatusCode.Conflict);
        var soulBytes=await Call("POST",soulPath,new Wire.JourneyClaimRequest{SeasonId=season.SeasonId,HeroClass="Mage"},"real-class");
        Assert.Equal("MageSoul",Assert.Single(Wire.JourneyClaimResponse.Parser.ParseFrom(soulBytes).Grants).Kind);
        foreach(var level in new[]{21,22,23,24})
        {
            var reward=rewards.Rewards.Single(r=>r.Level==level);
            await Call("POST","/api/v1/season-journey/rewards/"+reward.RewardId+"/claim",new Wire.JourneyClaimRequest{SeasonId=season.SeasonId},"cosmetic-"+level);
        }
        var inventoryBytes=await Call("GET","/api/v1/cosmetics");var inventory=Wire.CosmeticsResponse.Parser.ParseFrom(inventoryBytes);Assert.Equal(4,inventory.Owned.Count);
        var selectionBytes=await Call("PUT","/api/v1/cosmetics/selection",new Wire.CosmeticSelectionRequest{Slot="AvatarFrame",CosmeticId="trail-seeker",ExpectedVersion=inventory.Selection.Version},"real-selection");
        var selection=Wire.CosmeticSelectionResponse.Parser.ParseFrom(selectionBytes);Assert.Equal("trail-seeker",selection.AvatarFrameId);
        await Call("PUT","/api/v1/cosmetics/selection",new Wire.CosmeticSelectionRequest{Slot="Title",CosmeticId="first-threshold",ExpectedVersion=selection.Version},"wrong-slot",HttpStatusCode.Conflict);
        await Call("PUT","/api/v1/cosmetics/selection",new Wire.CosmeticSelectionRequest{Slot="Title",CosmeticId="relic-seeker",ExpectedVersion=inventory.Selection.Version},"stale-selection",HttpStatusCode.Conflict);
        var afterBytes=await Call("GET","/api/v1/season-journey/rewards?seasonId="+season.SeasonId);
        Assert.Equal(6,Wire.JourneyRewardsResponse.Parser.ParseFrom(afterBytes).Rewards.Count(r=>r.State=="Claimed"));
        var finalInventoryBytes=await Call("GET","/api/v1/cosmetics");Assert.Equal("trail-seeker",Wire.CosmeticsResponse.Parser.ParseFrom(finalInventoryBytes).Selection.AvatarFrameId);
        var directory=Environment.GetEnvironmentVariable("FANTASYCARD_JOURNEY_REWARD_INTEROP_DIR");
        if(!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
            foreach(var pair in new[]{("before.bin",beforeBytes),("after.bin",afterBytes),("missing.bin",missingBytes),("pack.bin",packBytes),("soul.bin",soulBytes),("inventory.bin",inventoryBytes),("selection.bin",selectionBytes),("final-inventory.bin",finalInventoryBytes)})
                await File.WriteAllBytesAsync(Path.Combine(directory,pair.Item1),pair.Item2,ct);
        }
    }
}
