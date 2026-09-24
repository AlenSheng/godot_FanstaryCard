using FantasyCard.Contracts.Bootstrap;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Players;
using FantasyCard.Server.Progression;
using Npgsql;
using System.Text.Json;

namespace FantasyCard.Server.Bootstrap;

public sealed class BootstrapRepository(
    NpgsqlDataSource dataSource,
    ProgressionRepository progressionRepository,
    EconomyRepository economyRepository,
    MailRepository mailRepository,
    PreparationRepository preparationRepository,
    TimeProvider timeProvider)
{
    public static string CurrentConfigVersion => GameConfigCatalog.Current.Version;

    public async Task<BootstrapResponse> GetAsync(
        PlayerProfile player,
        CancellationToken cancellationToken)
    {
        var decksTask = progressionRepository.GetDecksAsync(player.UserId, cancellationToken);
        var cardsTask = progressionRepository.GetCardsAsync(player.UserId, cancellationToken);
        var walletTask = GetWalletAsync(player.UserId, cancellationToken);
        var materialsTask = GetMaterialsAsync(player.UserId, cancellationToken);
        var weaponsTask = GetWeaponsAsync(player.UserId, cancellationToken);
        var loadoutsTask = GetLoadoutsAsync(player.UserId, cancellationToken);
        var unfinishedMatchTask = GetUnfinishedMatchAsync(player.UserId, cancellationToken);
        var unfinishedSettlementTask = GetUnfinishedSettlementAsync(player.UserId, cancellationToken);
        var inventoryFullTask = progressionRepository.GetInventoryAsync(player.UserId, cancellationToken);
        var shopTask = economyRepository.GetShopAsync(player.UserId, cancellationToken);
        var marketTask = economyRepository.GetMarketAsync(cancellationToken);
        var mailTask = mailRepository.GetAsync(player.UserId, cancellationToken);
        var activePreparationTask = preparationRepository.GetActiveAsync(player.UserId, cancellationToken);

        await Task.WhenAll(decksTask, cardsTask, walletTask, materialsTask, weaponsTask, loadoutsTask,
            unfinishedMatchTask, unfinishedSettlementTask, inventoryFullTask, shopTask, marketTask, mailTask,
            activePreparationTask);
        return new BootstrapResponse(
            timeProvider.GetUtcNow(),
            CurrentConfigVersion,
            player.ToResponse(),
            await walletTask,
            await materialsTask,
            await weaponsTask,
            await loadoutsTask,
            await decksTask,
            await cardsTask,
            (await inventoryFullTask).Summary,
            await unfinishedMatchTask,
            await unfinishedSettlementTask)
        {
            Inventory = await inventoryFullTask,
            Shop = await shopTask,
            Market = await marketTask,
            Mail = await mailTask,
            ActivePreparation = await activePreparationTask
        };
    }

    private async Task<SettlementResponse?> GetUnfinishedSettlementAsync(
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT s.settlement_id,s.match_id,s.player_id,s.result,s.details_json::text,s.created_at
            FROM match_settlements s
            WHERE s.player_id=$1
              AND s.acknowledged_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM settlement_asset_holds h
                  WHERE h.settlement_id=s.settlement_id AND h.state='Pending')
            ORDER BY s.created_at DESC,s.settlement_id DESC
            LIMIT 1
            """);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        return new SettlementResponse(
            reader.GetGuid(0),
            reader.GetGuid(1),
            reader.GetGuid(2),
            reader.GetString(3),
            JsonDocument.Parse(reader.GetString(4)).RootElement.Clone(),
            reader.GetFieldValue<DateTimeOffset>(5));
    }

    private async Task<UnfinishedMatchResponse?> GetUnfinishedMatchAsync(
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT m.match_id,m.room_id,m.status,rs.revision,m.config_version
            FROM match_players mp
            JOIN matches m ON m.match_id=mp.match_id
            LEFT JOIN room_snapshots rs ON rs.room_id=m.room_id
            WHERE mp.player_id=$1 AND mp.is_bot=false AND mp.state <> 'Settled'
              AND m.status IN ('Starting','Running')
            ORDER BY m.created_at DESC
            LIMIT 1
            """);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        return new UnfinishedMatchResponse(
            reader.GetGuid(0),
            reader.GetGuid(1),
            reader.GetString(2),
            reader.IsDBNull(3) ? null : reader.GetInt64(3),
            reader.GetString(4));
    }

    private async Task<WalletResponse> GetWalletAsync(Guid playerId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT gold, diamond FROM player_wallets WHERE player_id = $1");
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidOperationException("Player wallet was not provisioned.");
        }

        return new WalletResponse(reader.GetInt64(0), reader.GetInt64(1));
    }

    private async Task<MaterialsResponse> GetMaterialsAsync(Guid playerId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT warrior_soul, priest_soul, mage_soul, guardian_soul, equipment_fragments
            FROM player_materials WHERE player_id = $1
            """);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidOperationException("Player materials were not provisioned.");
        }

        return new MaterialsResponse(
            reader.GetInt64(0),
            reader.GetInt64(1),
            reader.GetInt64(2),
            reader.GetInt64(3),
            reader.GetInt64(4));
    }

    private async Task<IReadOnlyList<ClassWeaponResponse>> GetWeaponsAsync(
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT hero_class, level, version FROM class_weapons WHERE player_id = $1 ORDER BY hero_class");
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<ClassWeaponResponse>();
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new ClassWeaponResponse(
                (HeroClassDto)reader.GetInt16(0),
                reader.GetInt32(1),
                reader.GetInt64(2)));
        }

        return result;
    }

    private async Task<IReadOnlyList<LoadoutResponse>> GetLoadoutsAsync(
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT hero_class, head_id, chest_id, hands_id, legs_id, feet_id, version
            FROM player_loadouts WHERE player_id = $1 ORDER BY hero_class
            """);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<LoadoutResponse>();
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new LoadoutResponse(
                (HeroClassDto)reader.GetInt16(0),
                Enumerable.Range(1, 5)
                    .Select(index => reader.IsDBNull(index) ? null : (Guid?)reader.GetGuid(index))
                    .ToArray(),
                reader.GetInt64(6)));
        }

        return result;
    }

    private async Task<InventorySummaryResponse> GetInventorySummaryAsync(
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT count(*)::integer FROM equipments WHERE owner_id = $1 AND location = 'Inventory'");
        command.Parameters.AddWithValue(playerId);
        var count = (int)(await command.ExecuteScalarAsync(cancellationToken) ?? 0);
        const int capacity = 50;
        return new InventorySummaryResponse(capacity, count, capacity - count);
    }
}
