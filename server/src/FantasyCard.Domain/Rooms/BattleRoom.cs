using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Bots;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Rooms;

public sealed record BattleRoomPlayerSetup(
    Guid PlayerId,
    HeroClass HeroClass,
    IReadOnlyList<string> CardIds,
    PveBattleState? Pve,
    int WeaponLevel = 0,
    int InventoryCapacity = 20,
    int SafeSlots = 0,
    IReadOnlyList<ExplorationItem>? WornArmor = null,
    bool IsBot = false,
    CombatEquipmentProfile? Equipment = null,
    IReadOnlyList<int>? SafeSlotIndexes = null,
    string? DisplayName = null,
    IReadOnlyList<int>? CardLevels = null);

public sealed record DuelEscapeRequestResult(Guid DuelId, double Probability, long RoomRevision);
public sealed record RoomMoveResult(MapPosition Position, DuelStateSnapshot? StartedDuel, long RoomRevision);
public sealed record PotionUseResult(string ItemId, int Healed, long RoomRevision);

public sealed class RoomPlayerState
{
    internal RoomPlayerState(
        Guid playerId,
        HeroClass heroClass,
        PlayerCombatState combat,
        PveBattleState? pve,
        int inventoryCapacity,
        int safeSlots,
        IReadOnlyList<ExplorationItem>? wornArmor,
        bool isBot,
        IReadOnlyList<int>? safeSlotIndexes,
        string? displayName)
    {
        PlayerId = playerId;
        HeroClass = heroClass;
        Combat = combat;
        Pve = pve;
        Inventory = new ExplorationInventory(inventoryCapacity, safeSlots, safeSlotIndexes);
        WornArmor = (wornArmor ?? []).Select(item => item with { SlotIndex = -1, IsSafe = false }).ToArray();
        DisplayName = displayName;
        IsBot = isBot;
        Phase = pve is null ? RoomPlayerPhase.ActionBar : RoomPlayerPhase.Pve;
    }

    public Guid PlayerId { get; }
    public HeroClass HeroClass { get; }
    public RoomPlayerPhase Phase { get; internal set; }
    public Guid? CurrentDuelId { get; internal set; }
    public PlayerCombatState Combat { get; }
    public PveBattleState? Pve { get; internal set; }
    public MapPosition? Position { get; internal set; }
    public ExplorationInventory Inventory { get; }
    public IReadOnlyList<ExplorationItem> WornArmor { get; internal set; }
    public string? DisplayName { get; }
    internal List<ExplorationItem> RecycledEquipment { get; } = [];
    public bool IsBot { get; }
    public RewardChoiceState? RewardChoice { get; internal set; }
    public int RewardRefreshCount { get; internal set; }
    internal List<RewardRefreshReceiptSnapshot> RewardRefreshReceipts { get; } = [];
    internal HashSet<MapPosition> ClearedCells { get; } = [];
    internal HashSet<MapPosition> ConsumedSprings { get; } = [];

    internal RoomPlayerSnapshot Capture(
        TimeSpan? extractionRemaining = null,
        TimeSpan? disconnectedRemaining = null,
        SpringDrinkSnapshot? springDrink = null,
        TimeSpan? botPveRemaining = null) =>
        new(
            PlayerId,
            HeroClass,
            Phase,
            CurrentDuelId,
            Combat.Capture(),
            Pve?.Capture(),
            Position,
            Inventory.Capture(),
            WornArmor,
            extractionRemaining,
            disconnectedRemaining,
            RewardChoice?.Capture(),
            RewardRefreshCount,
            ClearedCells.OrderBy(p => p.Row).ThenBy(p => p.Column).ToArray(),
            ConsumedSprings.OrderBy(p => p.Row).ThenBy(p => p.Column).ToArray(),
            springDrink,
            IsBot,
            botPveRemaining,
            RewardRefreshReceipts.ToArray(),
            RecycledEquipment.ToArray(),
            DisplayName);
}

public sealed class DuelState
{
    private readonly HashSet<Guid> _leaveRequests = [];
    private readonly Dictionary<Guid, TimeSpan> _escapeCooldowns = [];
    private EscapeAttempt? _escapeAttempt;
    internal DuelState(
        Guid duelId,
        Guid firstPlayerId,
        Guid latePlayerId,
        DateTimeOffset startedAt,
        FrozenParticipantState firstFrozen,
        FrozenParticipantState lateFrozen)
    {
        DuelId = duelId;
        FirstPlayerId = firstPlayerId;
        LatePlayerId = latePlayerId;
        StartedAt = startedAt;
        LatePlayerUnlockAt = startedAt.AddMilliseconds(800);
        LeaveWindowEndsAt = startedAt.AddSeconds(8);
        FirstFrozen = firstFrozen;
        LateFrozen = lateFrozen;
    }

    public Guid DuelId { get; }
    public Guid FirstPlayerId { get; }
    public Guid LatePlayerId { get; }
    public DateTimeOffset StartedAt { get; }
    public DateTimeOffset LatePlayerUnlockAt { get; }
    public DateTimeOffset LeaveWindowEndsAt { get; }
    public bool HasRequestedLeave(Guid playerId) => _leaveRequests.Contains(playerId);

    internal bool RegisterLeave(Guid playerId, DateTimeOffset now)
    {
        if (now > LeaveWindowEndsAt)
            throw new DomainValidationException("The duel leave window has expired.");
        if (playerId != FirstPlayerId && playerId != LatePlayerId)
            throw new DomainValidationException("Player is not a participant in this duel.");
        _leaveRequests.Add(playerId);
        return _leaveRequests.Count == 2;
    }

    internal void BeginEscape(Guid playerId, double probability, int hpAtStart)
    {
        if (playerId != FirstPlayerId && playerId != LatePlayerId)
            throw new DomainValidationException("Player is not a participant in this duel.");
        if (_escapeAttempt is not null)
            throw new DomainValidationException("An escape attempt is already in progress.");
        if (_escapeCooldowns.TryGetValue(playerId, out var cooldown) && cooldown > TimeSpan.Zero)
            throw new DomainValidationException("Escape is on cooldown.");
        _escapeAttempt = new EscapeAttempt(playerId, TimeSpan.FromSeconds(2), probability, hpAtStart);
    }

    internal EscapeTickResult TickEscape(
        TimeSpan delta,
        PlayerCombatState first,
        PlayerCombatState late,
        Random random)
    {
        foreach (var playerId in _escapeCooldowns.Keys.ToArray())
        {
            var remaining = _escapeCooldowns[playerId] - delta;
            if (remaining <= TimeSpan.Zero) _escapeCooldowns.Remove(playerId);
            else _escapeCooldowns[playerId] = remaining;
        }
        if (_escapeAttempt is not { } attempt) return EscapeTickResult.None;
        var combat = attempt.PlayerId == FirstPlayerId ? first : late;
        if (combat.Hp < attempt.HpAtStart)
        {
            _escapeAttempt = null;
            return EscapeTickResult.Interrupted;
        }
        var remainingTime = attempt.Remaining - delta;
        if (remainingTime > TimeSpan.Zero)
        {
            _escapeAttempt = attempt with { Remaining = remainingTime };
            return EscapeTickResult.Pending;
        }
        _escapeAttempt = null;
        if (random.NextDouble() <= attempt.Probability) return EscapeTickResult.Succeeded;
        _escapeCooldowns[attempt.PlayerId] = TimeSpan.FromSeconds(12);
        return EscapeTickResult.Failed;
    }
    internal FrozenParticipantState FirstFrozen { get; }
    internal FrozenParticipantState LateFrozen { get; }

    internal FrozenParticipantState FrozenFor(Guid playerId) =>
        playerId == FirstPlayerId ? FirstFrozen :
        playerId == LatePlayerId ? LateFrozen :
        throw new DomainValidationException("Player is not a participant in this duel.");

    internal Guid OpponentOf(Guid playerId) =>
        playerId == FirstPlayerId ? LatePlayerId :
        playerId == LatePlayerId ? FirstPlayerId :
        throw new DomainValidationException("Player is not a participant in this duel.");

    public DuelStateSnapshot Capture() =>
        new(
            DuelId,
            FirstPlayerId,
            LatePlayerId,
            StartedAt,
            LatePlayerUnlockAt,
            LeaveWindowEndsAt,
            new FrozenParticipantSnapshot(FirstFrozen.Phase, FirstFrozen.Combat, FirstFrozen.Pve),
            new FrozenParticipantSnapshot(LateFrozen.Phase, LateFrozen.Combat, LateFrozen.Pve),
            _leaveRequests.ToArray(),
            _escapeCooldowns.Select(value => new DuelCooldownSnapshot(value.Key, value.Value)).ToArray(),
            _escapeAttempt is { } attempt
                ? new DuelEscapeAttemptSnapshot(attempt.PlayerId, attempt.Remaining, attempt.Probability, attempt.HpAtStart)
                : null);

