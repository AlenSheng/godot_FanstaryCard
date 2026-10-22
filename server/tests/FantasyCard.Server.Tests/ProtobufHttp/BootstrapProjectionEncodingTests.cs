using System.Collections;
using System.Text.Json;
using FantasyCard.Contracts.Bootstrap;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Matchmaking;
using Google.Protobuf.Reflection;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class BootstrapProjectionEncodingTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Projection_uses_existing_bootstrap_wire_fields_without_catalogs(bool ready)
    {
        var time = new DateTimeOffset(2026, 10, 19, 12, 0, 0, TimeSpan.Zero);
        var receipt = new SettlementResponse(Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid(), "Dead",
            JsonSerializer.SerializeToElement(new { revision = 789L }), time);
        var dto = new BootstrapSettlementProjection(time, "projection-config", ready ? receipt : null);
        var raw = HttpDtoMapper.EncodeResponse(HttpProtocolRegistry.Find("GET", "/api/v1/bootstrap")!, dto);
        var wire = Wire.BootstrapResponse.Parser.ParseFrom(raw);
        Assert.NotEmpty(wire.ServerTime);
        Assert.Equal(dto.ConfigVersion, wire.ConfigVersion);
        Assert.True(raw.Length < 512);
        if (ready)
        {
            Assert.Equal(receipt.SettlementId.ToString(), wire.UnfinishedSettlement.SettlementId);
            Assert.Equal(receipt.MatchId.ToString(), wire.UnfinishedSettlement.MatchId);
            Assert.Equal(receipt.PlayerId.ToString(), wire.UnfinishedSettlement.PlayerId);
            Assert.Equal(789, wire.UnfinishedSettlement.Details.Revision);
        }
        else Assert.Null(wire.UnfinishedSettlement);
        foreach (var field in Wire.BootstrapResponse.Descriptor.Fields.InFieldNumberOrder())
        {
            if (field.Name is "server_time" or "config_version" or "unfinished_settlement") continue;
            if (field.IsRepeated) Assert.Empty((IEnumerable)field.Accessor.GetValue(wire));
            else
            {
                Assert.Equal(FieldType.Message, field.FieldType);
                Assert.Null(field.Accessor.GetValue(wire));
            }
        }
    }
}
