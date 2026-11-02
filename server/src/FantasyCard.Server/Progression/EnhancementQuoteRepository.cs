using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Seasons;
using Npgsql;

namespace FantasyCard.Server.Progression;

public sealed partial class ProgressionRepository
{
    public async Task<EnhancementQuoteResponse?> GetEquipmentEnhancementQuoteAsync(
        Guid playerId, Guid equipmentId, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        var equipment = await ReadEnhancementEquipmentAsync(connection, null, playerId, equipmentId, false, cancellationToken);
        if (equipment is null) return null;
        var policy = await ResolveArmorEnhancementPolicyAsync(connection, null, equipment, cancellationToken);
        SeasonWalletSnapshot? wallet = null;
        long fragments;
        if (policy.Context is { } context)
        {
            wallet = await new SeasonRepository(dataSource, timeProvider ?? TimeProvider.System).GetWalletAsync(playerId, context, cancellationToken)
                ?? throw new DomainValidationException("The player has not joined the selected season.");
            if (wallet.ArchivedAt is not null) throw new DomainValidationException("The selected season wallet is closed for new actions.");
            fragments = wallet.EquipmentFragments;
        }
        else
        {
            await using var command = new NpgsqlCommand("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", connection);
            command.Parameters.AddWithValue(playerId);
            fragments = (long)(await command.ExecuteScalarAsync(cancellationToken))!;
        }
        var materials = await CountEnhancementMaterialsAsync(connection, playerId, equipment, cancellationToken);
        RequireArmorEnhancementTime(policy);
        return EnhancementQuote("Equipment", equipment.Quality, equipment.Level, equipment.Version, fragments, materials,
            equipment.Location is "Inventory" or "Equipped", equipment.Level >= 5 ? 0 : policy.Cost(equipment.Quality, equipment.Level + 1))
            with { FragmentSourceSeasonId = wallet?.SeasonId, FragmentWalletVersion = wallet?.Version };
    }

    public Task<EnhancementQuoteResponse?> GetWeaponEnhancementQuoteAsync(
        Guid playerId, HeroClass heroClass, CancellationToken cancellationToken) =>
        GetWeaponEnhancementQuoteAsync(playerId, heroClass, null, cancellationToken);

    public async Task<EnhancementQuoteResponse?> GetWeaponEnhancementQuoteAsync(
        Guid playerId, HeroClass heroClass, SeasonContext? fragmentSource, CancellationToken cancellationToken)
    {
        SeasonWalletSnapshot? seasonalWallet = null;
        if (fragmentSource is not null)
            seasonalWallet = await new SeasonRepository(dataSource, TimeProvider.System).GetWalletAsync(playerId, fragmentSource, cancellationToken)
                ?? throw new DomainValidationException("The player has not joined the selected season.");
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
        var quote = EnhancementQuote("ClassWeapon", "White", reader.GetInt32(0), reader.GetInt64(1),
            seasonalWallet?.EquipmentFragments ?? reader.GetInt64(2), 0, true);
        return quote with { FragmentSourceSeasonId = fragmentSource?.SeasonId, FragmentWalletVersion = seasonalWallet?.Version };
    }

    private static EnhancementQuoteResponse EnhancementQuote(
        string targetKind, string quality, int level, long version, long fragments, int materials, bool available, long? quotedCost = null)
    {
        var atMaximum = level >= 5;
        var cost = atMaximum ? 0 : quotedCost ?? FragmentCost(quality, level + 1);
        var materialCount = !atMaximum && targetKind == "Equipment" && level >= 3 ? 1 : 0;
        var blocked = !available ? "Equipment cannot be enhanced in its current state."
            : atMaximum ? "Already at maximum level."
            : fragments < cost ? "Not enough equipment fragments."
            : materials < materialCount ? "A same-quality inventory material is required." : null;
        return new(targetKind, level, atMaximum ? null : level + 1, version, cost, materialCount,
            materialCount > 0 ? quality : null, fragments, materials, blocked is null, blocked);
    }
}
