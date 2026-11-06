using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Matches;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Matchmaking;

namespace FantasyCard.Server.Tests.Config;

/// <summary>F01 preparation binding only. It never matches players, starts a map, consumes holds or advances time.</summary>
internal sealed class SeasonFirstFortnightPreparedController(PreparationRepository preparations, TimeProvider clock, SeasonDefinition season)
{
    private static readonly string[] EquipmentSlots = ["Head", "Chest", "Hands", "Legs", "Feet"];

    internal sealed record BoundPreparation(
        Guid PreparationId,
        Guid PlayerId,
        DateTimeOffset ScheduledAtUtc,
        PreparationSnapshotResponse Snapshot,
        SeasonContext Context,
        BattleRoom UnstartedRoom);

    /// <summary>Fetch the caller's actual active preparation instead of accepting an arbitrary actor snapshot.</summary>
    internal async Task<BoundPreparation> BindAsync(SeasonFirstFortnightInputsTests.Actor actor, Guid playerId,
        Guid preparationId, DateTimeOffset scheduledAtUtc, int seed, CancellationToken cancellationToken)
    {
        if (clock.GetUtcNow() != scheduledAtUtc)
            throw new InvalidOperationException("The F01 controller clock differs from the scheduled start.");
        var preparation = await preparations.GetActiveAsync(playerId, cancellationToken)
            ?? throw new InvalidOperationException("The F01 preparation is no longer active for this player.");
        if (preparation.PreparationId != preparationId)
            throw new InvalidOperationException("The F01 preparation identity differs from the active owner binding.");
        return BindCaptured(actor, playerId, preparation, season, scheduledAtUtc, seed);
    }

    /// <summary>Validate current frozen inputs and preserve their real backpack, safe slots, armor and potions.</summary>
    internal static BoundPreparation BindCaptured(SeasonFirstFortnightInputsTests.Actor actor, Guid playerId,
        PreparationResponse preparation, SeasonDefinition season, DateTimeOffset scheduledAtUtc, int seed)
    {
        scheduledAtUtc = scheduledAtUtc.ToUniversalTime();
        if (playerId == Guid.Empty || preparation.Status != "Active" || scheduledAtUtc < preparation.CreatedAt
            || scheduledAtUtc >= preparation.ExpiresAt || !season.Contains(scheduledAtUtc))
            throw new InvalidOperationException("The F01 preparation is not active at the scheduled time.");
        var config = GameConfigCatalog.Current;
        var snapshot = preparation.Snapshot;
        var source = snapshot.Season ?? throw new InvalidOperationException("F01 requires an actual seasonal preparation.");
        if (snapshot.ConfigVersion != config.Version || source.ConfigVersion != config.Version
            || snapshot.HeroClass != (FantasyCard.Contracts.Players.HeroClassDto)(int)actor.Hero
            || !snapshot.CardIds.SequenceEqual(actor.Cards, StringComparer.Ordinal)
            || snapshot.BorrowedTemplateId is not null)
            throw new InvalidOperationException("The F01 owned-deck preparation differs from its declared actor.");
        if (source.DifficultyId != snapshot.Difficulty || snapshot.Difficulty.Length != 2 || snapshot.Difficulty[0] != 'D'
            || snapshot.Difficulty[1] is < '0' or > '5')
            throw new InvalidOperationException("The F01 difficulty identity is inconsistent.");
        var context = new SeasonContext(source.SeasonId, snapshot.Difficulty[1] - '0', source.RulesetId,
            source.ConfigVersion, source.StatsVersion);
        if (context != season.ContextFor(context.Difficulty))
            throw new InvalidOperationException("The F01 preparation differs from the declared original season.");
        var levels = snapshot.CardLevels ?? throw new InvalidOperationException("F01 requires frozen effective card levels.");
        var actualLevels = snapshot.ActualCardLevels ?? throw new InvalidOperationException("F01 requires actual owned card levels.");
        var actualWeapon = snapshot.ActualClassWeaponLevel ?? throw new InvalidOperationException("F01 requires the actual weapon level.");
        if (levels.Count != 20 || actualLevels.Count != 20
            || !levels.SequenceEqual(actualLevels.Select(context.ProjectPermanentLevel))
            || snapshot.ClassWeaponLevel != context.ProjectPermanentLevel(actualWeapon))
            throw new InvalidOperationException("The F01 preparation does not preserve the actual seasonal level projection.");
        PreparationRules.Validate(snapshot.EquipmentIds, (BackpackTier)(int)snapshot.BackpackTier,
            snapshot.SafeSlotIndexes, snapshot.PotionCount);
        var backpack = config.Backpack(snapshot.BackpackTier.ToString());
        if (snapshot.BackpackCapacity != backpack.Capacity)
            throw new InvalidOperationException("The F01 frozen backpack capacity differs from its original catalog.");
        var equipment = snapshot.EquipmentSnapshots
            ?? throw new InvalidOperationException("F01 requires the current frozen equipment detail collection.");
        if (equipment.Count != snapshot.EquipmentIds.Count(id => id.HasValue))
            throw new InvalidOperationException("The F01 equipment IDs and frozen details differ.");
        var worn = new List<ExplorationItem>();
        for (var index = 0; index < snapshot.EquipmentIds.Count; index++)
        {
            if (snapshot.EquipmentIds[index] is not { } itemId) continue;
            var item = equipment.Single(value => value.InstanceId == itemId);
            if (item.Slot != EquipmentSlots[index] || item.StatsVersion != context.StatsVersion)
                throw new InvalidOperationException("The F01 equipment slot or stats version is inconsistent.");
            worn.Add(new(itemId.ToString("D"), ExplorationItemKind.Equipment, Equipment: new(
                item.Slot, item.Quality, item.Element, item.EffectAffix, item.SecondaryTrait, item.Level,
                UniqueAffix: item.UniqueAffix, UniqueElement: item.UniqueElement, StatsVersion: item.StatsVersion), IsGenerated: false));
        }
        var room = new BattleRoom(Guid.NewGuid(), config.Version, CombatCardCatalog.Create(config), seed,
            NumericalRules.ForSeason(config, context.Difficulty), context);
        var player = room.AddPlayer(new(playerId, actor.Hero, snapshot.CardIds, null,
            WeaponLevel: snapshot.ClassWeaponLevel, InventoryCapacity: snapshot.BackpackCapacity,
            SafeSlots: snapshot.SafeSlotIndexes.Count, WornArmor: worn,
            SafeSlotIndexes: snapshot.SafeSlotIndexes, CardLevels: levels, LootPreferenceElement: snapshot.LootPreferenceElement));
        for (var index = 0; index < snapshot.PotionCount; index++)
            if (!player.Inventory.TryAdd(new("health_potion:" + (index + 1), ExplorationItemKind.HealthPotion)))
                throw new InvalidOperationException("The actual prepared potions do not fit the F01 inventory.");
        if (room.Elapsed != TimeSpan.Zero || room.CapturePlayer(playerId).Combat.MaximumHp != snapshot.MaximumHp)
            throw new InvalidOperationException("The F01 unstarted state differs from the preparation.");
        return new(preparation.PreparationId, playerId, scheduledAtUtc, snapshot, context, room);
    }
}
