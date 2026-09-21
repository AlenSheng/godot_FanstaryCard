using FantasyCard.Contracts.Progression;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Realtime;

namespace FantasyCard.Server.Progression;

public static class EconomyEndpoints
{
    public static IServiceCollection AddEconomyModule(this IServiceCollection services)
    {
        services.AddSingleton<EconomyRepository>();
        services.AddSingleton<RedEquipmentQuotaRepository>();
        services.AddHostedService<RewardRefreshRecoveryWorker>();
        services.AddSingleton<EconomyReconciliationRepository>();
        services.AddHostedService<EconomyMaintenanceWorker>();
        return services;
    }

    public static IEndpointRouteBuilder MapEconomyEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var economy = endpoints.MapGroup("/api/v1/economy").WithTags("Economy");
        economy.MapGet("/context", GetEconomyContextAsync)
            .RequireRateLimiting(RequestLimitOptions.ReadPolicy)
            .Produces<EconomyContextResponse>()
            .ProducesProblem(401);

        var shop = endpoints.MapGroup("/api/v1/shop").WithTags("Economy");
        shop.MapGet("/", GetShopAsync).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<ShopResponse>().ProducesProblem(401);
        shop.MapGet("/context", GetShopContextAsync).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<ShopInventoryContextResponse>().ProducesProblem(401);
        shop.MapPost("/refresh", RefreshShopAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<ShopResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        shop.MapPost("/purchases", PurchaseAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<ShopPurchaseResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);

        var market = endpoints.MapGroup("/api/v1/market").WithTags("Economy");
        market.MapGet("/", GetMarketAsync).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<IReadOnlyList<MarketListingResponse>>().ProducesProblem(401);
        market.MapGet("/context", GetMarketContextAsync).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<MarketInventoryContextResponse>().ProducesProblem(401);
        market.MapPost("/listings", ListAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<MarketListingResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        market.MapPost("/{listingId:guid}/purchase", PurchaseMarketAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<MarketPurchaseResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        market.MapDelete("/listings/{listingId:guid}", CancelListingAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces(204).ProducesProblem(401).ProducesProblem(409);
        return endpoints;
    }

    private static async Task<IResult> GetEconomyContextAsync(
        HttpContext context,
        IdentityService identity,
        EconomyRepository economy,
        ProgressionRepository progression,
        CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct);
        if (player is null) return context.UnauthorizedProblem();

        var shopTask = economy.GetShopAsync(player.UserId, ct);
        var marketTask = economy.GetMarketAsync(ct);
        var inventoryTask = progression.GetInventoryAsync(player.UserId, ct);
        await Task.WhenAll(shopTask, marketTask, inventoryTask);

        return Results.Ok(new EconomyContextResponse(
            shopTask.Result,
            marketTask.Result,
            inventoryTask.Result));
    }

    private static async Task<IResult> GetShopAsync(HttpContext context, IdentityService identity, EconomyRepository repository, CancellationToken ct)
    { var player = await context.AuthenticatePlayerAsync(identity, ct); return player is null ? context.UnauthorizedProblem() : Results.Ok(await repository.GetShopAsync(player.UserId, ct)); }

    private static async Task<IResult> GetShopContextAsync(
        HttpContext context,
        IdentityService identity,
        EconomyRepository economy,
        ProgressionRepository progression,
        CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct);
        if (player is null) return context.UnauthorizedProblem();
        var shopTask = economy.GetShopAsync(player.UserId, ct);
        var inventoryTask = progression.GetInventoryAsync(player.UserId, ct);
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
            {
                foreach (var connectedPlayerId in connections.ConnectedPlayerIds)
                {
                    var message = eventStore.Create(
                        connectedPlayerId,
                        "inventory.changed",
                        context.TraceIdentifier,
                        new InventoryChangedEventPayload("shop.refresh", refresh.Shop.ResetKey));
                    await connections.SendPresentationAsync(connectedPlayerId, message);
                }
            }
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
    }

    private static async Task<IResult> PurchaseAsync(PurchaseShopRequest request, HttpContext context, IdentityService identity, EconomyRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try { return Results.Ok(await repository.PurchaseAsync(player.UserId, requestId, request, ct)); }
        catch (IdempotencyConflictException) { return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used with a different request."); }
        catch (InvalidOperationException ex) { return Problem(context, 409, "Purchase rejected", ex.Message); }
    }

    private static async Task<IResult> GetMarketAsync(HttpContext context, IdentityService identity, EconomyRepository repository, CancellationToken ct)
    { var player = await context.AuthenticatePlayerAsync(identity, ct); return player is null ? context.UnauthorizedProblem() : Results.Ok(await repository.GetMarketAsync(ct)); }

    private static async Task<IResult> GetMarketContextAsync(
        HttpContext context,
        IdentityService identity,
        EconomyRepository economy,
        ProgressionRepository progression,
        CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct);
        if (player is null) return context.UnauthorizedProblem();
        var listingsTask = economy.GetMarketAsync(ct);
        var inventoryTask = progression.GetInventoryAsync(player.UserId, ct);
        await Task.WhenAll(listingsTask, inventoryTask);
        return Results.Ok(new MarketInventoryContextResponse(listingsTask.Result, inventoryTask.Result));
    }

    private static async Task<IResult> ListAsync(CreateMarketListingRequest request, HttpContext context, IdentityService identity, EconomyRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try { return Results.Created("/api/v1/market/listings", await repository.ListAsync(player.UserId, requestId, request, ct)); }
        catch (IdempotencyConflictException) { return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used with a different request."); }
        catch (InvalidOperationException ex) { return Problem(context, 409, "Listing rejected", ex.Message); }
    }

    private static async Task<IResult> PurchaseMarketAsync(Guid listingId, HttpContext context, IdentityService identity, EconomyRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        if (!long.TryParse(context.Request.Query["expectedVersion"], out var version)) return Problem(context, 400, "Invalid version", "expectedVersion is required.");
        try { return Results.Ok(await repository.PurchaseMarketAsync(player.UserId, requestId, listingId, version, ct)); }
        catch (IdempotencyConflictException) { return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used with a different request."); }
        catch (InvalidOperationException ex) { return Problem(context, 409, "Purchase rejected", ex.Message); }
    }

    private static async Task<IResult> CancelListingAsync(Guid listingId, HttpContext context, IdentityService identity, EconomyRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try { await repository.CancelListingAsync(player.UserId, listingId, requestId, ct); return Results.NoContent(); }
        catch (IdempotencyConflictException) { return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used for another listing."); }
        catch (InvalidOperationException ex) { return Problem(context, 409, "Cancel rejected", ex.Message); }
    }

    private static IResult Problem(HttpContext context, int status, string title, string detail) => Results.Problem(statusCode: status, title: title, detail: detail, extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
}