    internal static DuelState Restore(DuelStateSnapshot snapshot)
    {
        if (snapshot.FirstFrozen is null || snapshot.LateFrozen is null)
            throw new InvalidOperationException("A duel snapshot is missing its frozen participant state.");
        var duel = new DuelState(
            snapshot.DuelId,
            snapshot.FirstPlayerId,
            snapshot.LatePlayerId,
            snapshot.StartedAt,
            new FrozenParticipantState(snapshot.FirstFrozen.Phase, snapshot.FirstFrozen.Combat, snapshot.FirstFrozen.Pve),
            new FrozenParticipantState(snapshot.LateFrozen.Phase, snapshot.LateFrozen.Combat, snapshot.LateFrozen.Pve));
        foreach (var playerId in snapshot.LeaveRequests ?? []) duel._leaveRequests.Add(playerId);
        foreach (var cooldown in snapshot.EscapeCooldowns ?? []) duel._escapeCooldowns[cooldown.PlayerId] = cooldown.Remaining;
        if (snapshot.EscapeAttempt is { } attempt)
            duel._escapeAttempt = new EscapeAttempt(attempt.PlayerId, attempt.Remaining, attempt.Probability, attempt.HpAtStart);
        return duel;
    }
}

internal sealed record EscapeAttempt(Guid PlayerId, TimeSpan Remaining, double Probability, int HpAtStart);
public enum EscapeTickResult { None, Pending, Interrupted, Failed, Succeeded }

internal sealed record FrozenParticipantState(
    RoomPlayerPhase Phase,
    PlayerCombatSnapshot Combat,
    PveBattleSnapshot? Pve);

public sealed record CeasefireSnapshot(Guid FirstPlayerId, Guid SecondPlayerId, TimeSpan Remaining);

internal sealed record Ceasefire(Guid FirstPlayerId, Guid SecondPlayerId, TimeSpan Remaining)
{
    public bool Includes(Guid first, Guid second) =>
        (FirstPlayerId == first && SecondPlayerId == second) ||
        (FirstPlayerId == second && SecondPlayerId == first);
}

public sealed partial class BattleRoom
{
    private readonly CombatCardCatalog _catalog;
    private readonly CombatRandom _legacyRandom;
    private readonly CombatRandom _playerSeedRandom;
    private readonly CombatRandom _rewardRandom;
    private readonly CombatRandom _lootRandom;
    private readonly CombatRandom _escapeRandom;
    private readonly CombatRandom _botRandom;
    private readonly CombatRandom _duelRandom;
    private bool _useLegacyRandom;
    private readonly Dictionary<Guid, RoomPlayerState> _players = [];
    private readonly Dictionary<Guid, DuelState> _duels = [];
    private readonly List<Ceasefire> _ceasefires = [];
    private readonly Dictionary<Guid, RelicPile> _relicPiles = [];
    private readonly Dictionary<Guid, TimeSpan> _extractions = [];
    private readonly Dictionary<Guid, TimeSpan> _disconnects = [];
    private readonly Dictionary<Guid, SpringDrinkSnapshot> _springDrinks = [];
    private readonly Dictionary<Guid, TimeSpan> _botPveRemaining = [];
    private readonly Dictionary<Guid, TimeSpan> _botDuelRemaining = [];
    private readonly List<CombatFeedbackResolution> _combatFeedback = [];

    public BattleRoom(Guid roomId, string configVersion, CombatCardCatalog catalog, int seed)
    {
        if (roomId == Guid.Empty)
        {
            throw new ArgumentException("Room id cannot be empty.", nameof(roomId));
        }
        ArgumentException.ThrowIfNullOrWhiteSpace(configVersion);
        RoomId = roomId;
        ConfigVersion = configVersion;
        _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
        _legacyRandom = new CombatRandom(seed);
        _playerSeedRandom = new CombatRandom(_legacyRandom.Next());
        _rewardRandom = new CombatRandom(_legacyRandom.Next());
        _lootRandom = new CombatRandom(_legacyRandom.Next());
        _escapeRandom = new CombatRandom(_legacyRandom.Next());
        _botRandom = new CombatRandom(_legacyRandom.Next());
        _duelRandom = new CombatRandom(_legacyRandom.Next());
    }

    public Guid RoomId { get; }
    public string ConfigVersion { get; }
    public long Revision { get; private set; }

    public IReadOnlyList<CombatFeedbackResolution> DrainCombatFeedback()
    {
        var feedback = _combatFeedback.ToArray();
        _combatFeedback.Clear();
        return feedback;
    }
    public TimeSpan Elapsed { get; private set; }
    public ChaosMapState? Map { get; private set; }

    private Random PlayerSeedRandom => _useLegacyRandom ? _legacyRandom : _playerSeedRandom;
    private Random RewardRandom => _useLegacyRandom ? _legacyRandom : _rewardRandom;
    private Random LootRandom => _useLegacyRandom ? _legacyRandom : _lootRandom;
    private Random EscapeRandom => _useLegacyRandom ? _legacyRandom : _escapeRandom;
    private Random BotRandom => _useLegacyRandom ? _legacyRandom : _botRandom;
    private Random DuelRandom => _useLegacyRandom ? _legacyRandom : _duelRandom;

    public void InitializeMap(ChaosMapState map)
    {
        ArgumentNullException.ThrowIfNull(map);
        if (Map is not null) throw new DomainValidationException("The room map is already initialized.");
        if (_players.Count > map.SpawnPositions.Count) throw new DomainValidationException("The map has too few spawn positions.");
        Map = map;
        foreach (var (player, index) in _players.Values.OrderBy(player => player.PlayerId).Select((player, index) => (player, index)))
        {
            player.Position = map.SpawnPositions[index];
            player.Pve = PveBattleFactory.Create(map.GetCell(player.Position.Value));
            player.Phase = RoomPlayerPhase.Pve;
            StartBotPveSimulation(player);
        }
        Revision++;
    }

    public MapPosition MovePlayer(Guid playerId, MapPosition target, long expectedRevision) =>
        MovePlayerAndPair(playerId, target, expectedRevision, DateTimeOffset.UtcNow).Position;

    public RoomMoveResult MovePlayerAndPair(Guid playerId, MapPosition target, long expectedRevision, DateTimeOffset now)
    {
        if (expectedRevision != Revision)
            throw new DomainValidationException($"Room revision conflict. Expected {expectedRevision}, current {Revision}.");
        if (Map is null) throw new DomainValidationException("The room map is not initialized.");
        var player = GetPlayer(playerId);
        if (player.Phase is not RoomPlayerPhase.ActionBar)
            throw new DomainValidationException("A player can only move from the action bar.");
        if (_springDrinks.ContainsKey(playerId))
            throw new DomainValidationException("A player cannot move while drinking from a spring.");
        if (player.Position is not { } current || !Map.CanMove(current, target))
            throw new DomainValidationException("The target cell is not a legal inward or same-layer move.");
        var targetPve = player.ClearedCells.Contains(target) ? null : PveBattleFactory.Create(Map.GetCell(target));
        if (player.Pve?.IsCleared == true) player.ClearedCells.Add(current);
        player.Position = target;
        player.Pve = targetPve;
        player.Phase = targetPve is null ? RoomPlayerPhase.ActionBar : RoomPlayerPhase.Pve;
        StartBotPveSimulation(player);
        _extractions.Remove(playerId);
        player.Combat.ClearShield();
        Revision++;
        var candidate = _players.Values
            .Where(other => other.PlayerId != playerId && other.Position == target)
            .Where(other => other.Phase is RoomPlayerPhase.Pve or RoomPlayerPhase.ActionBar or RoomPlayerPhase.Choice)
            .OrderBy(other => other.PlayerId)
            .FirstOrDefault(other => CanPairPlayers(playerId, other.PlayerId));
        var duel = candidate is null ? null : StartDuel(candidate.PlayerId, playerId, now).Capture();
        return new RoomMoveResult(target, duel, Revision);
    }

