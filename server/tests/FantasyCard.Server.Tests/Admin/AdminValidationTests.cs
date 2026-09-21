using FantasyCard.Server.Admin;

namespace FantasyCard.Server.Tests.Admin;

public sealed class AdminValidationTests
{
    [Fact]
    public void Admin_page_is_embedded_in_server_assembly() =>
        Assert.NotNull(typeof(AdminRepository).Assembly.GetManifestResourceStream("FantasyCard.Server.Admin.admin.html"));

    [Theory]
    [InlineData("Gold", 100, null)]
    [InlineData("HealthPotion", 3, null)]
    [InlineData("Equipment", 1, "Purple|Water|Feet")]
    public void Supported_mail_attachments_can_be_claimed(string kind, long amount, string? itemId) =>
        Assert.True(AdminRepository.ValidGrant(new AdminAttachment(kind, amount, itemId)));

    [Theory]
    [InlineData("Gold", 0, null)]
    [InlineData("Gold", 1, "ignored")]
    [InlineData("Equipment", 2, "White|Fire|Head")]
    [InlineData("Equipment", 1, "invalid|Fire|Head")]
    [InlineData("Unsupported", 1, null)]
    public void Invalid_or_unsupported_attachments_are_rejected(string kind, long amount, string? itemId) =>
        Assert.False(AdminRepository.ValidGrant(new AdminAttachment(kind, amount, itemId)));
}
