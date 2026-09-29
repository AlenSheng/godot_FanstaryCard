using System.Text.Json;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Matchmaking;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class SettlementEncodingTests
{
    [Theory]
    [InlineData("Extracted")]
    [InlineData("Dead")]
    public void Persisted_items_encode_in_receipt_and_bootstrap(string result)
    {
        using var details = JsonDocument.Parse("""
            {"roomId":"room","revision":42,"phase":6,"position":{"row":2,"column":3},
             "heroClass":"Mage","assetCount":2,"items":[
              {"item":{"itemId":"gold","kind":"Gold","quantity":120,"isSafe":true,"equipment":null},"equipped":false},
              {"item":{"itemId":"armor","kind":"Equipment","quantity":1,"isSafe":false,
               "equipment":{"slot":2,"quality":3,"element":4,"effectAffix":"Bulwark","secondaryTrait":null,"level":1,"isBound":false}},"equipped":true}]}
            """);
        var receipt = new SettlementResponse(Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid(), result,
            details.RootElement.Clone(), DateTimeOffset.UtcNow);
        foreach (var path in new[] { $"/api/v1/settlements/{receipt.SettlementId}", $"/api/v1/matches/{receipt.MatchId}/settlement" })
        {
            var bytes = HttpDtoMapper.EncodeResponse(HttpProtocolRegistry.Find("GET", path)!, receipt);
            Verify(Wire.SettlementResponse.Parser.ParseFrom(bytes), receipt);
        }
        var bootstrap = HttpDtoMapper.EncodeResponse(HttpProtocolRegistry.Find("GET", "/api/v1/bootstrap")!,
            new { UnfinishedSettlement = receipt });
        Verify(Wire.BootstrapResponse.Parser.ParseFrom(bootstrap).UnfinishedSettlement, receipt);
    }

    private static void Verify(Wire.SettlementResponse wire, SettlementResponse receipt)
    {
        Assert.Equal(receipt.SettlementId.ToString(), wire.SettlementId);
        Assert.Equal(receipt.Result, wire.Result);
        Assert.Equal(2, wire.Details.Items.Count);
        Assert.Equal(120, wire.Details.Items[0].Item.Quantity);
        Assert.True(wire.Details.Items[0].Item.IsSafe);
        Assert.Null(wire.Details.Items[0].Item.Equipment);
        Assert.True(wire.Details.Items[1].Equipped);
        Assert.Equal("Bulwark", wire.Details.Items[1].Item.Equipment.EffectAffix);
        Assert.Equal(3, wire.Details.Items[1].Item.Equipment.Quality);
    }
}
