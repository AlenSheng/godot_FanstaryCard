using FantasyCard.Server.Common;
using Microsoft.AspNetCore.Http;

namespace FantasyCard.Server.Tests.Common;

public sealed class IdempotencyKeysTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("short")]
    [InlineData("contains\ncontrol")]
    public void Read_rejects_missing_or_invalid_values(string? value)
    {
        var context = new DefaultHttpContext();
        if (value is not null) context.Request.Headers[IdempotencyKeys.HeaderName] = value;

        Assert.Null(IdempotencyKeys.Read(context));
    }

    [Fact]
    public void Read_trims_valid_value()
    {
        var context = new DefaultHttpContext();
        context.Request.Headers[IdempotencyKeys.HeaderName] = "  request-123  ";

        Assert.Equal("request-123", IdempotencyKeys.Read(context));
    }

    [Fact]
    public void Read_rejects_value_over_maximum_length()
    {
        var context = new DefaultHttpContext();
        context.Request.Headers[IdempotencyKeys.HeaderName] = new string('a', IdempotencyKeys.MaximumLength + 1);

        Assert.Null(IdempotencyKeys.Read(context));
    }
}
