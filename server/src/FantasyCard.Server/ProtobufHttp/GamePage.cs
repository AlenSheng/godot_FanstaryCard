using System.Globalization;
using FantasyCard.Contracts.Bootstrap;
using FantasyCard.Contracts.Mail;
using FantasyCard.Contracts.Progression;

namespace FantasyCard.Server.ProtobufHttp;

public readonly record struct GamePage(int Limit, int Offset)
{
    public static GamePage Read(HttpContext context)
    {
        var query = context.Request.Query;
        var limit = Parse(query["limit"].ToString(), 200);
        var offset = Parse(query["offset"].ToString(), 0);
        if (limit is < 1 or > 200 || offset is < 0 or > 1_000_000)
            throw new BadHttpRequestException("limit must be 1-200 and offset 0-1000000.", 400);
        return new(limit, offset);
    }
    private static int Parse(string value, int fallback) => value.Length == 0 ? fallback :
        int.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out var number) ? number :
        throw new BadHttpRequestException("Invalid pagination parameter.", 400);

    public static void SetHeaders(HttpContext context, object? value)
    {
        if (value is not (IReadOnlyList<MarketListingResponse> or MailListResponse or MarketInventoryContextResponse or EconomyContextResponse or BootstrapResponse)) return;
        var page = Read(context);
        switch (value)
        {
            case IReadOnlyList<MarketListingResponse> market: Next(context, "Market", market.Count, page); break;
            case MailListResponse mail: Next(context, "Mail", mail.Items.Count, page); break;
            case MarketInventoryContextResponse marketContext: Next(context, "Market", marketContext.Listings.Count, page); break;
            case EconomyContextResponse economy: Next(context, "Market", economy.Market.Count, page); break;
            case BootstrapResponse bootstrap:
                Next(context, "Market", bootstrap.Market?.Count ?? 0, new(200, 0));
                Next(context, "Mail", bootstrap.Mail?.Items.Count ?? 0, new(200, 0)); break;
        }
    }
    private static void Next(HttpContext context, string kind, int count, GamePage page)
    {
        if (count == page.Limit) context.Response.Headers["X-" + kind + "-Next-Offset"] = (page.Offset + count).ToString(CultureInfo.InvariantCulture);
    }
}
