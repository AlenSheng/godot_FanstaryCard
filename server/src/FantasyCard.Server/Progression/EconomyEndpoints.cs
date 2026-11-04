using FantasyCard.Server.ProtobufHttp;
using FantasyCard.Contracts.Progression;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Domain.Players;
using System.Globalization;

namespace FantasyCard.Server.Progression;

public static class EconomyEndpoints
{
    public static IServiceCollection AddEconomyModule(this IServiceCollection services)
    {
        services.AddSingleton<EconomyRepository>();
        services.AddSingleton<SeasonActivityRepository>();
        services.AddSingleton<RedEquipmentQuotaRepository>();
        services.AddSingleton<SeasonRedMintRepository>();
        services.AddSingleton<SeasonRedDropCoordinator>();
        services.AddHostedService<RewardRefreshRecoveryWorker>();
        services.AddSingleton<EconomyReconciliationRepository>();
        services.AddHostedService<EconomyMaintenanceWorker>();
        return services;
    }

    public static IEndpointRouteBuilder MapEconomyEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapSeasonActivityEndpoints();
        var economy = endpoints.MapGroup("/api/v1/economy").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Economy");
        economy.MapGet("/context", GetEconomyContextAsync)
            .RequireRateLimiting(RequestLimitOptions.ReadPolicy)
            .Produces<EconomyContextResponse>()
            .ProducesProblem(401);
        economy.MapGet("/wallet", GetWalletAsync)
            .RequireRateLimiting(RequestLimitOptions.ReadPolicy)
            .Produces<WalletResponse>()
            .ProducesProblem(401);

