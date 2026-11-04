using FantasyCard.Contracts.Bootstrap;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Seasons;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Players;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;
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
        var snapshotTime = timeProvider.GetUtcNow();
        var seasons = new SeasonRepository(dataSource, timeProvider);
        var schedule = await seasons.GetScheduleAtAsync(snapshotTime, cancellationToken);
        var seasonContext = schedule.Current?.ContextFor(0);
        var seasonWalletTask = seasonContext is null ? Task.FromResult<SeasonWalletSnapshot?>(null)
            : seasons.GetWalletAsync(player.UserId, seasonContext, cancellationToken);
        var seasonWalletsTask = seasons.GetWalletsAsync(player.UserId, snapshotTime, cancellationToken);
        var decksTask = progressionRepository.GetDecksAsync(player.UserId, cancellationToken);
        var cardsTask = progressionRepository.GetCardsAsync(player.UserId, cancellationToken);
        var coreTask = GetCoreStateAsync(player.UserId, cancellationToken);
        var inventoryFullTask = progressionRepository.GetInventoryForScheduleAsync(player.UserId, schedule, cancellationToken);
        var shopTask = economyRepository.GetShopForScheduleAsync(player.UserId,schedule,cancellationToken);
        var marketTask = economyRepository.GetMarketForScheduleAsync(schedule,cancellationToken);
        var mailTask = mailRepository.GetAsync(player.UserId, cancellationToken);
        var activePreparationTask = preparationRepository.GetActiveAsync(player.UserId, cancellationToken);

        await Task.WhenAll(decksTask, cardsTask, coreTask, inventoryFullTask, shopTask, marketTask, mailTask,
            activePreparationTask, seasonWalletTask, seasonWalletsTask);
        var core = await coreTask;
        var seasonWallet = await seasonWalletTask;
        var wallet = schedule.LegacyAllowed ? core.Wallet
            : core.Wallet with { Gold = seasonWallet?.Gold ?? 0 };
        var materials = schedule.LegacyAllowed ? core.Materials
            : core.Materials with { EquipmentFragments = seasonWallet?.EquipmentFragments ?? 0 };
        var inventory = await inventoryFullTask;
        var visibleEquipment = inventory.Equipments.Select(item => item.InstanceId).ToHashSet();
        var loadouts = schedule.LegacyAllowed ? core.Loadouts
            : core.Loadouts.Select(loadout => loadout with
            {
                EquipmentIds = loadout.EquipmentIds.Select(id => id.HasValue && visibleEquipment.Contains(id.Value) ? id : null).ToArray(),
                SeasonId = schedule.Current?.SeasonId
            }).ToArray();
        SeasonSummaryResponse? season = null;
        if (schedule.Stage != SeasonLifecycleStage.Legacy)
        {
            var current = schedule.Current;
            var unlocked = current is null || seasonWallet is null ? 0
                : await seasons.GetUnlockedDifficultyAsync(player.UserId, current.SeasonId, cancellationToken);
            season = new(schedule.Stage.ToString(), current?.SeasonId, current?.RulesetId, current?.ConfigVersion,
                current?.StatsVersion, current?.StartsAtUtc, current?.EndsAtUtc, current?.HighestOpenDifficulty ?? 0,
                Math.Min(unlocked, current?.HighestOpenDifficulty ?? 0), schedule.LegacyAllowed ? 5 : 0,
                core.Materials.EquipmentFragments, schedule.Next?.SeasonId, schedule.Next?.StartsAtUtc,
                seasonWallet is null ? null : WalletResponseFor(seasonWallet, true),
                (await seasonWalletsTask).Select(entry => WalletResponseFor(entry.Wallet, entry.CanFundWeapon)).ToArray(),
                seasonWallet is not null, seasonContext?.DifficultyId ?? "");
        }
        return new BootstrapResponse(
            snapshotTime,
            CurrentConfigVersion,
            player.ToResponse(),
            wallet,
            materials,
            core.Weapons,
            loadouts,
            await decksTask,
            await cardsTask,
            inventory.Summary,
            core.Match,
            core.Settlement)
        {
            Inventory = inventory,
            Shop = await shopTask,
            Market = await marketTask,
            Mail = await mailTask,
            ActivePreparation = await activePreparationTask,
            Season = season
        };
    }

    private static SeasonWalletResponse WalletResponseFor(SeasonWalletSnapshot wallet, bool canFundWeapon) =>
        new(wallet.SeasonId, wallet.Gold, wallet.EquipmentFragments, wallet.ChallengeMarks,
            wallet.Version, wallet.ArchivedAt, canFundWeapon,wallet.BlueprintMarks,wallet.OrangeBlueprintMarks);

    public async Task<BootstrapSettlementProjection> GetSettlementAsync(
        Guid playerId,
        Guid matchId,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand("""
            SELECT s.settlement_id,s.match_id,s.player_id,s.result,s.details_json::text,s.created_at,
                   s.config_version,s.season_id,s.difficulty_id,s.ruleset_id,s.stats_version
            FROM match_settlements s
            WHERE s.player_id=$1 AND s.match_id=$2
              AND s.acknowledged_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM settlement_asset_holds h
                  WHERE h.settlement_id=s.settlement_id AND h.state='Pending')
            ORDER BY s.created_at DESC,s.settlement_id DESC
            LIMIT 1
            """, connection);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(matchId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        SettlementResponse? settlement = null;
        if (await reader.ReadAsync(cancellationToken))
        {
            settlement = SettlementRepository.ReadResponse(reader);
        }
        return new BootstrapSettlementProjection(timeProvider.GetUtcNow(), CurrentConfigVersion, settlement);
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
            SELECT s.settlement_id,s.match_id,s.player_id,s.result,s.details_json::text,s.created_at,
                   s.config_version,s.season_id,s.difficulty_id,s.ruleset_id,s.stats_version
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
            settlement = SettlementRepository.ReadResponse(reader);
        }
        return new CoreState(wallet, materials, weapons, loadouts, match, settlement);
    }
}
