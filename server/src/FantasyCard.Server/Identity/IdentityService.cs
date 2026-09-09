using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using Microsoft.Extensions.Options;

namespace FantasyCard.Server.Identity;

public sealed record SignInResult(string AccessToken, DateTimeOffset ExpiresAt, PlayerProfile Player);

public sealed class IdentityService(
    IdentityRepository repository,
    IOptions<IdentityOptions> options,
    TimeProvider timeProvider,
    ServerMetrics metrics)
{
    public async Task<SignInResult> SignInLocalAsync(
        string? deviceId,
        string? displayName,
        CancellationToken cancellationToken)
    {
        try
        {
            var normalizedDeviceId = NormalizeDeviceId(deviceId);
            var normalizedDisplayName = PlayerProfile.NormalizeDisplayName(displayName);
            var token = SessionToken.Create();
            var now = timeProvider.GetUtcNow();
            var expiresAt = now.AddDays(options.Value.SessionLifetimeDays);
            var player = await repository.SignInLocalAsync(
                normalizedDeviceId,
                normalizedDisplayName,
                SessionToken.Hash(token),
                now,
                expiresAt,
                cancellationToken);
            metrics.IdentitySignInSucceeded("local");
            return new SignInResult(token, expiresAt, player);
        }
        catch (Exception) when (!cancellationToken.IsCancellationRequested)
        {
            metrics.IdentitySignInFailed("local", "rejected");
            throw;
        }
    }

    public async Task<SignInResult> SignInExternalAsync(
        string provider,
        string externalSubject,
        string? displayName,
        CancellationToken cancellationToken)
    {
        try
        {
            ArgumentException.ThrowIfNullOrWhiteSpace(provider);
            ArgumentException.ThrowIfNullOrWhiteSpace(externalSubject);
            var normalizedDisplayName = PlayerProfile.NormalizeDisplayName(displayName);
            var token = SessionToken.Create();
            var now = timeProvider.GetUtcNow();
            var expiresAt = now.AddDays(options.Value.SessionLifetimeDays);
            var player = await repository.SignInExternalAsync(
                provider, externalSubject, normalizedDisplayName, SessionToken.Hash(token),
                now, expiresAt, cancellationToken);
            metrics.IdentitySignInSucceeded(provider);
            return new SignInResult(token, expiresAt, player);
        }
        catch (Exception) when (!cancellationToken.IsCancellationRequested)
        {
            metrics.IdentitySignInFailed(provider, "rejected");
            throw;
        }
    }

    public async Task<PlayerProfile?> AuthenticateAsync(string token, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(token) || token.Length > 256)
        {
            metrics.IdentityTokenRejected();
            return null;
        }

        var result = await repository.FindByTokenHashAsync(
            SessionToken.Hash(token),
            timeProvider.GetUtcNow(),
            cancellationToken);
        if (result.IsExpired)
            metrics.IdentityTokenExpired();
        else if (result.Player is null)
            metrics.IdentityTokenRejected();
        return result.Player;
    }

    public static string NormalizeDeviceId(string? deviceId)
    {
        if (string.IsNullOrWhiteSpace(deviceId))
        {
            throw new DomainValidationException("Device id must contain 8-128 printable characters.");
        }

        var normalized = deviceId.Trim();
        if (normalized.Length is < 8 or > 128 || normalized.Any(char.IsControl))
        {
            throw new DomainValidationException("Device id must contain 8-128 printable characters.");
        }

        return normalized;
    }
}
