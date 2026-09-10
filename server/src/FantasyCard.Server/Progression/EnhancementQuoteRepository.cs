using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;

namespace FantasyCard.Server.Progression;

public sealed partial class ProgressionRepository
{
    public async Task<EnhancementQuoteResponse?> GetEquipmentEnhancementQuoteAsync(
        Guid playerId, Guid equipmentId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT e.quality,e.level,e.location,e.version,m.equipment_fragments,
                (SELECT count(*)::integer FROM equipments material
                 WHERE material.owner_id=e.owner_id AND material.quality=e.quality
                   AND material.location='Inventory' AND material.instance_id<>e.instance_id)
            FROM equipments e JOIN player_materials m ON m.player_id=e.owner_id
            WHERE e.instance_id=$1 AND e.owner_id=$2
            """);
        command.Parameters.AddWithValue(equipmentId);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        return EnhancementQuote("Equipment", reader.GetString(0), reader.GetInt32(1), reader.GetInt64(3),
            reader.GetInt64(4), reader.GetInt32(5), reader.GetString(2) is "Inventory" or "Equipped");
    }

    public async Task<EnhancementQuoteResponse?> GetWeaponEnhancementQuoteAsync(
        Guid playerId, HeroClass heroClass, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT w.level,w.version,m.equipment_fragments FROM class_weapons w
            JOIN player_materials m ON m.player_id=w.player_id
            WHERE w.player_id=$1 AND w.hero_class=$2
            """);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue((short)heroClass);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        return EnhancementQuote("ClassWeapon", "White", reader.GetInt32(0), reader.GetInt64(1), reader.GetInt64(2), 0, true);
    }

    private static EnhancementQuoteResponse EnhancementQuote(
        string targetKind, string quality, int level, long version, long fragments, int materials, bool available)
    {
        var atMaximum = level >= 5;
        var cost = atMaximum ? 0 : FragmentCost(quality, level + 1);
        var materialCount = !atMaximum && targetKind == "Equipment" && level >= 3 ? 1 : 0;
        var blocked = !available ? "Equipment cannot be enhanced in its current state."
            : atMaximum ? "Already at maximum level."
            : fragments < cost ? "Not enough equipment fragments."
            : materials < materialCount ? "A same-quality inventory material is required." : null;
        return new(targetKind, level, atMaximum ? null : level + 1, version, cost, materialCount,
            materialCount > 0 ? quality : null, fragments, materials, blocked is null, blocked);
    }
}