        var shop = endpoints.MapGroup("/api/v1/shop").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Economy");
        shop.MapGet("/", GetShopAsync).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<ShopResponse>().ProducesProblem(401);
        shop.MapGet("/context", GetShopContextAsync).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<ShopInventoryContextResponse>().ProducesProblem(401);
        shop.MapPost("/refresh", RefreshShopAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<ShopResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        shop.MapPost("/purchases", PurchaseAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<ShopPurchaseResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);

        var market = endpoints.MapGroup("/api/v1/market").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Economy");
        market.MapGet("/", GetMarketAsync).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<IReadOnlyList<MarketListingResponse>>().ProducesProblem(401);
        market.MapGet("/context", GetMarketContextAsync).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<MarketInventoryContextResponse>().ProducesProblem(401);
        market.MapPost("/listings", ListAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<MarketListingResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        market.MapPost("/{listingId:guid}/purchase", PurchaseMarketAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<MarketPurchaseResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        market.MapDelete("/listings/{listingId:guid}", CancelListingAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces(204).ProducesProblem(401).ProducesProblem(409);
        market.MapPost("/listings/{listingId:guid}/relist", RelistMarketAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<MarketListingResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        market.MapGet("/returns", GetMarketReturnsAsync).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<MarketReturnsResponse>().ProducesProblem(401);
        market.MapPost("/returns/{returnId:guid}/claim", ClaimMarketReturnAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<EquipmentResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        return endpoints;
    }

    private static async Task<IResult> GetEconomyContextAsync(
        HttpContext context,
        IdentityService identity,
        EconomyRepository economy,
        ProgressionRepository progression,
        SeasonRepository seasons,
        TimeProvider clock,
        CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct);
        if (player is null) return context.UnauthorizedProblem();

        var schedule=await seasons.GetScheduleAtAsync(clock.GetUtcNow(),ct);
        var shopTask = economy.GetShopForScheduleAsync(player.UserId,schedule,ct);
        var marketTask = economy.GetMarketForScheduleAsync(schedule,ct,GamePage.Read(context).Limit,GamePage.Read(context).Offset);
        var inventoryTask = progression.GetInventoryForScheduleAsync(player.UserId,schedule,ct);
        await Task.WhenAll(shopTask, marketTask, inventoryTask);

        return Results.Ok(new EconomyContextResponse(
            shopTask.Result,
            marketTask.Result,
            inventoryTask.Result));
    }

    private static async Task<IResult> GetShopAsync(HttpContext context, IdentityService identity, EconomyRepository repository, CancellationToken ct)
    { var player = await context.AuthenticatePlayerAsync(identity, ct); return player is null ? context.UnauthorizedProblem() : Results.Ok(await repository.GetShopAsync(player.UserId, ct)); }

    private static async Task<IResult> GetWalletAsync(HttpContext context, IdentityService identity, EconomyRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct);
        return player is null ? context.UnauthorizedProblem() : Results.Ok(await repository.GetWalletAsync(player.UserId, ct));
    }

    private static async Task<IResult> GetShopContextAsync(
        HttpContext context,
        IdentityService identity,
        EconomyRepository economy,
        ProgressionRepository progression,
        SeasonRepository seasons,
        TimeProvider clock,
        CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct);
        if (player is null) return context.UnauthorizedProblem();
        var schedule=await seasons.GetScheduleAtAsync(clock.GetUtcNow(),ct);
        var shopTask = economy.GetShopForScheduleAsync(player.UserId,schedule,ct);
        var inventoryTask = progression.GetInventoryForScheduleAsync(player.UserId,schedule,ct);
        await Task.WhenAll(shopTask, inventoryTask);
        return Results.Ok(new ShopInventoryContextResponse(shopTask.Result, inventoryTask.Result));
    }

    private static async Task<IResult> RefreshShopAsync(
        HttpContext context,
        IdentityService identity,
        EconomyRepository repository,
        ConnectionRegistry connections,
        RealtimeEventStore eventStore,
        CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct);
        if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try
        {
            var refresh = await repository.RefreshShopAsync(player.UserId, requestId, ct);
            if (!refresh.Replayed)
                NotifyClientsAfterResponse(context, connections, eventStore, "shop.refresh", refresh.Shop.ResetKey);
            return Results.Ok(refresh.Shop);
        }
        catch (IdempotencyConflictException)
        {
            return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used for another shop refresh.");
        }
        catch (InvalidOperationException exception)
        {
            return Problem(context, 409, "Shop refresh rejected", exception.Message);
        }
        catch (DomainValidationException exception) { return Problem(context,409,"Shop refresh rejected",exception.Message); }
    }

    private static async Task<IResult> PurchaseAsync(GameBody<PurchaseShopRequest> request, HttpContext context, IdentityService identity, EconomyRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try { return Results.Ok(await repository.PurchaseAsync(player.UserId, requestId, request, ct)); }
        catch (IdempotencyConflictException) { return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used with a different request."); }
        catch (InvalidOperationException ex) { return Problem(context, 409, "Purchase rejected", ex.Message); }
        catch (DomainValidationException ex) { return Problem(context,409,"Purchase rejected",ex.Message); }
    }

    private static async Task<IResult> GetMarketAsync(HttpContext context, IdentityService identity, EconomyRepository repository, CancellationToken ct)
    { var player = await context.AuthenticatePlayerAsync(identity, ct); return player is null ? context.UnauthorizedProblem() : Results.Ok(await repository.GetMarketAsync(ct, GamePage.Read(context).Limit, GamePage.Read(context).Offset,ReadMarketQuery(context))); }

    private static async Task<IResult> GetMarketContextAsync(
        HttpContext context,
        IdentityService identity,
        EconomyRepository economy,
        ProgressionRepository progression,
        SeasonRepository seasons,
        TimeProvider clock,
        CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct);
        if (player is null) return context.UnauthorizedProblem();
        var at=clock.GetUtcNow();var schedule=await seasons.GetScheduleAtAsync(at,ct);
        var listingsTask=economy.GetMarketForScheduleAsync(schedule,ct,GamePage.Read(context).Limit,GamePage.Read(context).Offset,ReadMarketQuery(context));
        var inventoryTask=progression.GetInventoryForScheduleAsync(player.UserId,schedule,ct);
        var policyTask=economy.GetMarketPolicyForScheduleAsync(player.UserId,schedule,at,ct);
        var ownTask=economy.GetOwnMarketListingsAsync(player.UserId,ct);var returnsTask=economy.GetMarketReturnsAsync(player.UserId,ct);
        await Task.WhenAll(listingsTask,inventoryTask,policyTask,ownTask,returnsTask);
        return Results.Ok(new MarketInventoryContextResponse(listingsTask.Result,inventoryTask.Result,policyTask.Result,ownTask.Result,returnsTask.Result.Items,returnsTask.Result.NextOffset));
    }

    private static async Task<IResult> ListAsync(GameBody<CreateMarketListingRequest> request, HttpContext context, IdentityService identity, EconomyRepository repository, ConnectionRegistry connections, RealtimeEventStore eventStore, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try
        {
            var listing = await repository.ListAsync(player.UserId, requestId, request, ct);
            var snapshot = await repository.GetListingForEventAsync(listing.ListingId, ct);
            if (snapshot is not null)
                NotifyClientsAfterResponse(context, connections, eventStore, "market.listed", listing.ListingId.ToString("D"), snapshot);
            return Results.Created("/api/v1/market/listings", listing);
        }
        catch (IdempotencyConflictException) { return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used with a different request."); }
        catch (InvalidOperationException ex) { return Problem(context, 409, "Listing rejected", ex.Message); }
        catch (DomainValidationException ex) { return Problem(context,409,"Listing rejected",ex.Message); }
    }

    private static async Task<IResult> PurchaseMarketAsync(Guid listingId, HttpContext context, IdentityService identity, EconomyRepository repository, ConnectionRegistry connections, RealtimeEventStore eventStore, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        if (!long.TryParse(context.Request.Query["expectedVersion"], out var version)) return Problem(context, 400, "Invalid version", "expectedVersion is required.");
        try
        {
            var purchase = await repository.PurchaseMarketAsync(player.UserId, requestId, listingId, version, ct,ReadMarketExpectation(context));
            var snapshot = await repository.GetListingForEventAsync(listingId, ct);
            if (snapshot is not null)
            {
                var sellerWallet = await repository.GetWalletAsync(snapshot.SellerId, ct);
                NotifyClientsAfterResponse(context, connections, eventStore, "market.sold", listingId.ToString("D"), snapshot,
                    snapshot.SeasonId is null?sellerWallet.Gold:null,true);
            }
            return Results.Ok(purchase);
        }
        catch (IdempotencyConflictException) { return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used with a different request."); }
        catch (InvalidOperationException ex) { return Problem(context, 409, "Purchase rejected", ex.Message); }
        catch (DomainValidationException ex) { return Problem(context,409,"Purchase rejected",ex.Message); }
    }

    private static async Task<IResult> CancelListingAsync(Guid listingId, HttpContext context, IdentityService identity, EconomyRepository repository, ConnectionRegistry connections, RealtimeEventStore eventStore, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try
        {
            await repository.CancelListingAsync(player.UserId, listingId, requestId, ct);
            var snapshot = await repository.GetListingForEventAsync(listingId, ct);
            if (snapshot is not null)
                NotifyClientsAfterResponse(context, connections, eventStore, "market.cancelled", listingId.ToString("D"), snapshot);
            return Results.NoContent();
        }
        catch (IdempotencyConflictException) { return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used for another listing."); }
        catch (InvalidOperationException ex) { return Problem(context, 409, "Cancel rejected", ex.Message); }
        catch (DomainValidationException ex) { return Problem(context,409,"Cancel rejected",ex.Message); }
    }

    private static MarketQuery ReadMarketQuery(HttpContext context)
    {
        static string? Optional(HttpContext source,string name)=>source.Request.Query[name].ToString() is {Length:>0} value?value:null;
        var currency=Optional(context,"currency")??"Gold";var sort=Optional(context,"sort")??"recent";
        var quality=Optional(context,"quality");var slot=Optional(context,"slot");var element=Optional(context,"element");var effect=Optional(context,"effect");
        var material=Optional(context,"materialsOnly");
        if(currency is not ("Gold" or "Diamond") || sort is not ("recent" or "price" or "material") ||
            quality is not (null or "White" or "Green" or "Blue" or "Purple" or "Orange" or "Red") ||
            slot is not (null or "Head" or "Chest" or "Hands" or "Legs" or "Feet") ||
            element is not (null or "Wood" or "Fire" or "Earth" or "Metal" or "Water") ||
            effect is not (null or "Piercing" or "Bulwark" or "Vitality") || material is not (null or "true" or "false"))
            throw new BadHttpRequestException("Invalid market filter.",400);
        return new(currency,quality,slot,element,effect,sort=="material" || material=="true",sort=="price");
    }

    private static MarketPurchaseExpectation? ReadMarketExpectation(HttpContext context)
    {
        var currency=context.Request.Query["currency"].ToString();var price=context.Request.Query["expectedPrice"].ToString();var season=context.Request.Query["seasonId"].ToString();
        if(currency.Length==0 && price.Length==0 && season.Length==0)return null;
        if(currency is not ("Gold" or "Diamond") || !long.TryParse(price,NumberStyles.None,CultureInfo.InvariantCulture,out var amount) || amount<1)
            throw new BadHttpRequestException("Confirm a valid market currency and expectedPrice.",400);
        return new(currency,amount,season.Length==0?null:season);
    }

    private static async Task<IResult> GetMarketReturnsAsync(HttpContext context,IdentityService identity,EconomyRepository repository,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();var page=GamePage.Read(context);
        return Results.Ok(await repository.GetMarketReturnsAsync(player.UserId,ct,page.Limit,page.Offset));
    }

    private static async Task<IResult> RelistMarketAsync(Guid listingId,GameBody<RelistMarketListingRequest> request,HttpContext context,IdentityService identity,
        EconomyRepository repository,ConnectionRegistry connections,RealtimeEventStore eventStore,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        var key=IdempotencyKeys.Read(context);if(key is null)return IdempotencyKeys.InvalidProblem(context);
        try
        {
            var result=await repository.RelistMarketAsync(player.UserId,listingId,key,request,ct);
            var previous=await repository.GetListingForEventAsync(listingId,ct);var current=await repository.GetListingForEventAsync(result.ListingId,ct);
            if(previous is not null)NotifyClientsAfterResponse(context,connections,eventStore,"market.cancelled",listingId.ToString("D"),previous);
            if(current is not null)NotifyClientsAfterResponse(context,connections,eventStore,"market.listed",result.ListingId.ToString("D"),current);
            return Results.Ok(result);
        }
        catch(IdempotencyConflictException){return Problem(context,409,"Idempotency conflict","The Idempotency-Key was already used with another relisting request.");}
        catch(DomainValidationException error){return Problem(context,409,"Relisting rejected",error.Message);}
        catch(InvalidOperationException error){return Problem(context,409,"Relisting rejected",error.Message);}
    }

    private static async Task<IResult> ClaimMarketReturnAsync(Guid returnId,GameBody<ClaimMarketReturnRequest> request,HttpContext context,IdentityService identity,
        EconomyRepository repository,ConnectionRegistry connections,RealtimeEventStore eventStore,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        var key=IdempotencyKeys.Read(context);if(key is null)return IdempotencyKeys.InvalidProblem(context);
        try
        {
            var result=await repository.ClaimMarketReturnAsync(player.UserId,returnId,key,request,ct);var trace=context.TraceIdentifier;
            context.Response.OnCompleted(async()=>await connections.SendPresentationAsync(player.UserId,
                eventStore.Create(player.UserId,"inventory.changed",trace,new InventoryChangedEventPayload("market.returned",result.InstanceId.ToString("D")))));
            return Results.Ok(result);
        }
        catch(IdempotencyConflictException){return Problem(context,409,"Idempotency conflict","The Idempotency-Key was already used with another return request.");}
        catch(DomainValidationException error){return Problem(context,409,"Market return rejected",error.Message);}
        catch(InvalidOperationException error){return Problem(context,409,"Market return rejected",error.Message);}
    }

    private static void NotifyClientsAfterResponse(
        HttpContext context,
        ConnectionRegistry connections,
        RealtimeEventStore eventStore,
        string action,
        string itemId,
        MarketListingResponse? listing = null,
        long? sellerGoldAfter = null,bool sellerWalletChanged=false)
    {
        var traceId = context.TraceIdentifier;
        context.Response.OnCompleted(async () =>
        {
            foreach (var batch in connections.ConnectedPlayerIds.Chunk(16))
            {
                await Task.WhenAll(batch.Select(async playerId =>
                {
                    var message = eventStore.Create(playerId, "inventory.changed", traceId,
                        new InventoryChangedEventPayload(action, itemId, listing,
                            listing?.SellerId==playerId?sellerGoldAfter:null,sellerWalletChanged && listing?.SellerId==playerId));
                    await connections.SendPresentationAsync(playerId, message);
                }));
            }
        });
    }

    private static IResult Problem(HttpContext context, int status, string title, string detail) => Results.Problem(statusCode: status, title: title, detail: detail, extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
}
