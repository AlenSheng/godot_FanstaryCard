using System.Text.Json;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Domain.Rooms;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class SettlementEncodingTests
{
    [Theory]
    [InlineData("Head", "White", "Fire")]
    [InlineData("Chest", "Green", "Wood")]
    [InlineData("Hands", "Blue", "Earth")]
    [InlineData("Legs", "Purple", "Metal")]
    [InlineData("Feet", "Orange", "Water")]
    [InlineData("Feet", "Red", "Fire")]
    public void Real_persisted_equipment_names_encode_in_receipt_and_bootstrap(string slot, string quality, string element)
    {
        var attributes = new EquipmentRewardData(slot, quality, element, null, "DrawInterval", 3, true);
        var details = JsonSerializer.SerializeToElement(new
        {
            Items = new[] { new { Item = new { ItemId = "owned-armor", Kind = "Equipment", Quantity = 1,
                IsSafe = false, Equipment = attributes }, Equipped = true } }
        });
        var receipt = new SettlementResponse(Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid(), "Extracted",
            details, DateTimeOffset.UtcNow);
        foreach (var path in new[] { $"/api/v1/settlements/{receipt.SettlementId}", $"/api/v1/matches/{receipt.MatchId}/settlement" })
        {
            var wire = Wire.SettlementResponse.Parser.ParseFrom(
                HttpDtoMapper.EncodeResponse(HttpProtocolRegistry.Find("GET", path)!, receipt));
            VerifyEquipmentNames(wire.Details.Items.Single().Item.Equipment, attributes);
        }
        var bootstrap = Wire.BootstrapResponse.Parser.ParseFrom(HttpDtoMapper.EncodeResponse(
            HttpProtocolRegistry.Find("GET", "/api/v1/bootstrap")!, new { UnfinishedSettlement = receipt }));
        VerifyEquipmentNames(bootstrap.UnfinishedSettlement.Details.Items.Single().Item.Equipment, attributes);
    }

    [Fact]
    public void Typed_equipment_names_use_the_same_wire_adapter()
    {
        var attributes = new EquipmentRewardData("Feet", "Purple", "Wood", "Vitality", "DrawInterval", 5, true);
        VerifyEquipmentNames((Wire.SettlementEquipment)HttpDtoMapper.FromDto(Wire.SettlementEquipment.Descriptor, attributes), attributes);
    }

    [Fact]
    public void Historical_numeric_strings_keep_the_original_numeric_tags()
    {
        using var data = JsonDocument.Parse("""{"slot":"2","quality":"3","element":"4"}""");
        var wire = (Wire.SettlementEquipment)HttpDtoMapper.FromDto(Wire.SettlementEquipment.Descriptor, data.RootElement);
        Assert.Equal(2, wire.Slot);
        Assert.Equal(3, wire.Quality);
        Assert.Equal(4, wire.Element);
        Assert.False(wire.HasSlotName);
        Assert.False(wire.HasQualityName);
        Assert.False(wire.HasElementName);
    }

    [Theory]
    [InlineData("slot", "Weapon")]
    [InlineData("slot", "feet")]
    [InlineData("quality", "Black")]
    [InlineData("quality", "")]
    [InlineData("element", "None")]
    [InlineData("element", "Unknown")]
    public void Invalid_persisted_equipment_names_are_rejected_without_default_success(string field, string value)
    {
        var data = JsonSerializer.SerializeToElement(new Dictionary<string, string> { [field] = value });
        var exception = Assert.Throws<InvalidDataException>(() => HttpDtoMapper.FromDto(Wire.SettlementEquipment.Descriptor, data));
        Assert.Contains(field, exception.Message, StringComparison.Ordinal);
    }

    private static void VerifyEquipmentNames(Wire.SettlementEquipment wire, EquipmentRewardData expected)
    {
        Assert.Equal(expected.Slot, wire.SlotName);
        Assert.Equal(expected.Quality, wire.QualityName);
        Assert.Equal(expected.Element, wire.ElementName);
        Assert.Equal(expected.Level, wire.Level);
        Assert.Equal(expected.IsBound, wire.IsBound);
        Assert.Equal(expected.SecondaryTrait, wire.SecondaryTrait);
        Assert.Equal(expected.EffectAffix ?? "", wire.EffectAffix);
        Assert.Equal(0, wire.Slot); // A name does not fabricate a historical numeric code.
        Assert.Equal(0, wire.Quality);
        Assert.Equal(0, wire.Element);
    }

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