    public ChaosMapProjection GetMapProjection(Guid playerId)
    {
        if (Map is null) throw new DomainValidationException("The room map is not initialized.");
        var player = GetPlayer(playerId);
        if (player.Position is not { } position) throw new DomainValidationException("The player has no map position.");
        var cell = Map.GetCell(position);
        return new ChaosMapProjection(
            Map.Cells.Select(mapCell => new MapCellProjection(mapCell.Position, mapCell.Layer, mapCell.IsBoss, mapCell.HasSpring)).ToArray(),
            position,
            player.Phase is RoomPlayerPhase.ActionBar ? Map.GetNeighbors(position).Where(target => Map.CanMove(position, target)).ToArray() : [],
            new CurrentCellProjection(cell.HasEvacuation || cell.IsBoss, cell.MonsterGroupId, player.ConsumedSprings.Contains(position)));
    }

    public RoomPlayerState AddPlayer(BattleRoomPlayerSetup setup)
    {
        ArgumentNullException.ThrowIfNull(setup);
        if (setup.PlayerId == Guid.Empty || _players.ContainsKey(setup.PlayerId) || _players.Count >= 4)
        {
            throw new DomainValidationException("Room player is invalid, duplicated, or exceeds the four-player limit.");
        }
        if (setup.CardLevels is not null && setup.CardLevels.Count != setup.CardIds.Count)
            throw new DomainValidationException("Card levels must match the deck slots.");
        for (var index = 0; index < setup.CardIds.Count; index++)
        {
            _catalog.Get(setup.CardIds[index], setup.CardLevels?[index] ?? 0);
        }

        var combat = new PlayerCombatState(
            setup.HeroClass,
            setup.CardIds,
            new Random(PlayerSeedRandom.Next()),
            setup.WeaponLevel,
            setup.Equipment,
            setup.CardLevels);
        var player = new RoomPlayerState(setup.PlayerId, setup.HeroClass, combat, setup.Pve, setup.InventoryCapacity, setup.SafeSlots, setup.WornArmor, setup.IsBot, setup.SafeSlotIndexes, setup.DisplayName);
        _players.Add(player.PlayerId, player);
        return player;
    }

    public RoomPlayerState GetPlayer(Guid playerId) =>
        _players.TryGetValue(playerId, out var player)
            ? player
            : throw new DomainValidationException("Player is not in this room.");

    public bool TryEnterActionBar(Guid playerId)
    {
        var player = GetPlayer(playerId);
        if (player.Phase != RoomPlayerPhase.Pve || player.Pve is null || !player.Pve.IsCleared)
            return false;
        player.Pve.RefreshPhase();
        player.Phase = RoomPlayerPhase.ActionBar;
        Revision++;
        return true;
    }

    public RewardChoiceSnapshot GetRewardChoice(Guid playerId) =>
        GetPlayer(playerId).RewardChoice?.Capture()
        ?? throw new DomainValidationException("The player has no pending reward choice.");

    public RewardRefreshReceiptSnapshot RefreshRewardChoice(
        Guid playerId,
        long expectedRevision,
        long accountGoldAvailable = 0,
        string? requestId = null)
    {
        var player = GetPlayer(playerId);
        if (!string.IsNullOrWhiteSpace(requestId))
        {
            var replay = player.RewardRefreshReceipts.SingleOrDefault(receipt => receipt.RequestId == requestId);
            if (replay is not null) return replay;
        }
        if (expectedRevision != Revision)
            throw new DomainValidationException($"Room revision conflict. Expected {expectedRevision}, current {Revision}.");
        var choice = player.RewardChoice ?? throw new DomainValidationException("The player has no pending reward choice.");
        if (player.Phase != RoomPlayerPhase.Choice)
            throw new DomainValidationException("Rewards can only be refreshed during the choice phase.");
        var cost = GameConfigCatalog.Current.RewardRefreshGold(choice.RefreshCount + 1);
        var accountGoldRequired = cost - player.Inventory.GoldQuantity;
        if (accountGoldRequired > accountGoldAvailable)
            throw new DomainValidationException($"Insufficient gold; account gold required: {accountGoldRequired}.");
        player.Inventory.TrySpendGold(Math.Min(cost, player.Inventory.GoldQuantity));
        choice.Refresh(RewardRandom);
        player.RewardRefreshCount = choice.RefreshCount;
        Revision++;
        var receipt = new RewardRefreshReceiptSnapshot(requestId ?? $"legacy:{Revision}", choice.Capture(), Revision);
        player.RewardRefreshReceipts.Add(receipt);
        return receipt;
    }

    public int ClaimReward(Guid playerId, string optionId, string? replaceItemId = null, bool equip = false)
    {
        var player = GetPlayer(playerId);
        if (player.Phase != RoomPlayerPhase.Choice || player.RewardChoice is null)
            throw new DomainValidationException("The player has no pending reward choice.");
        var option = player.RewardChoice.Get(optionId);
        if (equip && option.Kind != RewardChoiceKind.Equipment)
            throw new DomainValidationException("Only an equipment reward can be equipped.");
        if (option.Kind == RewardChoiceKind.ImmediateHeal && replaceItemId is not null)
            throw new DomainValidationException("Healing does not replace inventory items.");
        var applied = option.Kind == RewardChoiceKind.ImmediateHeal
            ? player.Combat.Heal(player.Combat.ResolveRecovery(
                (int)Math.Floor(player.Combat.MaximumHp * option.HealPercent / 100d)))
            : equip ? EquipReward(player, option.Item!, replaceItemId)
            : ClaimItemReward(player, option.Item!, replaceItemId);
        player.RewardChoice = null;
        if (player.Position is { } clearedPosition) player.ClearedCells.Add(clearedPosition);
        player.Phase = RoomPlayerPhase.ActionBar;
        Revision++;
        return applied;
    }

    private static int ClaimItemReward(RoomPlayerState player, ExplorationItem item, string? replaceItemId)
    {
        if (replaceItemId is null && player.Inventory.TryAdd(item)) return item.Quantity;
        if (string.IsNullOrWhiteSpace(replaceItemId))
            throw new DomainValidationException("The inventory is full; an explicit replacement is required.");
        var pending = player.Inventory.BeginChoiceReplacement(replaceItemId, item);
        TrackRecycled(player, player.Inventory.FinalizeChoiceReplacement(pending.Token));
        return item.Quantity;
    }

    public RoomPlayerSnapshot CapturePlayer(Guid playerId) =>
        CapturePlayerState(GetPlayer(playerId));

    public BattleRoomSnapshot Capture() =>
        new(
            RoomId,
            ConfigVersion,
            Revision,
            Elapsed,
            _players.Values.OrderBy(player => player.PlayerId).Select(CapturePlayerState).ToArray(),
            _duels.Values.OrderBy(duel => duel.DuelId).Select(duel => duel.Capture()).ToArray(),
            Map?.Capture(),
            _ceasefires.Select(value => new CeasefireSnapshot(value.FirstPlayerId, value.SecondPlayerId, value.Remaining)).ToArray(),
            _relicPiles.Values.Select(value => value.Capture()).ToArray(),
            _useLegacyRandom ? _legacyRandom.State : null,
            _botDuelRemaining.Select(value => new BotDuelTimerSnapshot(value.Key, value.Value)).ToArray(),
            _useLegacyRandom ? null : new RoomRandomStreamsSnapshot(
                _playerSeedRandom.State,
                _rewardRandom.State,
                _lootRandom.State,
                _escapeRandom.State,
                _botRandom.State,
                _duelRandom.State));

