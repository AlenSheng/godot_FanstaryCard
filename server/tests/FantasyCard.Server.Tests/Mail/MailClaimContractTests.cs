using System.Text.Json;
using FantasyCard.Contracts.Mail;

namespace FantasyCard.Server.Tests.Mail;

public sealed class MailClaimContractTests
{
    [Fact]
    public void Claim_all_reports_exact_grants_and_accepts_legacy_replays()
    {
        var mailId = Guid.NewGuid();
        var response = new MailClaimAllResponse(1, 1,
            [new MailClaimResponse(mailId, false, [new MailAttachmentResponse("Gold", 25)])]);
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);

        var json = JsonSerializer.Serialize(response, options);
        using var document = JsonDocument.Parse(json);
        Assert.Equal(mailId.ToString(), document.RootElement.GetProperty("claims")[0].GetProperty("mailId").GetString());
        Assert.Equal(25, document.RootElement.GetProperty("claims")[0].GetProperty("granted")[0].GetProperty("amount").GetInt64());
        Assert.Single(JsonSerializer.Deserialize<MailClaimAllResponse>(json, options)!.Claims!);

        var legacy = JsonSerializer.Deserialize<MailClaimAllResponse>("{\"mailCount\":1,\"attachmentCount\":1}", options);
        Assert.Null(legacy!.Claims);
    }
}
