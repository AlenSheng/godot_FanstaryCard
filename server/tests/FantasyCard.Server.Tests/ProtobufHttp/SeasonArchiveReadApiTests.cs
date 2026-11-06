using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Http;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Npgsql;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip="Set isolated PostgreSQL database.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task SeasonArchive_binary_HTTP_preserves_original_versions_paginates_and_keeps_all_sections_readonly()
    {
        await using var db=await PostgresTestSchema.CreateAsync(false);var ct=TestContext.Current.CancellationToken;
        var evidence=Environment.GetEnvironmentVariable("FANTASYCARD_ARCHIVE_READ_SCHEMA_EVIDENCE");
        if(evidence is not null)File.AppendAllText(evidence,JsonSerializer.Serialize(new {schema=new NpgsqlConnectionStringBuilder(db.ConnectionString).SearchPath,kind="archive-http",at=DateTimeOffset.UtcNow})+Environment.NewLine);
        await db.MigrateAsync();
        using var stream=typeof(RealNetworkEndToEndTests).Assembly.GetManifestResourceStream("ArchivedD0Config15")!;
        using var bytes=new MemoryStream();await stream.CopyToAsync(bytes,ct);var original=GameConfigCatalog.Load(bytes.ToArray());
        var today=DateOnly.FromDateTime(TimeZoneInfo.ConvertTime(DateTimeOffset.UtcNow,TimeZoneInfo.FindSystemTimeZoneById(SeasonDefinition.TimeZoneId)).DateTime);
        var old=SeasonDefinition.FromCalendarDays("archive-http-old",today.AddDays(-42),original.Version,"season-equipment-v1",highestOpenDifficulty:5);
        var clock=new CraftingClock(old.StartsAtUtc.AddHours(2));var device=Guid.NewGuid().ToString("N");var display="Archive-"+device[..8];
        var identity=await new IdentityRepository(db.DataSource,new PlayerProvisioningService()).SignInLocalAsync(device,display,RandomNumberGenerator.GetBytes(32),clock.Now,clock.Now.AddHours(1),ct);
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(old,original.ContentHash,ct,original);await seasons.EnsurePlayerAsync(identity.UserId,old.ContextFor(0),ct);
        var inputs=new CraftingPlayer(identity.UserId,old,clock,seasons,new(db.DataSource,clock,new(original)));
        var ids=new List<Guid>();
        foreach(var slot in new[]{"Head","Chest","Hands"})
        {
            var id=await CraftingTestInputs.ItemAsync(db,inputs,slot:slot,level:3);ids.Add(id);
            await inputs.Progression.LearnSeasonRecipeAsync(inputs.Player,"api-learn-"+slot,new(old.SeasonId,id,1),ct);
            await CraftingTestInputs.SqlAsync(db,"INSERT INTO player_crafting_wishes(player_id,season_id,quality,slot,element,wished_effect,failures,updated_at) VALUES($1,$2,'Purple',$3,'Water','Vitality',2,now())",inputs.Player,old.SeasonId,slot);
        }
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_loadouts SET head_id=$2,chest_id=$3,hands_id=$4 WHERE player_id=$1",inputs.Player,ids[0],ids[1],ids[2]);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_wallets SET gold=9007199254740993,equipment_fragments=456,challenge_marks=77,blueprint_marks=4,orange_blueprint_marks=14 WHERE player_id=$1",inputs.Player);
        clock.Now=old.EndsAtUtc;await seasons.AdvanceArchivePageAsync(inputs.Player,old.SeasonId,32,ct);
        var current=SeasonDefinition.FromCalendarDays("archive-http-current",today,GameConfigCatalog.Current.Version,"season-equipment-v1");
        await seasons.PublishAsync(current,GameConfigCatalog.Current.ContentHash,ct);await seasons.EnsurePlayerAsync(inputs.Player,current.ContextFor(0),ct);
        var archiveRoot=Path.Combine(Path.GetTempPath(),"fc-archive-read-"+Guid.NewGuid().ToString("N"));var versionRoot=Path.Combine(archiveRoot,original.Version);Directory.CreateDirectory(versionRoot);
        await File.WriteAllBytesAsync(Path.Combine(versionRoot,"fantasycard.config.bytes"),bytes.ToArray(),ct);
        await File.WriteAllTextAsync(Path.Combine(versionRoot,"fantasycard.config.sha256"),original.ContentHash,ct);
        await File.WriteAllTextAsync(Path.Combine(versionRoot,"fantasycard.config.version.txt"),original.Version,ct);
        var interop=Environment.GetEnvironmentVariable("FANTASYCARD_ARCHIVE_READ_INTEROP_DIR");
        if(interop is not null)Directory.CreateDirectory(interop);
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);timeout.CancelAfter(TimeSpan.FromSeconds(120));
        var port=ReserveLoopbackPort();await using var server=StartServer(db.ConnectionString,port,archiveRoot,legacy:false);
        using var client=new HttpClient{BaseAddress=new Uri($"http://127.0.0.1:{port}"),Timeout=TimeSpan.FromSeconds(12)};await server.WaitUntilReadyAsync(client,timeout.Token);
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        async Task<byte[]> Get(string path,HttpStatusCode expected,string? save=null)
        {
            using var response=await client.GetAsync(path,timeout.Token);var raw=await response.Content.ReadAsByteArrayAsync(timeout.Token);
            Assert.Equal(expected,response.StatusCode);Assert.Equal(HttpProtocolRegistry.MediaType,response.Content.Headers.ContentType?.MediaType);
            if(expected!=HttpStatusCode.OK)Assert.Equal((int)expected,Wire.HttpError.Parser.ParseFrom(raw).Status);
            if(save is not null && interop is not null)await File.WriteAllBytesAsync(Path.Combine(interop,save+".bin"),raw,ct);
            return raw;
        }
        await Get("/api/v1/season-archives",HttpStatusCode.Unauthorized);
        async Task<Wire.LocalSignInResponse> Login(string id,string name)
        {
            using var response=await client.PostAsync("/api/v1/auth/local",PbContent(new Wire.LocalSignInRequest{DeviceId=id,DisplayName=name}),timeout.Token);
            Assert.Equal(HttpStatusCode.OK,response.StatusCode);return Wire.LocalSignInResponse.Parser.ParseFrom(await response.Content.ReadAsByteArrayAsync(timeout.Token));
        }
        var owner=await Login(device,display);Assert.Equal(inputs.Player.ToString("D"),owner.Player.UserId);
        var peer=await Login(Guid.NewGuid().ToString("N"),"Peer-"+Guid.NewGuid().ToString("N")[..8]);
        client.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",peer.AccessToken);
        Assert.Empty(Wire.SeasonArchivesResponse.Parser.ParseFrom(await Get("/api/v1/season-archives",HttpStatusCode.OK)).Items);
        await Get("/api/v1/season-archives/"+old.SeasonId+"/equipment",HttpStatusCode.NotFound);
        client.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",owner.AccessToken);
        var list=Wire.SeasonArchivesResponse.Parser.ParseFrom(await Get("/api/v1/season-archives?limit=1",HttpStatusCode.OK,"list"));var source=Assert.Single(list.Items);
        Assert.Equal(original.Version,source.ConfigVersion);Assert.Equal(original.ContentHash,source.ConfigSha256);Assert.Equal(9007199254740993,source.Wallet.Gold);
        Assert.Equal(77,source.Wallet.ChallengeMarks);Assert.Equal(4,source.Wallet.BlueprintMarks);Assert.Equal(14,source.Wallet.OrangeBlueprintMarks);
        foreach(var section in new[]{"equipment","recipes","wishes","loadouts"})
        {
            var path="/api/v1/season-archives/"+old.SeasonId+"/"+section+"?limit=2";
            var page=Wire.SeasonArchiveSectionResponse.Parser.ParseFrom(await Get(path,HttpStatusCode.OK,section));
            Assert.True(page.ReadOnly);Assert.Equal(source.ConfigSha256,page.Season.ConfigSha256);Assert.Equal(2,page.NextOffset);
            var tail=Wire.SeasonArchiveSectionResponse.Parser.ParseFrom(await Get(path+"&offset=2",HttpStatusCode.OK));Assert.False(tail.HasNextOffset);
            if(section=="equipment"){Assert.Equal(2,page.Equipments.Count);Assert.Single(tail.Equipments);Assert.All(page.Equipments,item=>Assert.Equal("SeasonArchive",item.Location));}
            if(section=="loadouts"){Assert.Equal(3,page.ReferencedEquipments.Count);Assert.Equal(ids[0].ToString("D"),page.Loadouts.Single(x=>x.HeroClass=="Mage").EquipmentIds[0]);}
        }
        var configuration=Wire.PublishedConfigurationResponse.Parser.ParseFrom(await Get("/api/v1/config/"+original.Version,HttpStatusCode.OK,"configuration"));
        Assert.Equal(original.ContentHash,configuration.ContentHash);Assert.Equal(original.Version,configuration.ConfigVersion);
        await Get("/api/v1/season-archives/"+current.SeasonId+"/equipment",HttpStatusCode.NotFound);
        await Get("/api/v1/season-archives?limit=51",HttpStatusCode.BadRequest,"invalid-page");
        await Get("/api/v1/season-archives/"+old.SeasonId+"/unknown",HttpStatusCode.BadRequest);
        Assert.Equal(456,await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",inputs.Player,old.SeasonId));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_discard_batches"));
    }
}
