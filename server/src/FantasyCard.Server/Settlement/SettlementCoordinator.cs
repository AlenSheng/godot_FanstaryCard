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
                        ? ExtractedAssets(player)
                        : DeadAssets(snapshot, player);
                    using var details = JsonDocument.Parse(JsonSerializer.Serialize(new
                    {
                        snapshot.RoomId,
                        snapshot.Revision,
                        player.Phase,
                        player.Position,
                        heroClass = player.HeroClass.ToString(),
                        assetCount = assets.Length
                    }));
                    await repository.SettleAsync(
                        matchId,
                        player.PlayerId,
                        result,
                        details.RootElement,
                        assets,
                        CancellationToken.None);
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

    private static SettlementAsset[] ExtractedAssets(RoomPlayerSnapshot player)
    {
        var assets = (player.Inventory?.Items ?? [])
            .Select(item => ToAsset(item, "Inventory"))
            .Concat((player.WornArmor ?? []).Select(item => ToAsset(item, "Equipped")))
            .Concat((player.RecycledEquipment ?? []).Select(item => ToAsset(item, "Recycled")))
            .ToList();
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

    private static SettlementAsset ToAsset(ExplorationItem item, string equipmentDestination) =>
        new(item.Kind.ToString(), item.ItemId, item.IsSafe, item.Quantity,
            item.IsGenerated == false ? null : item.Equipment,
            item.Kind == ExplorationItemKind.Equipment ? equipmentDestination : null);
}
