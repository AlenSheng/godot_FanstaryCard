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
        var coreTask = GetCoreStateAsync(player.UserId, cancellationToken);
        var inventoryFullTask = progressionRepository.GetInventoryAsync(player.UserId, cancellationToken);
        var shopTask = economyRepository.GetShopAsync(player.UserId, cancellationToken);
        var marketTask = economyRepository.GetMarketAsync(cancellationToken);
        var mailTask = mailRepository.GetAsync(player.UserId, cancellationToken);
        var activePreparationTask = preparationRepository.GetActiveAsync(player.UserId, cancellationToken);

        await Task.WhenAll(decksTask, cardsTask, coreTask, inventoryFullTask, shopTask, marketTask, mailTask,
            activePreparationTask);
        var core = await coreTask;
        return new BootstrapResponse(
            timeProvider.GetUtcNow(),
            CurrentConfigVersion,
            player.ToResponse(),
            core.Wallet,
            core.Materials,
            core.Weapons,
            core.Loadouts,
            await decksTask,
            await cardsTask,
            (await inventoryFullTask).Summary,
            core.Match,
            core.Settlement)
        {
            Inventory = await inventoryFullTask,
            Shop = await shopTask,
            Market = await marketTask,
            Mail = await mailTask,
            ActivePreparation = await activePreparationTask
        };
    }

    private sealed record CoreState(
        WalletResponse Wallet, MaterialsResponse Materials,
        IReadOnlyList<ClassWeaponResponse> Weapons, IReadOnlyList<LoadoutResponse> Loadouts,
        UnfinishedMatchResponse? Match, SettlementResponse? Settlement);

    private async Task<CoreState> GetCoreStateAsync(Guid playerId, CancellationToken cancellationToken)
    {
        // Independent result sets preserve one-to-many rows without a Cartesian join.
        // Only read queries belong here; shop initialization keeps its own transaction.
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var batch = new NpgsqlBatch(connection);
        string[] queries =
        [
            "SELECT gold, diamond FROM player_wallets WHERE player_id = $1",
            "SELECT warrior_soul, priest_soul, mage_soul, guardian_soul, equipment_fragments FROM player_materials WHERE player_id = $1",
            "SELECT hero_class, level, version FROM class_weapons WHERE player_id = $1 ORDER BY hero_class",
            "SELECT hero_class, head_id, chest_id, hands_id, legs_id, feet_id, version FROM player_loadouts WHERE player_id = $1 ORDER BY hero_class",
            """
            SELECT m.match_id,m.room_id,m.status,rs.revision,m.config_version
            FROM match_players mp
            JOIN matches m ON m.match_id=mp.match_id
            LEFT JOIN room_snapshots rs ON rs.room_id=m.room_id
            WHERE mp.player_id=$1 AND mp.is_bot=false
              AND ((m.status='Starting' AND mp.state='Ready')
                OR (m.status IN ('Launching','Running') AND mp.state='Active'))
            ORDER BY m.created_at DESC
            LIMIT 1
            """,
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
            """
        ];
        foreach (var sql in queries)
        {
            var command = new NpgsqlBatchCommand(sql);
            command.Parameters.AddWithValue(playerId);
            batch.BatchCommands.Add(command);
        }
        await using var reader = await batch.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
            throw new InvalidOperationException("Player wallet was not provisioned.");
        var wallet = new WalletResponse(reader.GetInt64(0), reader.GetInt64(1));
        await reader.NextResultAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
            throw new InvalidOperationException("Player materials were not provisioned.");
        var materials = new MaterialsResponse(reader.GetInt64(0), reader.GetInt64(1),
            reader.GetInt64(2), reader.GetInt64(3), reader.GetInt64(4));
        await reader.NextResultAsync(cancellationToken);
        var weapons = new List<ClassWeaponResponse>();
        while (await reader.ReadAsync(cancellationToken))
            weapons.Add(new ClassWeaponResponse((HeroClassDto)reader.GetInt16(0), reader.GetInt32(1), reader.GetInt64(2)));
        await reader.NextResultAsync(cancellationToken);
        var loadouts = new List<LoadoutResponse>();
        while (await reader.ReadAsync(cancellationToken))
            loadouts.Add(new LoadoutResponse((HeroClassDto)reader.GetInt16(0),
                Enumerable.Range(1, 5).Select(index => reader.IsDBNull(index) ? null : (Guid?)reader.GetGuid(index)).ToArray(),
                reader.GetInt64(6)));
        await reader.NextResultAsync(cancellationToken);
        UnfinishedMatchResponse? match = null;
        if (await reader.ReadAsync(cancellationToken))
            match = new UnfinishedMatchResponse(reader.GetGuid(0), reader.GetGuid(1), reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetInt64(3), reader.GetString(4));
        await reader.NextResultAsync(cancellationToken);
        SettlementResponse? settlement = null;
        if (await reader.ReadAsync(cancellationToken))
        {
            using var details = JsonDocument.Parse(reader.GetString(4));
            settlement = new SettlementResponse(reader.GetGuid(0), reader.GetGuid(1), reader.GetGuid(2),
                reader.GetString(3), details.RootElement.Clone(), reader.GetFieldValue<DateTimeOffset>(5));
        }
        return new CoreState(wallet, materials, weapons, loadouts, match, settlement);
    }
}
