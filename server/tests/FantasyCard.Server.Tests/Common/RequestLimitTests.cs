using FantasyCard.Server.Common;

namespace FantasyCard.Server.Tests.Common;

public sealed class RequestLimitTests
{
    [Fact]
    public void Realtime_limiter_rejects_overflow_within_one_second()
    {
        var limiter = new RealtimeCommandRateLimiter(3);
        var now = DateTimeOffset.UnixEpoch;

        Assert.True(limiter.TryAcquire(now));
        Assert.True(limiter.TryAcquire(now.AddMilliseconds(100)));
        Assert.True(limiter.TryAcquire(now.AddMilliseconds(200)));
        Assert.False(limiter.TryAcquire(now.AddMilliseconds(999)));
    }

    [Fact]
    public void Realtime_limiter_releases_only_expired_entries()
    {
        var limiter = new RealtimeCommandRateLimiter(2);
        var now = DateTimeOffset.UnixEpoch;
        Assert.True(limiter.TryAcquire(now));
        Assert.True(limiter.TryAcquire(now.AddMilliseconds(500)));

        Assert.True(limiter.TryAcquire(now.AddSeconds(1)));
        Assert.False(limiter.TryAcquire(now.AddMilliseconds(1499)));
        Assert.True(limiter.TryAcquire(now.AddMilliseconds(1500)));
    }

    [Fact]
    public void Realtime_limiter_requires_a_positive_limit()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => new RealtimeCommandRateLimiter(0));
    }
}
