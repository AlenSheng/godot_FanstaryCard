using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Progression;
using Google.Protobuf;
using Npgsql;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class InventoryDiscardEncodingTests
{
    [Fact]
    public void TypedBatchCarriesEveryExactVersionAndExplicitSeason()
    {
        var contract = HttpProtocolRegistry.Find("POST", "/api/v1/inventory/discard")!;
        Assert.Equal(Wire.DiscardEquipmentRequest.Descriptor, contract.RequestDescriptor);
        var id = Guid.NewGuid(); var version = 9_007_199_254_740_993L;
        var wire = new Wire.DiscardEquipmentRequest { SeasonId = "original-season" };
        wire.Items.Add(new Wire.DiscardEquipmentItemRequest { EquipmentId = id.ToString("D"), ExpectedVersion = version });
        var dto = Assert.IsType<DiscardEquipmentRequest>(HttpDtoMapper.DecodeRequest(contract, wire.ToByteArray(), typeof(DiscardEquipmentRequest)));
        Assert.Equal("original-season", dto.SeasonId);
        Assert.Equal(new DiscardEquipmentItemRequest(id, version), Assert.Single(dto.Items!));
        Assert.Null(Assert.IsType<DiscardEquipmentRequest>(HttpDtoMapper.ToDto(new Wire.DiscardEquipmentRequest(), typeof(DiscardEquipmentRequest))).SeasonId);
    }

    [Fact]
    public void TypedReceiptKeepsThePhysicalBodyAndOriginalProvenance()
    {
        var item = new EquipmentResponse(Guid.NewGuid(), "Head", "Orange", 3, true, "Recycled", 8,
            "Water", "Vitality", "DrawInterval", "origin", "original-season", "ActiveSeason", "season-equipment-v1", "NaturalDrop", true);
        var response = new DiscardEquipmentResponse([item], "original-season");
        var contract = HttpProtocolRegistry.Find("POST", "/api/v1/inventory/discard")!;
        var packet = Wire.DiscardEquipmentResponse.Parser.ParseFrom(HttpDtoMapper.EncodeResponse(contract, response));
        Assert.Equal("original-season", packet.SeasonId); Assert.Equal("Recycled", Assert.Single(packet.Items).Location);
        var decoded = Assert.IsType<DiscardEquipmentResponse>(HttpDtoMapper.ToDto(packet, typeof(DiscardEquipmentResponse)));
        Assert.Equal(item, Assert.Single(decoded.Items));
    }

    [Theory]
    [InlineData("empty")][InlineData("duplicate")][InlineData("negative-version")][InlineData("empty-guid")][InlineData("too-many")]
    public async Task InvalidBatchIsRejectedBeforeAnyDatabaseConnection(string shape)
    {
        await using var source = NpgsqlDataSource.Create("Host=invalid;Database=not-used;Username=not-used");
        var item = new DiscardEquipmentItemRequest(Guid.NewGuid(), 1);
        var items = shape switch
        {
            "empty" => Array.Empty<DiscardEquipmentItemRequest>(),
            "duplicate" => new[] { item, item },
            "negative-version" => [item with { ExpectedVersion = -1 }],
            "empty-guid" => [item with { EquipmentId = Guid.Empty }],
            _ => Enumerable.Range(0, 51).Select(_ => item with { EquipmentId = Guid.NewGuid() }).ToArray()
        };
        await Assert.ThrowsAsync<DomainValidationException>(() => new ProgressionRepository(source)
            .DiscardEquipmentAsync(Guid.NewGuid(), "invalid-batch", new(items), TestContext.Current.CancellationToken));
    }
}