    public static BattleRoom Restore(BattleRoomSnapshot snapshot, CombatCardCatalog catalog, int seed)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        var room = new BattleRoom(snapshot.RoomId, snapshot.ConfigVersion, catalog, seed)
        {
            Revision = snapshot.Revision,
            Elapsed = snapshot.Elapsed
        };
        var legacyConsumedSprings = snapshot.Map?.ConsumedSprings ?? [];
        if (snapshot.Map is { } mapSnapshot) room.Map = ChaosMapState.Restore(mapSnapshot);
        foreach (var playerSnapshot in snapshot.Players)
        {
            var cards = playerSnapshot.Combat.Deck.Hand
                .Concat(playerSnapshot.Combat.Deck.Library)
                .Concat(playerSnapshot.Combat.Deck.Discard)
                .ToArray();
            var inventory = playerSnapshot.Inventory
                ?? throw new InvalidOperationException("A room player snapshot is missing inventory state.");
            var player = room.AddPlayer(new BattleRoomPlayerSetup(
                playerSnapshot.PlayerId,
                playerSnapshot.HeroClass,
                cards.Select(card => card.CardId).ToArray(),
                null,
                playerSnapshot.Combat.WeaponLevel,
                inventory.Capacity,
                inventory.SafeSlots,
                playerSnapshot.WornArmor,
                playerSnapshot.IsBot,
                playerSnapshot.Combat.Equipment,
                SafeSlotIndexes: inventory.SafeSlotIndexes,
                DisplayName: playerSnapshot.DisplayName,
                CardLevels: cards.Select(card => card.Level).ToArray()));
            player.Combat.Restore(playerSnapshot.Combat);
            player.Pve = playerSnapshot.Pve is null ? null : PveBattleState.Rehydrate(playerSnapshot.Pve);
            player.Position = playerSnapshot.Position;
            player.Phase = playerSnapshot.Phase;
            player.CurrentDuelId = playerSnapshot.CurrentDuelId;
            player.RewardChoice = playerSnapshot.RewardChoice is null ? null : RewardChoiceState.Restore(playerSnapshot.RewardChoice);
            player.RewardRefreshCount = playerSnapshot.RewardRefreshCount ?? player.RewardChoice?.RefreshCount ?? 0;
            foreach (var receipt in playerSnapshot.RewardRefreshReceipts ?? [])
            {
                if (string.IsNullOrWhiteSpace(receipt.RequestId) || receipt.RoomRevision < 1 ||
                    player.RewardRefreshReceipts.Any(existing => existing.RequestId == receipt.RequestId))
                    throw new InvalidOperationException("The snapshot contains invalid reward refresh receipts.");
                player.RewardRefreshReceipts.Add(receipt);
            }
            foreach (var clearedCell in playerSnapshot.ClearedCells ?? []) player.ClearedCells.Add(clearedCell);
            foreach (var consumedSpring in playerSnapshot.ConsumedSprings ?? legacyConsumedSprings)
                player.ConsumedSprings.Add(consumedSpring);
            if (player.RewardRefreshCount is < 0 or > 3 ||
                player.RewardChoice is { } restoredChoice && restoredChoice.RefreshCount != player.RewardRefreshCount)
                throw new InvalidOperationException("The snapshot contains inconsistent reward refresh counts.");
            player.Inventory.Apply(ExplorationInventory.Restore(inventory));
            player.RecycledEquipment.AddRange(playerSnapshot.RecycledEquipment ?? []);
            if (playerSnapshot.ExtractionRemaining is { } extraction && extraction > TimeSpan.Zero)
                room._extractions[player.PlayerId] = extraction;
            if (playerSnapshot.DisconnectedRemaining is { } disconnected && disconnected > TimeSpan.Zero)
                room._disconnects[player.PlayerId] = disconnected;
            if (playerSnapshot.SpringDrink is { } springDrink && springDrink.Remaining > TimeSpan.Zero)
            {
                if (player.Phase != RoomPlayerPhase.ActionBar || player.Position != springDrink.Position ||
                    room.Map is null || !room.Map.GetCell(springDrink.Position).HasSpring ||
                    player.ConsumedSprings.Contains(springDrink.Position))
                    throw new InvalidOperationException("The snapshot contains an invalid spring read state.");
                room._springDrinks[player.PlayerId] = springDrink;
            }
            if (player.IsBot && player.Phase == RoomPlayerPhase.Pve && player.Pve?.Phase == PveBattlePhase.Active)
            {
                room._botPveRemaining[player.PlayerId] = playerSnapshot.BotPveRemaining is { } botPve && botPve > TimeSpan.Zero
                    ? botPve
                    : room.BotPveDuration(player);
            }
        }
        foreach (var duel in snapshot.Duels) room._duels.Add(duel.DuelId, DuelState.Restore(duel));
        foreach (var timer in snapshot.BotDuelTimers ?? [])
        {
            if (!room._duels.ContainsKey(timer.DuelId) || timer.Remaining <= TimeSpan.Zero)
                throw new InvalidOperationException("The snapshot contains an invalid bot duel timer.");
            room._botDuelRemaining[timer.DuelId] = timer.Remaining;
        }
        foreach (var ceasefire in snapshot.Ceasefires ?? [])
            room._ceasefires.Add(new Ceasefire(ceasefire.FirstPlayerId, ceasefire.SecondPlayerId, ceasefire.Remaining));
        foreach (var pile in snapshot.RelicPiles ?? []) room._relicPiles.Add(pile.PileId, RelicPile.Restore(pile));
        if (snapshot.RandomStreams is { } streams)
        {
            room._playerSeedRandom.Restore(streams.PlayerSeed);
            room._rewardRandom.Restore(streams.Reward);
            room._lootRandom.Restore(streams.Loot);
            room._escapeRandom.Restore(streams.Escape);
            room._botRandom.Restore(streams.Bot);
            room._duelRandom.Restore(streams.Duel);
        }
        else if (snapshot.RandomState is { } randomState)
        {
            room._legacyRandom.Restore(randomState);
            room._useLegacyRandom = true;
        }
        return room;
    }

    private RoomPlayerSnapshot CapturePlayerState(RoomPlayerState player) =>
        player.Capture(
            _extractions.TryGetValue(player.PlayerId, out var extraction) ? extraction : null,
            _disconnects.TryGetValue(player.PlayerId, out var disconnected) ? disconnected : null,
            _springDrinks.TryGetValue(player.PlayerId, out var springDrink) ? springDrink : null,
            _botPveRemaining.TryGetValue(player.PlayerId, out var botPve) ? botPve : null);

    private void StartBotPveSimulation(RoomPlayerState player)
    {
        _botPveRemaining.Remove(player.PlayerId);
        if (player.IsBot && player.Phase == RoomPlayerPhase.Pve && player.Pve?.Phase == PveBattlePhase.Active)
            _botPveRemaining[player.PlayerId] = BotPveDuration(player);
    }

    private TimeSpan BotPveDuration(RoomPlayerState player)
    {
        if (Map is null || player.Position is not { } position)
            throw new InvalidOperationException("A bot PVE simulation requires an initialized map position.");
        return TimeSpan.FromSeconds(BotRules.PveSimSeconds(ToBotLayer(Map.GetCell(position))));
    }

    private static CellLayer ToBotLayer(ChaosMapCell cell) =>
        cell.IsBoss ? CellLayer.Boss : cell.Layer switch
        {
            ChaosMapLayer.Outer => CellLayer.Outer,
            ChaosMapLayer.Middle => CellLayer.Mid,
            ChaosMapLayer.Core => CellLayer.Elite,
            _ => throw new ArgumentOutOfRangeException(nameof(cell))
        };

    public void MarkPlayerConnected(Guid playerId)
    {
        GetPlayer(playerId);
        _disconnects.Remove(playerId);
    }

    public void MarkPlayerDisconnected(Guid playerId)
    {
        var player = GetPlayer(playerId);
        if (player.IsBot) return;
        if (player.Phase is RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted) return;
        _disconnects[playerId] = TimeSpan.FromSeconds(15);
        Revision++;
    }

    public DuelState StartDuel(Guid firstPlayerId, Guid latePlayerId, DateTimeOffset now)
    {
        if (firstPlayerId == latePlayerId)
        {
            throw new DomainValidationException("A duel requires two distinct players.");
        }
        var first = GetPlayer(firstPlayerId);
        var late = GetPlayer(latePlayerId);
        EnsureDuelEligible(first);
        EnsureDuelEligible(late);
        if (!CanPairPlayers(firstPlayerId, latePlayerId))
            throw new DomainValidationException("The pair is protected by an active ceasefire.");
        var duel = new DuelState(
            Guid.CreateVersion7(),
            firstPlayerId,
            latePlayerId,
            now,
            Freeze(first),
            Freeze(late));
        _duels.Add(duel.DuelId, duel);
        PrepareDuelParticipant(first, duel.DuelId);
        PrepareDuelParticipant(late, duel.DuelId);
        if (first.IsBot && late.IsBot)
            _botDuelRemaining[duel.DuelId] = TimeSpan.FromSeconds(BotRules.BotVsBotSimSeconds());
        Revision++;
        return duel;
    }

    public void EndDuelSurvived(Guid duelId, DuelEndReason reason)
    {
        if (reason == DuelEndReason.Victory)
        {
            throw new DomainValidationException("A victory duel end requires a dead participant.");
        }
        var duel = GetDuel(duelId);
        RestoreParticipant(GetPlayer(duel.FirstPlayerId), duel.FirstFrozen);
        RestoreParticipant(GetPlayer(duel.LatePlayerId), duel.LateFrozen);
        _duels.Remove(duelId);
        _botDuelRemaining.Remove(duelId);
        if (reason is DuelEndReason.MutualLeave or DuelEndReason.Escaped)
            AddCeasefire(duel.FirstPlayerId, duel.LatePlayerId);
        Revision++;
    }

    public bool RequestDuelLeave(Guid duelId, Guid playerId, DateTimeOffset now)
    {
        var duel = GetDuel(duelId);
        var completed = duel.RegisterLeave(playerId, now);
        if (completed)
        {
            EndDuelSurvived(duelId, DuelEndReason.MutualLeave);
        }
        else
        {
            Revision++;
        }
        return completed;
    }

    public bool CanPairPlayers(Guid firstPlayerId, Guid secondPlayerId)
    {
        if (firstPlayerId == secondPlayerId) return false;
        var first = GetPlayer(firstPlayerId);
        var second = GetPlayer(secondPlayerId);
        for (var index = _ceasefires.Count - 1; index >= 0; index--)
        {
            var ceasefire = _ceasefires[index];
            if (!ceasefire.Includes(firstPlayerId, secondPlayerId)) continue;
            var distance = first.Position is { } firstPosition && second.Position is { } secondPosition
                ? firstPosition.ManhattanDistance(secondPosition)
                : 0;
            if (ceasefire.Remaining <= TimeSpan.Zero || distance >= 3)
            {
                _ceasefires.RemoveAt(index);
                return true;
            }
            return false;
        }
        return true;
    }

    public IReadOnlyList<RelicPileSnapshot> GetRelicPilesAt(MapPosition position) =>
        _relicPiles.Values.Where(pile => pile.Position == position).Select(pile => pile.Capture()).ToArray();

    public RelicPileSnapshot GetRelicPile(Guid pileId) =>
        _relicPiles.TryGetValue(pileId, out var pile)
            ? pile.Capture()
            : throw new DomainValidationException("Relic pile is not in this room.");

    public long TakeRelicItem(Guid playerId, Guid pileId, string itemId, long expectedVersion, string? replaceItemId = null)
    {
        var player = GetInventoryPlayer(playerId);
        if (!_relicPiles.TryGetValue(pileId, out var pile))
            throw new DomainValidationException("Relic pile is not in this room.");
        if (player.Position != pile.Position)
            throw new DomainValidationException("The relic pile is not on the player's current cell.");
        var success = pile.TakeToInventory(player.Inventory, itemId, expectedVersion, replaceItemId);
        if (!success) throw new DomainValidationException("The relic item could not be retrieved.");
        if (pile.Items.Count == 0) _relicPiles.Remove(pileId);
        Revision++;
        return pile.Version;
    }

    public long ReplaceRelicItem(Guid playerId, Guid pileId, string itemId, long expectedVersion, string replaceItemId)
    {
        if (string.IsNullOrWhiteSpace(replaceItemId))
            throw new DomainValidationException("A backpack item is required for relic replacement.");
        return TakeRelicItem(playerId, pileId, itemId, expectedVersion, replaceItemId);
    }

    public long SelectPveTarget(Guid playerId, Guid battleId, string targetId, long expectedRevision)
    {
        if (expectedRevision != Revision)
            throw new DomainValidationException($"Room revision conflict. Expected {expectedRevision}, current {Revision}.");
        var player = GetPlayer(playerId);
        if (player.Phase != RoomPlayerPhase.Pve || player.Pve?.BattleId != battleId)
            throw new DomainValidationException("The supplied PVE battle is not active for this player.");
        if (player.Pve.SelectTarget(targetId)) Revision++;
        return Revision;
    }

    public TimeSpan RequestExtraction(Guid playerId)
    {
        var player = GetPlayer(playerId);
        if (Map is null || player.Position is not { } position || !Map.GetCell(position).HasEvacuation && !Map.GetCell(position).IsBoss)
            throw new DomainValidationException("The current cell has no evacuation point.");
        if (player.Phase != RoomPlayerPhase.ActionBar || player.Pve is not null && !player.Pve.IsCleared)
            throw new DomainValidationException("The player must be in the action bar after clearing their PVE.");
        if (_springDrinks.ContainsKey(playerId))
            throw new DomainValidationException("Extraction cannot start while drinking from a spring.");
        _extractions[playerId] = TimeSpan.FromSeconds(3);
        Revision++;
        return _extractions[playerId];
    }

    public TimeSpan RequestSpring(Guid playerId)
    {
        var player = GetPlayer(playerId);
        if (Map is null || player.Position is not { } position || !Map.GetCell(position).HasSpring)
            throw new DomainValidationException("The current cell has no life spring.");
        if (player.Phase != RoomPlayerPhase.ActionBar)
            throw new DomainValidationException("A life spring can only be used from the action bar.");
        if (player.ConsumedSprings.Contains(position))
            throw new DomainValidationException("This player has already used the current life spring.");
        if (_springDrinks.ContainsKey(playerId))
            throw new DomainValidationException("The player is already drinking from a spring.");
        if (_extractions.ContainsKey(playerId))
            throw new DomainValidationException("A life spring cannot be used while extracting.");
        var read = new SpringDrinkSnapshot(position, TimeSpan.FromSeconds(1.2));
        _springDrinks[playerId] = read;
        Revision++;
        return read.Remaining;
    }

    public PotionUseResult UsePotion(Guid playerId)
    {
        var player = GetPlayer(playerId);
        if (player.Phase != RoomPlayerPhase.ActionBar)
            throw new DomainValidationException("A health potion can only be used from the action bar.");
        if (_extractions.ContainsKey(playerId))
            throw new DomainValidationException("A health potion cannot be used while extracting.");
        if (_springDrinks.ContainsKey(playerId))
            throw new DomainValidationException("A health potion cannot be used while drinking from a spring.");
        var potion = player.Inventory.Items.FirstOrDefault(item => item.Kind == ExplorationItemKind.HealthPotion)
            ?? throw new DomainValidationException("The player has no health potion.");
        if (!player.Inventory.TryRemove(potion.ItemId, out _))
            throw new InvalidOperationException("The selected health potion disappeared before it could be consumed.");

        var baseRecovery = (int)Math.Floor(
            player.Combat.MaximumHp * Configuration.GameConfigCatalog.Current.Economy.HealthPotionHealRate);
        var healed = player.Combat.Heal(player.Combat.ResolveRecovery(baseRecovery));
        Revision++;
        return new PotionUseResult(potion.ItemId, healed, Revision);
    }

    public DuelEscapeRequestResult RequestDuelEscape(Guid duelId, Guid playerId)
    {
        var duel = GetDuel(duelId);
        var player = GetPlayer(playerId);
        var opponent = GetPlayer(duel.OpponentOf(playerId));
        var probability = DuelRules.EscapeProbability(
            player.HeroClass, player.Combat.Hp, player.Combat.MaximumHp,
            opponent.Combat.Hp, opponent.Combat.MaximumHp,
            player.Combat.Equipment.ForcedEscapeBonus);
        duel.BeginEscape(playerId, probability, player.Combat.Hp);
        Revision++;
        return new DuelEscapeRequestResult(duelId, probability, Revision);
    }

    public void EndDuelWithDeath(Guid duelId, Guid loserId)
    {
        var duel = GetDuel(duelId);
        var winnerId = duel.OpponentOf(loserId);
        RestoreParticipant(GetPlayer(winnerId), duel.FrozenFor(winnerId));
        var loser = GetPlayer(loserId);
        loser.Combat.MarkDead();
        loser.Pve = null;
        loser.CurrentDuelId = null;
        loser.Phase = RoomPlayerPhase.Dead;
        _duels.Remove(duelId);
        _botDuelRemaining.Remove(duelId);
        if (!loser.IsBot) CreateDeathRelicPile(loser);
        Revision++;
    }

    public CombatResolution PlayCards(
        Guid playerId,
        Guid battleId,
        string targetId,
        IReadOnlyList<Guid> cardInstanceIds,
        long expectedRevision,
        DateTimeOffset now)
    {
        if (expectedRevision != Revision)
        {
            throw new DomainValidationException($"Room revision conflict. Expected {expectedRevision}, current {Revision}.");
        }
        var attacker = GetPlayer(playerId);
        DuelState? duel = null;
        RoomPlayerState? pvpTarget = null;
        MonsterCombatState? pveTarget = null;
        if (attacker.Phase == RoomPlayerPhase.Pvp)
        {
            duel = GetDuel(battleId);
            if (duel.LatePlayerId == playerId && now < duel.LatePlayerUnlockAt)
            {
                throw new DomainValidationException("The late joiner is still locked.");
            }
            var opponentId = duel.OpponentOf(playerId);
            if (!Guid.TryParse(targetId, out var parsedTarget) || parsedTarget != opponentId)
            {
                throw new DomainValidationException("PVP target does not match the current opponent.");
            }
            pvpTarget = GetPlayer(opponentId);
            if (_disconnects.ContainsKey(playerId) || _disconnects.ContainsKey(opponentId))
                throw new DomainValidationException("Both duel participants must be connected.");
        }
        else if (attacker.Phase == RoomPlayerPhase.Pve && attacker.Pve?.BattleId == battleId)
        {
            pveTarget = attacker.Pve.GetTarget(targetId);
            if (pveTarget.IsDead) throw new DomainValidationException("A defeated monster cannot be attacked again.");
        }
        else
        {
            throw new DomainValidationException("The supplied battle is not active for this player.");
        }

        if (attacker.Combat.StunRemaining > TimeSpan.Zero)
        {
            throw new DomainValidationException("A stunned player cannot play cards.");
        }
        var selected = attacker.Combat.Deck.SelectFromHand(cardInstanceIds);
        var definitions = selected.Select(card => _catalog.Get(card.CardId, card.Level, card.ElementOverride)).ToArray();
        var draft = CombatResolver.Resolve(
            definitions,
            attacker.Combat,
            pvpTarget is not null ? pvpTarget.Combat.ElementalResistance : pveTarget!.ElementalResistance);
        var stun = attacker.Combat.ResolveTargetStun($"{battleId:D}:{targetId}", draft.Stun);
        var blockSpeed = attacker.Combat.ResolveControl(TimeSpan.FromSeconds(definitions.Max(card => card.Effect.DrawBlockSeconds) / 2));
        var healthBeforeCost = attacker.Combat.Hp;
        attacker.Combat.PayHealthCost(draft.HealthCost);
        var healthCost = healthBeforeCost - attacker.Combat.Hp;
        var heal = attacker.Combat.Heal(draft.Heal);
        var shieldGain = attacker.Combat.GainShield(draft.Shield);
        attacker.Combat.Deck.DiscardPlayed(selected);
        attacker.Combat.AddDrawCharge(draft.DrawCharge);
        attacker.Combat.DrawImmediate(draft.ImmediateDraw);
        attacker.Combat.ApplyDrawSpeed(draft.DrawSpeedDuration, draft.DrawSpeedModifier);
        var fenxian = attacker.Combat.UpdateFenxian(draft.CoreElement, draft.CoreCount);
        attacker.Combat.AddDrawCharge(fenxian.Charge);
        attacker.Combat.DrawImmediate(fenxian.Draw);
        if (pveTarget is not null)
            attacker.Combat.ApplyDrawBlockSpeed(blockSpeed);

        int shieldDamage;
        int hpDamage;
        bool defeated;
        bool battleEnded;
        var resolvedDamage = draft.Damage;
        if (duel is not null)
        {
            var target = pvpTarget!;
            resolvedDamage = target.Combat.ResolveIncomingDamage(draft.Damage);
            (shieldDamage, hpDamage) = target.Combat.TakeDamage(resolvedDamage);
            target.Combat.ApplyStun(stun);
            target.Combat.ApplyDrawBlock(draft.DrawBlock);
            defeated = target.Combat.IsDead;
            battleEnded = defeated;
            if (defeated)
            {
                EndDuelWithDeath(duel.DuelId, target.PlayerId);
            }
            else
            {
                Revision++;
            }
        }
        else
        {
            var target = pveTarget!;
            (shieldDamage, hpDamage) = target.TakeDamage(draft.Damage);
            target.ApplyStun(stun);
            defeated = target.IsDead;
            if (defeated) AddMonsterCard(attacker, target);
            var pve = attacker.Pve!;
            pve.RefreshPhase();
            battleEnded = pve.IsCleared;
            if (battleEnded) OpenRewardChoice(attacker);
            if (!battleEnded) Revision++;
        }

        var resolution = new CombatResolution(
            battleId,
            playerId,
            targetId,
            resolvedDamage,
            shieldDamage,
            hpDamage,
            heal,
            shieldGain,
            defeated,
            battleEnded,
            Revision,
            CombatResolver.ResolveDamageSegments(draft.DamageSegments ?? [], shieldDamage + hpDamage,
                pvpTarget?.HeroClass == HeroClass.Guardian ? 1 - pvpTarget.Combat.Equipment.BulwarkDamageReduction : 1),
            draft.CoreElement, draft.CoreCount, stun.TotalSeconds,
            pvpTarget is not null ? draft.DrawBlock.TotalSeconds : 0, healthCost,
            draft.DrawCharge + fenxian.Charge, draft.ImmediateDraw + fenxian.Draw,
            draft.DrawSpeedDuration.TotalSeconds, draft.DrawSpeedModifier,
            pveTarget is not null ? blockSpeed.TotalSeconds : 0,
            draft.ResonanceMultiplier, draft.ConflictPairCount, draft.ConflictCancellation);
        _combatFeedback.Add(new CombatFeedbackResolution(playerId.ToString("D"), resolution));
        return resolution;
    }

    private void AddMonsterCard(RoomPlayerState player, MonsterCombatState monster)
    {
        var monsterId = monster.MonsterId;
        var speciesId = monsterId.EndsWith("-a", StringComparison.Ordinal) || monsterId.EndsWith("-b", StringComparison.Ordinal)
            ? monsterId[..^2] : monsterId;
        var monsterType = speciesId switch
        {
            "fire-bat" => "FireBat", "thorn-mite" => "ThornMite", "murk-snail" => "MudHydra",
            "sand-lizard" => "SandLizard", "rust-rat" => "RustRat", "box-spirit" => "BoxSpirit",
            "metal-guard" => "GoldGuard", "fire-herald" => "FireReaver", "marsh-mother" => "SwampMother",
            "stone-guard" => "StoneGuard", "thorn-guard" => "ThornGuard", "annihilation-core" => "VoidCore",
            _ => null
        };
        var card = monsterType is null ? null : GameConfigCatalog.Current.Cards.FirstOrDefault(value => value.MonsterType == monsterType);
        if (card is not null && _catalog.Contains(card.CardId))
            player.Combat.Deck.AddToDiscard(new CombatCardInstance(Guid.CreateVersion7(), card.CardId,
                ElementOverride: monsterType == "BoxSpirit" ? monster.Intents[0].Element : null));
    }

    private void OpenRewardChoice(RoomPlayerState player)
    {
        if (player.Position is not { } position || Map is null)
            throw new DomainValidationException("A cleared PVE battle must have a map position.");
        AddPveVictoryDrops(player, Map.GetCell(position));
        player.Pve!.RefreshPhase();
        var cell = Map.GetCell(position);
        player.RewardChoice = RewardChoiceState.Create(cell.Layer, RewardRandom, cell.IsBoss, player.RewardRefreshCount,
            isTreasure: cell.MonsterGroupId == "BOX");
        player.Phase = RoomPlayerPhase.Choice;
        Revision++;
    }

    private void AddPveVictoryDrops(RoomPlayerState player, ChaosMapCell cell)
    {
        var isBoss = cell.IsBoss || string.Equals(cell.MonsterGroupId, "BOSS", StringComparison.Ordinal);
        var loot = GameConfigCatalog.Current.LootLayer(cell.Layer, isBoss);
        var gold = loot.Gold;
        var warriorSoul = LootRandom.Next(loot.WarriorSoulMin, checked(loot.WarriorSoulMax + 1));
        var classSoul = loot.ClassSoul;
        var fragments = LootRandom.Next(loot.FragmentMin, checked(loot.FragmentMax + 1));

        // These are non-choice drops. If a new stack cannot be created, the drop is intentionally recycled.
        player.Inventory.TryAdd(new ExplorationItem("gold", ExplorationItemKind.Gold, gold));
        player.Inventory.TryAdd(new ExplorationItem("warrior_soul", ExplorationItemKind.WarriorSoul, warriorSoul));
        player.Inventory.TryAdd(new ExplorationItem($"class_soul:{player.HeroClass}", ExplorationItemKind.ClassSoul, classSoul));
        player.Inventory.TryAdd(new ExplorationItem("equipment_fragments", ExplorationItemKind.EquipmentFragments, fragments));
    }

    public void Advance(TimeSpan delta, DateTimeOffset? now = null)
    {
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(delta, TimeSpan.Zero);
        var tickNow = now ?? DateTimeOffset.UtcNow;
        var firstTickFeedback = _combatFeedback.Count;
        Elapsed += delta;
        var disconnectedPlayers = new List<Guid>();
        foreach (var playerId in _disconnects.Keys.ToArray())
        {
            var remaining = _disconnects[playerId] - delta;
            if (remaining > TimeSpan.Zero) _disconnects[playerId] = remaining;
            else
            {
                _disconnects.Remove(playerId);
                disconnectedPlayers.Add(playerId);
            }
        }
        foreach (var playerId in disconnectedPlayers)
        {
            var player = GetPlayer(playerId);
            if (player.Phase is RoomPlayerPhase.Pvp && player.CurrentDuelId is { } duelId && _duels.ContainsKey(duelId))
                EndDuelWithDeath(duelId, playerId);
            else if (player.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted))
            {
                player.Combat.MarkDead();
                player.Pve?.MarkDead();
                player.Pve = null;
                player.Phase = RoomPlayerPhase.Dead;
                CreateDeathRelicPile(player);
                Revision++;
            }
        }
        for (var index = _ceasefires.Count - 1; index >= 0; index--)
        {
            var ceasefire = _ceasefires[index];
            var remaining = ceasefire.Remaining - delta;
            if (remaining <= TimeSpan.Zero) _ceasefires.RemoveAt(index);
            else _ceasefires[index] = ceasefire with { Remaining = remaining };
        }
        var escapedDuels = new List<Guid>();
        foreach (var duel in _duels.Values)
        {
            var first = GetPlayer(duel.FirstPlayerId);
            var late = GetPlayer(duel.LatePlayerId);
            if (duel.TickEscape(delta, first.Combat, late.Combat, EscapeRandom) == EscapeTickResult.Succeeded)
                escapedDuels.Add(duel.DuelId);
        }
        foreach (var duelId in escapedDuels)
            EndDuelSurvived(duelId, DuelEndReason.Escaped);
        foreach (var playerId in _extractions.Keys.ToArray())
        {
            var remaining = _extractions[playerId] - delta;
            if (remaining > TimeSpan.Zero)
            {
                _extractions[playerId] = remaining;
                continue;
            }
            _extractions.Remove(playerId);
            var player = GetPlayer(playerId);
            if (player.Phase == RoomPlayerPhase.ActionBar)
            {
                player.Phase = RoomPlayerPhase.Extracted;
                player.Pve = null;
            }
        }
        foreach (var playerId in _springDrinks.Keys.ToArray())
        {
            var read = _springDrinks[playerId];
            var remaining = read.Remaining - delta;
            if (remaining > TimeSpan.Zero)
            {
                _springDrinks[playerId] = read with { Remaining = remaining };
                continue;
            }
            _springDrinks.Remove(playerId);
            var player = GetPlayer(playerId);
            if (player.Phase != RoomPlayerPhase.ActionBar || player.Position != read.Position ||
                Map is null || !Map.GetCell(read.Position).HasSpring ||
                !player.ConsumedSprings.Add(read.Position))
                continue;
            var percent = Map.GetCell(read.Position).Layer switch
            {
                ChaosMapLayer.Outer => 18,
                ChaosMapLayer.Middle => 25,
                ChaosMapLayer.Core => 35,
                _ => throw new InvalidOperationException("The life spring has an unsupported map layer.")
            };
            player.Combat.Heal(player.Combat.ResolveRecovery(
                (int)Math.Floor(player.Combat.MaximumHp * percent / 100d)));
        }
        if (TerminateBotsWhenNoRealPlayersRemain())
        {
            Revision++;
            return;
        }
        foreach (var player in _players.Values)
        {
            if (player.Phase == RoomPlayerPhase.Dead)
            {
                continue;
            }
            if (player.IsBot && AdvanceBot(player, delta, tickNow))
            {
                continue;
            }
            var duelPaused = player.Phase == RoomPlayerPhase.Pvp &&
                player.CurrentDuelId is { } currentDuelId &&
                _duels.TryGetValue(currentDuelId, out var currentDuel) &&
                (_disconnects.ContainsKey(currentDuel.FirstPlayerId) || _disconnects.ContainsKey(currentDuel.LatePlayerId));
            if (!duelPaused)
                player.Combat.Advance(delta, player.Phase is RoomPlayerPhase.Pve or RoomPlayerPhase.Pvp);
            if (player.Phase != RoomPlayerPhase.Pve || player.Pve?.Phase != PveBattlePhase.Active)
            {
                continue;
            }

            foreach (var monster in player.Pve.Monsters.Where(monster => !monster.IsDead))
            {
                var intent = monster.Advance(delta);
                if (intent is null)
                {
                    continue;
                }
                if (intent.Kind is MonsterIntentKind.Attack or MonsterIntentKind.Direct)
                {
                    var damage = monster.ResolveIntentDamage(
                        intent,
                        player.Combat.ElementalResistance(intent.Element));
                    var resolvedDamage = player.Combat.ResolveIncomingDamage(damage);
                    var (shieldDamage, hpDamage) = player.Combat.TakeDamage(resolvedDamage);
                    var kind = intent.Kind == MonsterIntentKind.Direct || intent.Element == CardElement.None
                        ? "Direct" : intent.Element.ToString();
                    _combatFeedback.Add(new CombatFeedbackResolution(monster.MonsterId, new CombatResolution(
                        player.Pve.BattleId, Guid.Empty, player.PlayerId.ToString("D"), resolvedDamage,
                        shieldDamage, hpDamage, 0, 0, player.Combat.IsDead, player.Combat.IsDead, Revision,
                        shieldDamage + hpDamage > 0 ? [new(kind, shieldDamage + hpDamage)] : [])));
                    if (player.Combat.IsDead)
                    {
                        player.Phase = RoomPlayerPhase.Dead;
                        player.Pve.MarkDead();
                        CreateDeathRelicPile(player);
                        break;
                    }
                }
                else
                {
                    monster.ResolveUtilityIntent(intent);
                }
            }
        }
        TerminateBotsWhenNoRealPlayersRemain();
        Revision++;
        for (var index = firstTickFeedback; index < _combatFeedback.Count; index++)
            _combatFeedback[index] = _combatFeedback[index] with
            {
                Resolution = _combatFeedback[index].Resolution with { RoomRevision = Revision }
            };
    }

    private bool TerminateBotsWhenNoRealPlayersRemain()
    {
        var realPlayers = _players.Values.Where(player => !player.IsBot).ToArray();
        if (realPlayers.Length == 0 || realPlayers.Any(player =>
                player.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted)))
            return false;

        _duels.Clear();
        _botDuelRemaining.Clear();
        var changed = false;
        foreach (var bot in _players.Values.Where(player => player.IsBot &&
                     player.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted)))
        {
            _extractions.Remove(bot.PlayerId);
            _disconnects.Remove(bot.PlayerId);
            _springDrinks.Remove(bot.PlayerId);
            _botPveRemaining.Remove(bot.PlayerId);
            bot.CurrentDuelId = null;
            bot.Pve = null;
            bot.RewardChoice = null;
            bot.Phase = RoomPlayerPhase.Extracted;
            changed = true;
        }
        return changed;
    }

    private bool AdvanceBot(RoomPlayerState player, TimeSpan delta, DateTimeOffset now)
    {
        if (player.Phase == RoomPlayerPhase.Choice && player.RewardChoice is { } choice)
        {
            var bagFull = player.Inventory.FreeSlots == 0;
            var hasFragmentStack = player.Inventory.Items.Any(item =>
                item.Kind == ExplorationItemKind.EquipmentFragments);
            var slot = BotRules.PickChoice(
                player.Combat.Hp,
                player.Combat.MaximumHp,
                bagFull,
                hasFragmentStack);
            var kind = slot switch
            {
                ChoiceSlot.Gear => RewardChoiceKind.Equipment,
                ChoiceSlot.Fragments => RewardChoiceKind.EquipmentFragments,
                ChoiceSlot.Heal => RewardChoiceKind.ImmediateHeal,
                _ => throw new InvalidOperationException("The bot selected an unsupported reward slot.")
            };
            ClaimReward(player.PlayerId, choice.Options.Single(option => option.Kind == kind).OptionId);
            return true;
        }

        if (player.Phase != RoomPlayerPhase.Pve || player.Pve?.Phase != PveBattlePhase.Active)
            return player.Phase switch
            {
                RoomPlayerPhase.Pvp => AdvanceBotDuel(player, delta, now),
                RoomPlayerPhase.ActionBar => AdvanceBotActionBar(player, now),
                _ => false
            };

        var remaining = _botPveRemaining.GetValueOrDefault(player.PlayerId, BotPveDuration(player)) - delta;
        if (remaining > TimeSpan.Zero)
        {
            _botPveRemaining[player.PlayerId] = remaining;
            return true;
        }

        _botPveRemaining.Remove(player.PlayerId);
        if (Map is null || player.Position is not { } position)
            throw new InvalidOperationException("A bot PVE simulation requires an initialized map position.");
        var layer = ToBotLayer(Map.GetCell(position));
        var targetHp = BotRules.ApplyHpLoss(
            player.Combat.Hp,
            player.Combat.MaximumHp,
            BotRules.PveHpLossPercent(layer));
        player.Combat.PayHealthCost(player.Combat.Hp - targetHp);
        foreach (var monster in player.Pve.Monsters.Where(monster => !monster.IsDead))
        {
            monster.TakeDamage(int.MaxValue);
            AddMonsterCard(player, monster);
        }
        OpenRewardChoice(player);
        return true;
    }

    private bool AdvanceBotDuel(RoomPlayerState player, TimeSpan delta, DateTimeOffset now)
    {
        if (player.CurrentDuelId is not { } duelId || !_duels.TryGetValue(duelId, out var duel))
            return true;
        var opponent = GetPlayer(duel.OpponentOf(player.PlayerId));
        if (opponent.IsBot)
        {
            if (player.PlayerId != duel.FirstPlayerId) return true;
            var remaining = _botDuelRemaining.GetValueOrDefault(
                duelId,
                TimeSpan.FromSeconds(BotRules.BotVsBotSimSeconds())) - delta;
            if (remaining > TimeSpan.Zero)
            {
                _botDuelRemaining[duelId] = remaining;
                return true;
            }

            var first = GetPlayer(duel.FirstPlayerId);
            var late = GetPlayer(duel.LatePlayerId);
            var resolved = BotRules.ResolveBotVersusBot(
                first.Combat.Hp,
                first.Combat.MaximumHp,
                late.Combat.Hp,
                late.Combat.MaximumHp);
            EndBotDuel(duelId);
            first.Combat.PayHealthCost(first.Combat.Hp - resolved.LeftHp);
            late.Combat.PayHealthCost(late.Combat.Hp - resolved.RightHp);
            return true;
        }

        if (duel.LatePlayerId == player.PlayerId && now < duel.LatePlayerUnlockAt) return true;
        if (_disconnects.ContainsKey(player.PlayerId) || _disconnects.ContainsKey(opponent.PlayerId)) return true;
        if (player.Combat.StunRemaining > TimeSpan.Zero) return true;
        var hand = player.Combat.Deck.Hand;
        var choices = BotRules.SelectDuelCards(
            hand.Select(card => ToBotCard(_catalog.Get(card.CardId, card.Level, card.ElementOverride))).ToArray(),
            BotRules.HpPercent(player.Combat.Hp, player.Combat.MaximumHp));
        if (choices.Length == 0) return true;
        PlayCards(
            player.PlayerId,
            duelId,
            opponent.PlayerId.ToString("D"),
            choices.Select(index => hand[index].InstanceId).ToArray(),
            Revision,
            now);
        return true;
    }

    private bool AdvanceBotActionBar(RoomPlayerState player, DateTimeOffset now)
    {
        if (Map is null || player.Position is not { } position) return true;
        if (_extractions.ContainsKey(player.PlayerId) || _springDrinks.ContainsKey(player.PlayerId)) return true;
        var cell = Map.GetCell(position);
        var decision = BotDirector.Decide(
            new BotWorld(
                BotPhase.ActionBar,
                new GridCell(position.Row, position.Column),
                ToBotLayer(cell),
                player.Combat.Hp,
                player.Combat.MaximumHp,
                player.Inventory.FreeSlots == 0,
                player.Inventory.Items.Any(item => item.Kind == ExplorationItemKind.EquipmentFragments),
                cell.HasSpring && !player.ConsumedSprings.Contains(position),
                HasPotion: player.Inventory.Items.Any(item => item.Kind == ExplorationItemKind.HealthPotion),
                cell.HasEvacuation || cell.IsBoss,
                PveCleared: player.Pve is null || player.Pve.IsCleared,
                (int)Elapsed.TotalSeconds,
                0,
                0,
                Map.GetNeighbors(position)
                    .Where(next => Map.CanMove(position, next))
                    .Select(next => new GridCell(next.Row, next.Column))
                    .ToArray(),
                []),
            BotRandom);
        switch (decision.Kind)
        {
            case BotActionKind.StartHeal when decision.UseSpring:
                RequestSpring(player.PlayerId);
                break;
            case BotActionKind.StartHeal:
                UsePotion(player.PlayerId);
                break;
            case BotActionKind.StartExtract:
                RequestExtraction(player.PlayerId);
                break;
            case BotActionKind.Move when decision.MoveTo is { } target:
                MovePlayerAndPair(
                    player.PlayerId,
                    new MapPosition(target.Row, target.Col),
                    Revision,
                    now);
                break;
        }
        return true;
    }

    private void EndBotDuel(Guid duelId)
    {
        var duel = GetDuel(duelId);
        RestoreParticipant(GetPlayer(duel.FirstPlayerId), duel.FirstFrozen);
        RestoreParticipant(GetPlayer(duel.LatePlayerId), duel.LateFrozen);
        _duels.Remove(duelId);
        _botDuelRemaining.Remove(duelId);
        Revision++;
    }

    private static BotCard ToBotCard(CombatCardDefinition definition)
    {
        var effect = definition.Effect;
        return new BotCard(
            effect.Element.ToString().ToLowerInvariant(),
            effect.ElementalDamage > 0 || effect.DirectDamage > 0,
            effect.Heal > 0,
            effect.StunSeconds > 0,
            Math.Max(Math.Max(effect.ElementalDamage, effect.DirectDamage), effect.Heal));
    }

    private DuelState GetDuel(Guid duelId) =>
        _duels.TryGetValue(duelId, out var duel)
            ? duel
            : throw new DomainValidationException("Duel is not active in this room.");

    private static void EnsureDuelEligible(RoomPlayerState player)
    {
        if (player.Phase is RoomPlayerPhase.Pvp or RoomPlayerPhase.Dead)
        {
            throw new DomainValidationException("Player is not eligible to enter another duel.");
        }
    }

    private static FrozenParticipantState Freeze(RoomPlayerState player) =>
        new(player.Phase, player.Combat.Capture(), player.Pve?.Capture());

    private void AddCeasefire(Guid firstPlayerId, Guid secondPlayerId)
    {
        _ceasefires.RemoveAll(value => value.Includes(firstPlayerId, secondPlayerId));
        _ceasefires.Add(new Ceasefire(firstPlayerId, secondPlayerId, TimeSpan.FromSeconds(45)));
    }

    private void CreateDeathRelicPile(RoomPlayerState player)
    {
        if (_relicPiles.Values.Any(pile => pile.VictimId == player.PlayerId.ToString("D"))) return;
        if (player.Position is not { } position) return;
        var pile = new RelicPile(Guid.CreateVersion7(), player.PlayerId.ToString("D"), position, player.DisplayName);
        foreach (var item in player.Inventory.Items.Where(item => !item.IsSafe).ToArray())
        {
            pile.Add(item with { IsSafe = false });
            player.Inventory.TryRemove(item.ItemId, out _);
        }
        foreach (var armor in player.WornArmor) pile.Add(armor);
        player.WornArmor = [];
        _relicPiles.Add(pile.PileId, pile);
    }

    private void PrepareDuelParticipant(RoomPlayerState player, Guid duelId)
    {
        _extractions.Remove(player.PlayerId);
        _springDrinks.Remove(player.PlayerId);
        player.Pve?.Freeze();
        player.Combat.PrepareForDuel(new Random(DuelRandom.Next()));
        player.Phase = RoomPlayerPhase.Pvp;
        player.CurrentDuelId = duelId;
    }

    private static void RestoreParticipant(RoomPlayerState player, FrozenParticipantState frozen)
    {
        player.Combat.Restore(frozen.Combat);
        player.Pve = frozen.Pve is null ? null : PveBattleState.Rehydrate(frozen.Pve);
        player.Phase = frozen.Phase;
        player.CurrentDuelId = null;
    }
}
