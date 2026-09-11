using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;

namespace FantasyCard.Server.Progression;

public static class ProgressionEndpoints
{
    public static IServiceCollection AddProgressionModule(this IServiceCollection services)
    {
        services.AddSingleton<ProgressionRepository>();
        services.AddSingleton<MailRepository>();
        return services;
    }

    public static IEndpointRouteBuilder MapProgressionEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var cards = endpoints.MapGroup("/api/v1/cards").WithTags("Progression");
        var mail = endpoints.MapGroup("/api/v1/mail").WithTags("Mail");
        mail.MapGet("/", ListMailAsync).Produces<IReadOnlyList<object>>().ProducesProblem(401);
        mail.MapPost("/{mailId:guid}/claim", ClaimMailAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).ProducesProblem(401).ProducesProblem(404);
        cards.MapGet("/", GetCardsAsync).Produces<IReadOnlyList<CardResponse>>().ProducesProblem(401);
        cards.MapPost("/{cardId}/craft", CraftCardAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<CardMutationResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        cards.MapPost("/{cardId}/dismantle", DismantleCardAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<CardMutationResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        cards.MapPost("/{cardId}/upgrade", UpgradeCardAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<CardMutationResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);

        var decks = endpoints.MapGroup("/api/v1/decks").WithTags("Progression");
        decks.MapGet("/", GetDecksAsync).Produces<IReadOnlyList<DeckResponse>>().ProducesProblem(401);
        decks.MapPut("/{heroClass}", SaveDeckAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<DeckResponse>()
            .ProducesProblem(400)
            .ProducesProblem(401)
            .ProducesProblem(404)
            .ProducesProblem(409);

        var inventory = endpoints.MapGroup("/api/v1/inventory").WithTags("Progression");
        inventory.MapGet("/", GetInventoryAsync).Produces<InventoryResponse>().ProducesProblem(401);

        var loadouts = endpoints.MapGroup("/api/v1/loadouts").WithTags("Progression");
        loadouts.MapGet("/{heroClass}", GetLoadoutAsync)
            .Produces<LoadoutResponse>()
            .ProducesProblem(400)
            .ProducesProblem(401)
            .ProducesProblem(404);
        loadouts.MapPut("/{heroClass}", SaveLoadoutAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<LoadoutResponse>()
            .ProducesProblem(400)
            .ProducesProblem(401)
            .ProducesProblem(404)
            .ProducesProblem(409);

        var equipment = endpoints.MapGroup("/api/v1/equipment").WithTags("Progression");
        equipment.MapGet("/{equipmentId:guid}/enhancement-quote", EquipmentEnhancementQuoteAsync)
            .Produces<EnhancementQuoteResponse>().ProducesProblem(401).ProducesProblem(404);
        equipment.MapPost("/{equipmentId:guid}/enhance", EnhanceEquipmentAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<EnhanceResult>()
            .ProducesProblem(400)
            .ProducesProblem(401)
            .ProducesProblem(404)
            .ProducesProblem(409);

        var weapons = endpoints.MapGroup("/api/v1/class-weapons").WithTags("Progression");
        weapons.MapGet("/{heroClass}/enhancement-quote", WeaponEnhancementQuoteAsync)
            .Produces<EnhancementQuoteResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(404);
        weapons.MapPost("/{heroClass}/enhance", EnhanceWeaponAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<EnhanceResult>()
            .ProducesProblem(400)
            .ProducesProblem(401)
            .ProducesProblem(404)
            .ProducesProblem(409);
        return endpoints;
    }

    private static Task<IResult> CraftCardAsync(
        string cardId, CardMutationRequest request, HttpContext context,
        IdentityService identityService, ProgressionRepository repository, CancellationToken cancellationToken) =>
        MutateCardAsync(cardId, request, true, context, identityService, repository, cancellationToken);

    private static Task<IResult> DismantleCardAsync(
        string cardId, CardMutationRequest request, HttpContext context,
        IdentityService identityService, ProgressionRepository repository, CancellationToken cancellationToken) =>
        MutateCardAsync(cardId, request, false, context, identityService, repository, cancellationToken);

    private static Task<IResult> UpgradeCardAsync(
        string cardId, CardMutationRequest request, HttpContext context,
        IdentityService identityService, ProgressionRepository repository, CancellationToken cancellationToken) =>
        MutateCardAsync(cardId, request, false, context, identityService, repository, cancellationToken, upgrade: true);

    private static async Task<IResult> MutateCardAsync(
        string cardId, CardMutationRequest request, bool craft, HttpContext context,
        IdentityService identityService, ProgressionRepository repository, CancellationToken cancellationToken, bool upgrade = false)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        if (request.ExpectedVersion < 0)
            return Problem(context, 400, "Invalid version", "expectedVersion must be nonnegative.");
        try
        {
            return Results.Ok(upgrade
                ? await repository.UpgradeCardAsync(player.UserId, cardId, requestId, request, cancellationToken)
                : await repository.MutateCardAsync(player.UserId, cardId, requestId, request, craft, cancellationToken));
        }
        catch (IdempotencyConflictException)
        {
            return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used with a different request.");
        }
        catch (DomainValidationException exception)
        {
            return Problem(context, 409, "Card operation rejected", exception.Message);
        }
    }

    private static async Task<IResult> ListMailAsync(HttpContext context, IdentityService identityService, MailRepository repository, CancellationToken ct)
    { var player = await context.AuthenticatePlayerAsync(identityService, ct); return player is null ? context.UnauthorizedProblem() : Results.Ok(await repository.ListAsync(player.UserId, ct)); }
    private static async Task<IResult> ClaimMailAsync(Guid mailId, HttpContext context, IdentityService identityService, MailRepository repository, CancellationToken ct)
    { var player = await context.AuthenticatePlayerAsync(identityService, ct); if (player is null) return context.UnauthorizedProblem(); return await repository.ClaimAsync(player.UserId, mailId, ct) ? Results.Ok() : Results.NotFound(); }

    private static async Task<IResult> GetInventoryAsync(
        HttpContext context,
        IdentityService identityService,
        ProgressionRepository repository,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        return player is null
            ? context.UnauthorizedProblem()
            : Results.Ok(await repository.GetInventoryAsync(player.UserId, cancellationToken));
    }

    private static async Task<IResult> SaveLoadoutAsync(
        string heroClass,
        UpdateLoadoutRequest request,
        HttpContext context,
        IdentityService identityService,
        ProgressionRepository repository,
        TimeProvider timeProvider,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        if (!Enum.TryParse<HeroClassDto>(heroClass, true, out var dto) || !Enum.IsDefined(dto))
            return Problem(context, 400, "Unknown hero class", "Use Priest, Mage, or Guardian.");
        if (request.EquipmentIds is null || request.EquipmentIds.Count != 5)
            return Problem(context, 400, "Invalid loadout", "Exactly five equipment slots are required.");
        try
        {
            var result = await repository.SaveLoadoutAsync(
                player.UserId, (HeroClass)(int)dto, request.EquipmentIds,
                requestId, request.ExpectedVersion, timeProvider.GetUtcNow(), cancellationToken);
            return result.Status switch
            {
                SaveLoadoutStatus.Updated => Results.Ok(result.Loadout),
                SaveLoadoutStatus.VersionConflict => Problem(context, 409, "Loadout changed", "Reload and retry."),
                SaveLoadoutStatus.NotFound => Results.NotFound(),
                _ => Problem(context, 409, "Equipment unavailable", result.Detail!)
            };
        }
        catch (DomainValidationException exception)
        {
            return Problem(context, 400, "Invalid loadout", exception.Message);
        }
        catch (IdempotencyConflictException)
        {
            return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used with a different request.");
        }
    }

    private static async Task<IResult> GetLoadoutAsync(
        string heroClass,
        HttpContext context,
        IdentityService identityService,
        ProgressionRepository repository,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        if (!Enum.TryParse<HeroClassDto>(heroClass, true, out var dto) || !Enum.IsDefined(dto))
            return Problem(context, 400, "Unknown hero class", "Use Priest, Mage, or Guardian.");
        var loadout = await repository.GetLoadoutAsync(
            player.UserId, (HeroClass)(int)dto, cancellationToken);
        return loadout is null ? Results.NotFound() : Results.Ok(loadout);
    }

    private static async Task<IResult> EquipmentEnhancementQuoteAsync(
        Guid equipmentId, HttpContext context, IdentityService identityService,
        ProgressionRepository repository, CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        var quote = await repository.GetEquipmentEnhancementQuoteAsync(player.UserId, equipmentId, cancellationToken);
        return quote is null ? Problem(context, 404, "Equipment not found", "Equipment was not found.") : Results.Ok(quote);
    }

    private static async Task<IResult> WeaponEnhancementQuoteAsync(
        string heroClass, HttpContext context, IdentityService identityService,
        ProgressionRepository repository, CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        if (!Enum.TryParse<HeroClassDto>(heroClass, true, out var dto) || !Enum.IsDefined(dto))
            return Problem(context, 400, "Unknown hero class", "Use Priest, Mage, or Guardian.");
        var quote = await repository.GetWeaponEnhancementQuoteAsync(player.UserId, (HeroClass)(int)dto, cancellationToken);
        return quote is null ? Problem(context, 404, "Class weapon not found", "Class weapon was not found.") : Results.Ok(quote);
    }

    private static async Task<IResult> EnhanceEquipmentAsync(
        Guid equipmentId,
        EnhanceEquipmentRequest request,
        HttpContext context,
        IdentityService identityService,
        ProgressionRepository repository,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try
        {
            return Results.Ok(await repository.EnhanceEquipmentAsync(
                player.UserId, equipmentId, requestId, request, cancellationToken));
        }
        catch (IdempotencyConflictException)
        {
            return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used with a different request.");
        }
        catch (DomainValidationException exception)
        {
            return Problem(context, 400, "Cannot enhance equipment", exception.Message);
        }
    }

    private static async Task<IResult> EnhanceWeaponAsync(
        string heroClass,
        EnhanceEquipmentRequest request,
        HttpContext context,
        IdentityService identityService,
        ProgressionRepository repository,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        if (!Enum.TryParse<HeroClassDto>(heroClass, true, out var dto) || !Enum.IsDefined(dto))
            return Problem(context, 400, "Unknown hero class", "Use Priest, Mage, or Guardian.");
        try
        {
            return Results.Ok(await repository.EnhanceWeaponAsync(
                player.UserId, (HeroClass)(int)dto, requestId, request.ExpectedVersion, cancellationToken));
        }
        catch (IdempotencyConflictException)
        {
            return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used with a different request.");
        }
        catch (DomainValidationException exception)
        {
            return Problem(context, 400, "Cannot enhance weapon", exception.Message);
        }
    }

    private static async Task<IResult> GetCardsAsync(
        HttpContext context,
        IdentityService identityService,
        ProgressionRepository repository,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        return player is null
            ? context.UnauthorizedProblem()
            : Results.Ok(await repository.GetCardsAsync(player.UserId, cancellationToken));
    }

    private static async Task<IResult> GetDecksAsync(
        HttpContext context,
        IdentityService identityService,
        ProgressionRepository repository,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        return player is null
            ? context.UnauthorizedProblem()
            : Results.Ok(await repository.GetDecksAsync(player.UserId, cancellationToken));
    }

    private static async Task<IResult> SaveDeckAsync(
        string heroClass,
        UpdateDeckRequest request,
        HttpContext context,
        IdentityService identityService,
        ProgressionRepository repository,
        TimeProvider timeProvider,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null)
        {
            return context.UnauthorizedProblem();
        }

        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null)
        {
            return IdempotencyKeys.InvalidProblem(context);
        }

        if (!Enum.TryParse<HeroClassDto>(heroClass, true, out var heroClassDto) || !Enum.IsDefined(heroClassDto))
        {
            return Problem(context, 400, "Unknown hero class", "Use Priest, Mage, or Guardian.");
        }

        if (request.CardIds is null)
        {
            return Problem(context, 400, "Invalid deck", "cardIds is required.");
        }

        try
        {
            var result = await repository.SaveDeckAsync(
                player.UserId,
                (HeroClass)(int)heroClassDto,
                request.CardIds,
                requestId,
                request.ExpectedVersion,
                timeProvider.GetUtcNow(),
                cancellationToken);
            return result.Status switch
            {
                SaveDeckStatus.Updated => Results.Ok(result.Deck),
                SaveDeckStatus.VersionConflict => Problem(
                    context,
                    409,
                    "Deck changed",
                    "Reload the deck and retry with its latest version."),
                _ => Results.NotFound()
            };
        }
        catch (DomainValidationException exception)
        {
            return Problem(context, 400, "Invalid deck", exception.Message);
        }
        catch (IdempotencyConflictException)
        {
            return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used with a different request.");
        }
    }

    private static IResult Problem(HttpContext context, int status, string title, string detail) =>
        Results.Problem(
            statusCode: status,
            title: title,
            detail: detail,
            extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
}
