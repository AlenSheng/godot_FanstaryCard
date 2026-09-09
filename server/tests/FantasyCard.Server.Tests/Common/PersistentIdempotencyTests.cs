using FantasyCard.Server.Common;

namespace FantasyCard.Server.Tests.Common;

public sealed class PersistentIdempotencyTests
{
    [Fact]
    public void Hash_IsStableForSameRequest()
    {
        var request = new { TargetId = Guid.Parse("018f90dc-19a3-7a3d-8c33-1234567890ab"), Version = 7L };

        Assert.Equal(PersistentIdempotency.Hash(request), PersistentIdempotency.Hash(request));
    }

    [Fact]
    public void Hash_ChangesWhenTargetChanges()
    {
        var first = PersistentIdempotency.Hash(new { TargetId = "first" });
        var second = PersistentIdempotency.Hash(new { TargetId = "second" });

        Assert.NotEqual(first, second);
    }
}
