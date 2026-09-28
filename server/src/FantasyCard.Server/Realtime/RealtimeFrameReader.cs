using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Common;

namespace FantasyCard.Server.Realtime;

// The budget applies to every complete binary frame, including malformed protobuf.
internal sealed class RealtimeFrameReader(int permitLimit)
{
    private readonly RealtimeCommandRateLimiter _limiter = new(permitLimit);
    private DateTimeOffset? _lastRateLimitNotice;

    public FrameResult Read(byte[] payload, DateTimeOffset now)
    {
        if (!_limiter.TryAcquire(now))
        {
            var notify = _lastRateLimitNotice is null || now - _lastRateLimitNotice >= TimeSpan.FromSeconds(1);
            if (notify) _lastRateLimitNotice = now;
            return new(null, notify ? "error.rate_limited" : null, true);
        }
        try
        {
            var command = RealtimeProtobufCodec.DecodeClient(payload);
            return new(command, command is null ? "error.invalid_message" : null, false);
        }
        catch (Exception exception) when (exception is InvalidDataException or OverflowException)
        {
            return new(null, "error.invalid_message", false);
        }
    }

    internal sealed record FrameResult(ClientCommand? Command, string? ErrorType, bool RateLimited);
}
