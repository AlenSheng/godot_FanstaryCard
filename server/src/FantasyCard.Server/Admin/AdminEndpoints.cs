using System.Security.Cryptography;
using System.Text;
using FantasyCard.Server.Common;

namespace FantasyCard.Server.Admin;

public static class AdminEndpoints
{
    public static IServiceCollection AddAdminModule(this IServiceCollection services)
    {
        services.AddSingleton<AdminRepository>();
        services.AddSingleton<ClientSettingsRepository>();
        services.AddSingleton<ClientSettingsHub>();
        return services;
    }

    public static IEndpointRouteBuilder MapAdminEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/admin", PageAsync).RequireRateLimiting(RequestLimitOptions.AdminPolicy);
        var admin = endpoints.MapGroup("/api/admin")
            .WithTags("Admin")
            .RequireRateLimiting(RequestLimitOptions.AdminPolicy)
            .AddEndpointFilter(AuthorizeAsync);
        admin.MapGet("/players", FindPlayersAsync);
        admin.MapGet("/players/{playerId:guid}/equipment", GetEquipmentAsync);
        admin.MapPost("/mail", SendMailAsync);
        admin.MapPost("/message", SendMessageAsync);
        admin.MapPost("/revoke", RevokeAsync);
        admin.MapPost("/ban", BanAsync);
        admin.MapPost("/unban", UnbanAsync);
        admin.MapPost("/players/unlock-all-cards", UnlockAllCardsAsync);
        admin.MapPost("/players/max-all-cards", MaxAllCardsAsync);
        admin.MapPost("/players/grant-all-equipment", GrantAllEquipmentAsync);
        admin.MapPost("/players/max-existing-equipment", MaxExistingEquipmentAsync);
        admin.MapGet("/client-settings", GetClientSettingsAsync);
        admin.MapPut("/client-settings", UpdateClientSettingsAsync);
        return endpoints;
    }

    private static bool IsSecure(HttpContext context) => context.Request.IsHttps ||
        context.Request.Headers["X-Forwarded-Proto"].ToString().Equals("https", StringComparison.OrdinalIgnoreCase);

    private static async ValueTask<object?> AuthorizeAsync(EndpointFilterInvocationContext invocation, EndpointFilterDelegate next)
    {
        var context = invocation.HttpContext;
        SetPrivateHeaders(context);
        if (!IsSecure(context)) return Results.Problem(statusCode: 403, title: "HTTPS required");
        var configured = context.RequestServices.GetRequiredService<IConfiguration>()["Admin:ApiKey"];
        if (string.IsNullOrEmpty(configured) || configured.Length < 32)
            return Results.Problem(statusCode: 503, title: "Admin system is not configured");
        var supplied = context.Request.Headers["X-Admin-Key"].ToString();
        var expectedBytes = SHA256.HashData(Encoding.UTF8.GetBytes(configured));
        var suppliedBytes = SHA256.HashData(Encoding.UTF8.GetBytes(supplied));
        if (supplied.Length is < 32 or > 256 || !CryptographicOperations.FixedTimeEquals(expectedBytes, suppliedBytes))
            return Results.Problem(statusCode: 401, title: "Admin authentication required");
        return await next(invocation);
    }

    private static void SetPrivateHeaders(HttpContext context)
    {
        context.Response.Headers.CacheControl = "private, no-store";
        context.Response.Headers["X-Content-Type-Options"] = "nosniff";
    }

    private static IResult PageAsync(HttpContext context, IConfiguration configuration)
    {
        SetPrivateHeaders(context);
        if (!IsSecure(context)) return Results.Problem(statusCode: 403, title: "HTTPS required");
        if ((configuration["Admin:ApiKey"]?.Length ?? 0) < 32)
            return Results.Problem(statusCode: 503, title: "Admin system is not configured");

        context.Response.Headers["Content-Security-Policy"] = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'none'; base-uri 'none'";
        var assembly = typeof(AdminEndpoints).Assembly;
        using var stream = assembly.GetManifestResourceStream("FantasyCard.Server.Admin.admin.html")!;
        using var reader = new StreamReader(stream);
        return Results.Content(reader.ReadToEnd(), "text/html; charset=utf-8");
    }

    private static async Task<IResult> FindPlayersAsync(string q, AdminRepository repository, CancellationToken cancellationToken)
    {
        q = q?.Trim() ?? "";
        if (q.Length is < 1 or > 160) return BadRequest("UID or exact account/name is required (up to 160 characters).");
        return Results.Ok(await repository.FindPlayersAsync(q, cancellationToken));
    }

    private static async Task<IResult> GetEquipmentAsync(Guid playerId, AdminRepository repository, CancellationToken cancellationToken) =>
        Results.Ok(await repository.GetInventoryEquipmentAsync(playerId, cancellationToken));

    private static async Task<IResult> SendMailAsync(AdminMailRequest request, HttpContext context,
        AdminRepository repository, CancellationToken cancellationToken)
    {
        if (!ValidText(request.Title, 160) || !ValidText(request.Body, 4000) ||
            !ValidOptionalText(request.TitleEn, 160) || !ValidOptionalText(request.BodyEn, 4000) || request.Attachments is null ||
            request.Attachments.Count is < 1 or > 10 || request.Attachments.Any(item => !AdminRepository.ValidGrant(item)))
            return BadRequest("Invalid mail or attachment. Supported: balances, consumables and equipment.");
        return await WriteMailAsync(request, "grant", context, repository, cancellationToken);
    }

    private static async Task<IResult> SendMessageAsync(AdminMessageRequest request, HttpContext context,
        AdminRepository repository, CancellationToken cancellationToken)
    {
        if (!ValidText(request.Title, 160) || !ValidText(request.Body, 4000) ||
            !ValidOptionalText(request.TitleEn, 160) || !ValidOptionalText(request.BodyEn, 4000))
            return BadRequest("Invalid message.");
        return await WriteMailAsync(new AdminMailRequest(request.PlayerId, request.Title, request.Body, [], request.TitleEn, request.BodyEn),
            "message", context, repository, cancellationToken);
    }

    private static async Task<IResult> WriteMailAsync(AdminMailRequest request, string operation, HttpContext context,
        AdminRepository repository, CancellationToken cancellationToken)
    {
        var id = IdempotencyKeys.Read(context);
        if (id is null) return IdempotencyKeys.InvalidProblem(context);
        try
        {
            var mailId = await repository.SendMailAsync(request, operation, id, cancellationToken);
            return mailId is null ? Results.NotFound() : Results.Ok(new { mailId });
        }
        catch (AdminConflictException exception) { return Conflict(exception); }
    }

    private static async Task<IResult> RevokeAsync(AdminRevokeRequest request, HttpContext context,
        AdminRepository repository, CancellationToken cancellationToken)
    {
        if (!ValidText(request.Reason, 500) || string.IsNullOrWhiteSpace(request.Kind) || request.Amount is < 1 or > 1_000_000 ||
            (request.Kind == "Equipment" ? request.Amount != 1 || !Guid.TryParse(request.ItemId, out _)
                : !AdminRepository.ValidGrant(new AdminAttachment(request.Kind, request.Amount, null))))
            return BadRequest("Invalid item, amount or reason.");
        var id = IdempotencyKeys.Read(context);
        if (id is null) return IdempotencyKeys.InvalidProblem(context);
        try
        {
            var applied = await repository.RevokeAsync(request, id, cancellationToken);
            return applied is null ? Results.NotFound() : Results.Ok(new { applied });
        }
        catch (AdminConflictException exception) { return Conflict(exception); }
    }

    private static async Task<IResult> BanAsync(AdminBanRequest request, HttpContext context,
        AdminRepository repository, CancellationToken cancellationToken)
    {
        if (!ValidText(request.Reason, 500)) return BadRequest("Ban reason is required.");
        return await SetBanAsync(request.PlayerId, request.Reason, context, repository, cancellationToken);
    }

    private static Task<IResult> UnbanAsync(AdminBanRequest request, HttpContext context,
        AdminRepository repository, CancellationToken cancellationToken) =>
        SetBanAsync(request.PlayerId, null, context, repository, cancellationToken);

    private static Task<IResult> UnlockAllCardsAsync(AdminBulkOperationRequest request, HttpContext context,
        AdminRepository repository, CancellationToken cancellationToken) =>
        RunBulkOperationAsync(request, context, repository.UnlockAllCardsAsync, cancellationToken);

    private static Task<IResult> MaxAllCardsAsync(AdminBulkOperationRequest request, HttpContext context,
        AdminRepository repository, CancellationToken cancellationToken) =>
        RunBulkOperationAsync(request, context, repository.MaxAllCardsAsync, cancellationToken);

    private static Task<IResult> GrantAllEquipmentAsync(AdminBulkOperationRequest request, HttpContext context,
        AdminRepository repository, CancellationToken cancellationToken) =>
        RunBulkOperationAsync(request, context, repository.GrantAllEquipmentAsync, cancellationToken);

    private static Task<IResult> MaxExistingEquipmentAsync(AdminBulkOperationRequest request, HttpContext context,
        AdminRepository repository, CancellationToken cancellationToken) =>
        RunBulkOperationAsync(request, context, repository.MaxExistingEquipmentAsync, cancellationToken);

    private static async Task<IResult> RunBulkOperationAsync(AdminBulkOperationRequest request, HttpContext context,
        Func<Guid, string, CancellationToken, Task<AdminBulkOperationResult?>> operation, CancellationToken cancellationToken)
    {
        if (request.PlayerId == Guid.Empty) return BadRequest("A player must be selected.");
        var id = IdempotencyKeys.Read(context);
        if (id is null) return IdempotencyKeys.InvalidProblem(context);
        try
        {
            var result = await operation(request.PlayerId, id, cancellationToken);
            return result is null ? Results.NotFound() : Results.Ok(result);
        }
        catch (AdminConflictException exception) { return Conflict(exception); }
    }

    private static async Task<IResult> SetBanAsync(Guid playerId, string? reason, HttpContext context,
        AdminRepository repository, CancellationToken cancellationToken)
    {
        var id = IdempotencyKeys.Read(context);
        if (id is null) return IdempotencyKeys.InvalidProblem(context);
        try
        {
            var applied = await repository.SetBanAsync(playerId, reason, id, cancellationToken);
            return applied is null ? Results.NotFound() : Results.Ok(new { applied, banned = reason is not null });
        }
        catch (AdminConflictException exception) { return Conflict(exception); }
    }

    private static bool ValidText(string? value, int maxLength) =>
        !string.IsNullOrWhiteSpace(value) && value.Length <= maxLength &&
        !value.Any(character => char.IsControl(character) && character is not ('\r' or '\n' or '\t'));
    private static bool ValidOptionalText(string? value, int maxLength) =>
        value is null || (value.Length <= maxLength &&
        !value.Any(character => char.IsControl(character) && character is not ('\r' or '\n' or '\t')));
    private static IResult BadRequest(string detail) => Results.Problem(statusCode: 400, title: "Invalid admin request", detail: detail);
    private static IResult Conflict(AdminConflictException exception) => Results.Problem(statusCode: 409, title: "Operation conflict", detail: exception.Message);

    private static async Task<IResult> GetClientSettingsAsync(ClientSettingsRepository repository,
        CancellationToken cancellationToken) =>
        Results.Ok(await repository.GetAsync(cancellationToken));

    private static async Task<IResult> UpdateClientSettingsAsync(UpdateClientSettingsRequest request,
        ClientSettingsRepository repository, ClientSettingsHub hub, IHostEnvironment environment,
        IConfiguration configuration, CancellationToken cancellationToken)
    {
        if (request.AnnouncementTitle is null || request.AnnouncementBody is null ||
            request.AnnouncementTitle.Length > 120 || request.AnnouncementBody.Length > 6000 ||
            request.AnnouncementTitle.Any(char.IsControl) ||
            request.AnnouncementBody.Any(character => char.IsControl(character) && character is not ('\r' or '\n' or '\t')) ||
            !ValidOptionalText(request.AnnouncementTitleEn, 120) ||
            !ValidOptionalText(request.AnnouncementBodyEn, 6000))
            return BadRequest("Announcement title or body is invalid.");
        if (request.LocalLoginEnabled && !configuration.GetValue<bool>("Identity:AllowManagedLocalAuth"))
            return BadRequest("Managed local login is not permitted on this server.");
        var updated = await repository.UpdateAsync(request, cancellationToken);
        if (updated is null) return Results.Problem(statusCode: 409, title: "Settings changed; reload before publishing");
        await hub.PublishAsync(ClientSettingsEndpoints.PublicInfo(updated, environment, configuration));
        return Results.Ok(updated);
    }
}
