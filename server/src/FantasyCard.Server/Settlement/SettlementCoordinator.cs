using System.Text.Json;
using System.Collections.Concurrent;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Settlement;

public sealed class SettlementCoordinator(
    SettlementRepository repository,
    TimeProvider? timeProvider = null)
{
    private const int MaximumTrackedSettlements = 4096;
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private readonly TimeProvider _timeProvider = timeProvider ?? TimeProvider.System;
    private readonly ConcurrentDictionary<SettlementKey, DateTimeOffset> _completed = new();
    private readonly ConcurrentDictionary<SettlementKey, byte> _inFlight = new();

    public async Task ObserveAsync(Guid matchId, BattleRoomSnapshot snapshot)
    {
        foreach (var player in snapshot.Players)
        {
            var result = player.Phase switch
            {
                FantasyCard.Domain.Combat.RoomPlayerPhase.Extracted => "Extracted",
                FantasyCard.Domain.Combat.RoomPlayerPhase.Dead => "Dead",
                _ => null
            };
            if (result is null) continue;

            var key = new SettlementKey(matchId, player.PlayerId);
            if (_completed.ContainsKey(key) || !_inFlight.TryAdd(key, 0))
                continue;

            try
            {
                if (player.IsBot)
                {
                    await repository.CompleteBotAsync(matchId, player.PlayerId, CancellationToken.None);
                }
                else
                {
                    var assets = result == "Extracted"
                        ? ExtractedAssets(snapshot,player)
                        : DeadAssets(snapshot, player);
                    var items = SettlementItems(player, result);
                    var cleared = (snapshot.Map?.Cells ?? []).Where(cell => (player.ClearedCells ?? []).Contains(cell.Position)).ToArray();
                    using var details = JsonDocument.Parse(JsonSerializer.Serialize(new
                    {
                        snapshot.RoomId,
                        snapshot.Revision,
                        snapshot.ConfigVersion,
                        snapshot.Season,
                        player.Phase,
                        player.Position,
                        player.BotVictoryReward,
                        player.ExtractionCompletedAt,
                        player.JourneyCompletions,
                        snapshot.StartedAtUtc,
                        player.TerminalRoomElapsed,
                        heroClass = player.HeroClass.ToString(),
                        assetCount = assets.Length,
                        difficultyProgress = new
                        {
                            eliteCleared = cleared.Any(cell => cell.MonsterGroupId.StartsWith('E')),
                            bossCleared = cleared.Any(cell => cell.IsBoss || cell.MonsterGroupId == "BOSS")
                        },
                        items
                    }, Json));
                    await repository.SettleAsync(
                        matchId,
                        player.PlayerId,
                        result,
                        details.RootElement,
                        assets,
                        CancellationToken.None, snapshot.Season, snapshot.ConfigVersion);
                }

                _completed[key] = _timeProvider.GetUtcNow();
                PruneCompleted(_timeProvider.GetUtcNow());
            }
            catch
            {
                // A failed settlement must remain retryable on the next room
                // observation; only successful durable work is remembered.
                throw;
            }
            finally
            {
                _inFlight.TryRemove(key, out _);
            }
        }
    }

    private void PruneCompleted(DateTimeOffset now)
    {
        if (_completed.Count <= MaximumTrackedSettlements) return;
        foreach (var entry in _completed)
        {
            if (now - entry.Value <= TimeSpan.FromHours(1)) continue;
            _completed.TryRemove(entry.Key, out _);
        }
    }

    private readonly record struct SettlementKey(Guid MatchId, Guid PlayerId);

    private sealed record SettlementDisplayItem(SettlementDisplayAsset Item, bool Equipped);
    private sealed record SettlementDisplayAsset(
        string ItemId, string Kind, int Quantity, bool IsSafe, EquipmentRewardData? Equipment);

    private static SettlementDisplayItem[] SettlementItems(RoomPlayerSnapshot player, string result)
    {
        var inventory = (player.Inventory?.Items ?? [])
            .Where(item => result == "Extracted" || item.IsSafe)
            .Select(item => DisplayItem(item, false));
        var worn = result == "Extracted"
            ? (player.WornArmor ?? []).Select(item => DisplayItem(item, true))
            : Enumerable.Empty<SettlementDisplayItem>();
        return [.. inventory.Concat(worn)];
    }

    private static SettlementDisplayItem DisplayItem(ExplorationItem item, bool equipped) =>
        new(new(item.ItemId, item.Kind.ToString(), item.Quantity, item.IsSafe, item.Equipment), equipped);

    private SettlementAsset[] ExtractedAssets(BattleRoomSnapshot snapshot,RoomPlayerSnapshot player)
    {
        var assets = (player.Inventory?.Items ?? [])
            .Select(item => ToAsset(item, "Inventory"))
            .Concat((player.WornArmor ?? []).Select(item => ToAsset(item, "Equipped")))
            .Concat((player.RecycledEquipment ?? []).Select(item => ToAsset(item, "Recycled")))
            .ToList();
        if (snapshot.Season is { } season && repository.ConfigurationFor(snapshot.ConfigVersion).SeasonCrafting is { } crafting)
        {
            var cleared = (snapshot.Map?.Cells ?? []).Where(cell => (player.ClearedCells ?? []).Contains(cell.Position));
            var pending = crafting.Pending(season.Difficulty,player.IsBot,cleared);
            if (pending.Blueprints > 0) assets.Add(new("BlueprintMarks","blueprint",false,pending.Blueprints));
            if (pending.OrangeBlueprints > 0) assets.Add(new("OrangeBlueprintMarks","orange-blueprint",false,pending.OrangeBlueprints));
        }
        return [.. assets];
    }

    private static SettlementAsset[] DeadAssets(BattleRoomSnapshot snapshot, RoomPlayerSnapshot player)
    {
        var assets = (player.Inventory?.Items ?? [])
            .Where(item => item.IsSafe)
            .Select(item => ToAsset(item, "Inventory"))
            .ToList();
        var victimId = player.PlayerId.ToString("D");
        assets.AddRange((snapshot.RelicPiles ?? [])
            .Where(pile => string.Equals(pile.VictimId, victimId, StringComparison.Ordinal))
            .SelectMany(pile => pile.Items)
            .Where(item => item.Kind == ExplorationItemKind.Equipment)
            .Select(item => ToAsset(item, "RelicPile")));
        assets.AddRange((player.RecycledEquipment ?? []).Select(item => ToAsset(item, "Recycled")));
        if (player.Inventory?.Capacity == 28)
            assets.Add(new("Backpack", "Advanced", false));
        else if (player.Inventory?.Capacity == 36)
            assets.Add(new("Backpack", "Top", false));
        return [.. assets.DistinctBy(asset => (asset.AssetKind, asset.AssetId))];
    }

    private static SettlementAsset ToAsset(ExplorationItem item, string equipmentDestination)
    {
        if(item.IsCombatProjection)throw new InvalidOperationException("Combat projections cannot be settled as assets.");
        return new(item.Kind.ToString(), item.ItemId, item.IsSafe, item.Quantity,
            item.IsGenerated == false ? null : item.Equipment,
            item.Kind == ExplorationItemKind.Equipment ? equipmentDestination : null);
    }
}
