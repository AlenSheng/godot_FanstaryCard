using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using FantasyCard.Contracts.Http;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip="Set isolated PostgreSQL database.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task SeasonCrafting_binary_session_uses_all_five_routes_and_preserves_asset_identity()
    {
        await using var database=await PostgresTestSchema.CreateAsync(migrate:false);
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(120));var ct=timeout.Token;var port=ReserveLoopbackPort();
        var start=new ProcessStartInfo("dotnet"){WorkingDirectory=FindServerProjectDirectory(),UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true,CreateNoWindow=true};
        start.ArgumentList.Add(typeof(FantasyCard.Server.Persistence.DatabaseMigrator).Assembly.Location);
        start.Environment["ASPNETCORE_ENVIRONMENT"]="Development";start.Environment["ASPNETCORE_URLS"]=$"http://127.0.0.1:{port}";
        start.Environment["ConnectionStrings__Postgres"]=database.ConnectionString;start.Environment["Identity__EnableLocalAuth"]="true";
        start.Environment["ProtobufHttp__AllowLegacyJson"]="false";start.Environment.Remove("OTEL_EXPORTER_OTLP_ENDPOINT");
        await using var server=NetworkServerProcess.Start(start);
        using var client=new HttpClient{BaseAddress=new Uri($"http://127.0.0.1:{port}"),Timeout=TimeSpan.FromSeconds(12)};
        await server.WaitUntilReadyAsync(client,ct);client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        async Task<byte[]> Call(string method,string path,IMessage? body=null,string? key=null,HttpStatusCode status=HttpStatusCode.OK)
        {
            using var request=new HttpRequestMessage(new HttpMethod(method),path);
            if(method!="GET")request.Content=PbContent(body??new Wire.Empty());
            if(key is not null)request.Headers.Add("Idempotency-Key",key);
            using var response=await client.SendAsync(request,ct);var bytes=await response.Content.ReadAsByteArrayAsync(ct);
            var detail=response.StatusCode==status?"":Wire.HttpError.Parser.ParseFrom(bytes).Detail;
            Assert.True(response.StatusCode==status,$"{method} {path}: expected {status}, got {response.StatusCode}; {detail}");
            Assert.Equal(HttpProtocolRegistry.MediaType,response.Content.Headers.ContentType?.MediaType);return bytes;
        }
        await Call("GET","/api/v1/season-crafting",status:HttpStatusCode.Unauthorized);
        var owner=Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST","/api/v1/auth/local",new Wire.LocalSignInRequest{DeviceId=Guid.NewGuid().ToString(),DisplayName="CraftOwner-"+Guid.NewGuid().ToString("N")[..8]}));
        var peer=Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST","/api/v1/auth/local",new Wire.LocalSignInRequest{DeviceId=Guid.NewGuid().ToString(),DisplayName="CraftPeer-"+Guid.NewGuid().ToString("N")[..8]}));
        var player=Guid.Parse(owner.Player.UserId);var other=Guid.Parse(peer.Player.UserId);Assert.NotEqual(player,other);
        var day=DateOnly.FromDateTime(TimeZoneInfo.ConvertTime(DateTimeOffset.UtcNow,TimeZoneInfo.FindSystemTimeZoneById(SeasonDefinition.TimeZoneId)).DateTime);
        var config=GameConfigCatalog.Current;var definition=SeasonDefinition.FromCalendarDays("craft-api",day,config.Version,"season-equipment-v1",highestOpenDifficulty:5);
        var seasons=new SeasonRepository(database.DataSource,TimeProvider.System);await seasons.PublishAsync(definition,config.ContentHash,ct);
        foreach(var id in new[]{player,other})
        {
            await seasons.EnsurePlayerAsync(id,definition.ContextFor(0),ct);
            await using var unlock=database.DataSource.CreateCommand("UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1");
            unlock.Parameters.AddWithValue(id);await unlock.ExecuteNonQueryAsync(ct);
        }
        await seasons.ApplyAsync(player,definition.ContextFor(0),0,5000,77,"test.fund","fund",SeasonWalletPurpose.General,ct);
        await using(var connection=await database.DataSource.OpenConnectionAsync(ct))
        await using(var transaction=await connection.BeginTransactionAsync(ct))
        {
            await SeasonRepository.ApplyWithinTransactionAsync(connection,transaction,player,definition.ContextFor(0),0,0,0,"test.blueprints","marks",SeasonWalletPurpose.General,DateTimeOffset.UtcNow,new string('a',64),ct,50,50);
            await transaction.CommitAsync(ct);
        }
        client.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",owner.AccessToken);
        var state=Wire.SeasonCraftingResponse.Parser.ParseFrom(await Call("GET","/api/v1/season-crafting"));
        Assert.Equal(50,state.Wallet.BlueprintMarks);Assert.Equal(50,state.Wallet.OrangeBlueprintMarks);Assert.Equal(77,state.Wallet.ChallengeMarks);
        var craft=new Wire.CraftEquipmentRequest{SeasonId=definition.SeasonId,Quality="Purple",Slot="Hands",Element="Water",WishedEffect="Vitality",ExpectedWalletVersion=state.Wallet.Version};
        var firstBytes=await Call("POST","/api/v1/season-crafting/craft",craft,"craft-first");
        var first=Wire.CraftEquipmentResponse.Parser.ParseFrom(firstBytes);
        Assert.Equal("Hands",first.Equipment.Slot);Assert.Equal("Water",first.Equipment.Element);Assert.Equal(4,first.BlueprintsSpent);
        Assert.Equal(firstBytes,await Call("POST","/api/v1/season-crafting/craft",craft,"craft-first"));
        var learn=new Wire.LearnSeasonRecipeRequest{SeasonId=definition.SeasonId,EquipmentId=first.Equipment.InstanceId,ExpectedVersion=first.Equipment.Version};
        var learned=Wire.LearnSeasonRecipeResponse.Parser.ParseFrom(await Call("POST","/api/v1/season-crafting/recipes/learn",learn,"learn-first"));
        Assert.True(learned.Equipment.RecipeExtracted);Assert.Equal(first.Equipment.EffectAffix,learned.Recipe.EffectAffix);
        state=Wire.SeasonCraftingResponse.Parser.ParseFrom(await Call("GET","/api/v1/season-crafting"));
        var second=Wire.CraftEquipmentResponse.Parser.ParseFrom(await Call("POST","/api/v1/season-crafting/craft",new Wire.CraftEquipmentRequest{SeasonId=definition.SeasonId,Quality="Purple",Slot="Feet",Element="Fire",WishedEffect="Piercing",ExpectedWalletVersion=state.Wallet.Version},"craft-body"));
        var path=$"/api/v1/season-crafting/reforge-quote?seasonId={definition.SeasonId}&recipeId={learned.Recipe.RecipeId}&bodyEquipmentId={second.Equipment.InstanceId}";
        client.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",peer.AccessToken);
        await Call("GET",path,status:HttpStatusCode.BadRequest);
        client.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",owner.AccessToken);
        var quote=Wire.ReforgeQuoteResponse.Parser.ParseFrom(await Call("GET",path));Assert.True(quote.CanReforge);Assert.Equal(1,quote.FragmentCost);
        var rebuild=new Wire.ReforgeEquipmentRequest{SeasonId=definition.SeasonId,RecipeId=learned.Recipe.RecipeId,BodyEquipmentId=second.Equipment.InstanceId,ExpectedBodyVersion=quote.Before.Version,ExpectedWalletVersion=quote.ExpectedWalletVersion};
        var rebuiltBytes=await Call("POST","/api/v1/season-crafting/reforge",rebuild,"rebuild-action");var result=Wire.ReforgeEquipmentResponse.Parser.ParseFrom(rebuiltBytes);
        Assert.Equal(second.Equipment.InstanceId,result.Equipment.InstanceId);Assert.Equal(first.Equipment.Slot,result.Equipment.Slot);
        Assert.Equal("TemplateReforge",result.Equipment.SourceKind);Assert.Equal(4999,result.Wallet.EquipmentFragments);
        Assert.Equal(42,result.Wallet.BlueprintMarks);Assert.Equal(50,result.Wallet.OrangeBlueprintMarks);Assert.Equal(77,result.Wallet.ChallengeMarks);
        Assert.Equal(rebuiltBytes,await Call("POST","/api/v1/season-crafting/reforge",rebuild,"rebuild-action"));
        await Call("POST","/api/v1/season-crafting/recipes/learn",new Wire.LearnSeasonRecipeRequest{SeasonId=definition.SeasonId,EquipmentId=result.Equipment.InstanceId,ExpectedVersion=result.Equipment.Version},"relearn-blocked",HttpStatusCode.BadRequest);
        rebuild.ExpectedBodyVersion++;await Call("POST","/api/v1/season-crafting/reforge",rebuild,"rebuild-action",HttpStatusCode.Conflict);
        Assert.Equal(2L,await database.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE season_id=$1",definition.SeasonId));
    }
}
