using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class ProgressionRepository
{
    private sealed record ArmorEnhancementPolicy(SeasonScheduleSnapshot Schedule, GameConfigCatalog Configuration)
    {
        public SeasonContext? Context => Schedule.Current?.ContextFor(0);
        public long Cost(string quality, int targetLevel) => Schedule.Current is { } season
            ? SeasonEnhancementRules.ArmorCost(Configuration, season, quality, targetLevel)
            : Configuration.EquipmentQuality(quality).EnhancementCost(targetLevel);
    }

    private static async Task<EquipmentResponse?> ReadEnhancementEquipmentAsync(NpgsqlConnection connection,
        NpgsqlTransaction? transaction, Guid playerId, Guid itemId, bool lockRow, CancellationToken ct)
    {
        var sql = """
            SELECT instance_id,slot,quality,level,is_bound,location,version,element,effect_affix,secondary_trait,
                origin_season_id,season_id,asset_scope,stats_version,source_kind,recipe_extracted,unique_affix,unique_element
            FROM equipments WHERE instance_id=$1 AND owner_id=$2
            """ + (lockRow ? " FOR UPDATE" : "");
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        command.Parameters.AddWithValue(itemId); command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(ct);
        if (!await reader.ReadAsync(ct)) return null;
        return ReadEquipment(reader) with
        {
            OriginSeasonId = reader.IsDBNull(10) ? null : reader.GetString(10),
            SeasonId = reader.IsDBNull(11) ? null : reader.GetString(11),
            AssetScope = reader.IsDBNull(12) ? null : reader.GetString(12),
            StatsVersion = reader.IsDBNull(13) ? null : reader.GetString(13),
            SourceKind = reader.IsDBNull(14) ? null : reader.GetString(14),
            RecipeExtracted = reader.IsDBNull(12) ? null : reader.GetBoolean(15),
            UniqueAffix = reader.IsDBNull(16) ? null : reader.GetString(16),
            UniqueElement = reader.IsDBNull(17) ? null : reader.GetString(17)
        };
    }

    private async Task<ArmorEnhancementPolicy> ResolveArmorEnhancementPolicyAsync(NpgsqlConnection connection,
        NpgsqlTransaction? transaction, EquipmentResponse equipment, CancellationToken ct)
    {
        var clock = timeProvider ?? TimeProvider.System;
        var schedule = await new SeasonRepository(dataSource, clock).GetScheduleAsync(ct);
        if (equipment.SourceKind is "BotReward" or "Borrowed")
            throw new DomainValidationException("Generated or borrowed equipment cannot fund armor enhancement.");
        if (schedule.Current is not { } season)
        {
            if (!schedule.LegacyAllowed || equipment.SeasonId is not null || equipment.AssetScope is not null)
                throw new DomainValidationException("Equipment belongs to another season or archive.");
            return new(schedule, GameConfigCatalog.Current);
        }
        if (equipment.SeasonId != season.SeasonId || equipment.AssetScope != "ActiveSeason" ||
            equipment.StatsVersion != season.StatsVersion)
            throw new DomainValidationException("Equipment belongs to another season or archive.");
        GameConfigCatalog configuration;
        try { configuration = _enhancementConfigurations.Resolve(season.ConfigVersion); }
        catch (IOException) { throw new DomainValidationException("The original equipment configuration is unavailable."); }
        await using var hash = new NpgsqlCommand("SELECT config_sha256 FROM season_definitions WHERE season_id=$1", connection, transaction);
        hash.Parameters.AddWithValue(season.SeasonId);
        if (await hash.ExecuteScalarAsync(ct) is not string expected || expected != configuration.ContentHash)
            throw new DomainValidationException("The original equipment configuration hash differs from its published season.");
        _ = configuration.ResolveSeasonEquipment(season.StatsVersion);
        return new(schedule, configuration);
    }

    private static bool SameEnhancementDomain(EquipmentResponse target, EquipmentResponse material) =>
        target.SeasonId == material.SeasonId && target.AssetScope == material.AssetScope &&
        (target.SeasonId is null || target.StatsVersion == material.StatsVersion) &&
        material.SourceKind is not ("BotReward" or "Borrowed");

    private static async Task<int> CountEnhancementMaterialsAsync(NpgsqlConnection connection,
        Guid playerId, EquipmentResponse target, CancellationToken ct)
    {
        await using var command = new NpgsqlCommand("""
            SELECT count(*)::integer FROM equipments
            WHERE owner_id=$1 AND quality=$2 AND instance_id<>$3 AND location='Inventory'
                AND (($4::varchar IS NULL AND season_id IS NULL AND asset_scope IS NULL)
                    OR (season_id=$4 AND asset_scope='ActiveSeason' AND stats_version=$5))
                AND COALESCE(source_kind,'') NOT IN ('BotReward','Borrowed')
            """, connection);
        command.Parameters.AddWithValue(playerId); command.Parameters.AddWithValue(target.Quality);
        command.Parameters.AddWithValue(target.InstanceId);
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, (object?)target.SeasonId ?? DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, (object?)target.StatsVersion ?? DBNull.Value);
        return (int)(await command.ExecuteScalarAsync(ct))!;
    }

    private void RequireArmorEnhancementTime(ArmorEnhancementPolicy policy)
    {
        var now = (timeProvider ?? TimeProvider.System).GetUtcNow();
        if (policy.Schedule.Current is { } season && !season.Contains(now) ||
            policy.Schedule.Current is null && policy.Schedule.Next is { } next && now >= next.StartsAtUtc)
            throw new DomainValidationException("The season changed during enhancement. Reload and retry.");
    }
}
