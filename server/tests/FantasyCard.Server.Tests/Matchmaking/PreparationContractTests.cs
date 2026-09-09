using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;

namespace FantasyCard.Server.Tests.Matchmaking;

public sealed class PreparationContractTests
{
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        Converters = { new JsonStringEnumConverter() }
    };

    [Fact]
    public void Equipment_snapshot_round_trips_as_an_additive_optional_field()
    {
        var itemId = Guid.NewGuid();
        var snapshot = CreateSnapshot([
            new(itemId, "Feet", "White", 0, "Fire", null, "DrawInterval")
        ]);

        var json = JsonSerializer.Serialize(snapshot, Options);
        var restored = JsonSerializer.Deserialize<PreparationSnapshotResponse>(json, Options)!;

        var equipment = Assert.Single(restored.EquipmentSnapshots!);
        Assert.Equal(itemId, equipment.InstanceId);
        Assert.Equal("Fire", equipment.Element);
    }

    [Fact]
    public void Legacy_snapshot_without_equipment_details_remains_readable()
    {
        var json = JsonSerializer.Serialize(CreateSnapshot(null), Options);
        using var document = JsonDocument.Parse(json);
        var legacy = document.RootElement.EnumerateObject()
            .Where(property => property.Name != "equipmentSnapshots")
            .ToDictionary(property => property.Name, property => property.Value.Clone());
        var legacyJson = JsonSerializer.Serialize(legacy, Options);

        var restored = JsonSerializer.Deserialize<PreparationSnapshotResponse>(legacyJson, Options)!;

        Assert.Null(restored.EquipmentSnapshots);
    }

    private static PreparationSnapshotResponse CreateSnapshot(
        IReadOnlyList<PreparationEquipmentSnapshotResponse>? equipment) =>
        new(
            HeroClassDto.Mage,
            70,
            Enumerable.Range(1, 20).Select(index => $"card-{index}").ToArray(),
            [null, null, null, null, Guid.NewGuid()],
            0,
            BackpackTierDto.Free,
            20,
            [],
            0,
            "Standard",
            "test",
            equipment);
}
