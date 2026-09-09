using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class BattleRoomSnapshotTests
{
    [Fact]
    public void Restoring_online_players_does_not_create_expired_disconnect_timers()
    {
        var first = Guid.NewGuid();
        var second = Guid.NewGuid();
        var room = CreateRoom(first, second);
        var snapshot = room.Capture();
        Assert.All(snapshot.Players, p =>
        {
            Assert.Null(p.DisconnectedRemaining);
            Assert.Null(p.ExtractionRemaining);
        });
        var restored = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), 77);
        restored.Advance(TimeSpan.FromMilliseconds(100));
        Assert.All(restored.Capture().Players, p => Assert.Equal(RoomPlayerPhase.Pve, p.Phase));
    }

    [Fact]
    public void Legacy_zero_timer_snapshot_does_not_kill_or_extract_idle_player()
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 77);
        var id = Guid.NewGuid();
        room.AddPlayer(new(id, HeroClass.Mage,
            Enumerable.Range(1, 20).Select(i => $"common-{i:D2}").ToArray(), null));
        var snapshot = room.Capture();
        snapshot = snapshot with { Players = snapshot.Players.Select(p => p with
        {
            ExtractionRemaining = TimeSpan.Zero,
            DisconnectedRemaining = TimeSpan.Zero
        }).ToArray() };
        var restored = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), 77);
        restored.Advance(TimeSpan.FromMilliseconds(100));
        Assert.Equal(RoomPlayerPhase.ActionBar, restored.GetPlayer(id).Phase);
    }

    [Fact]
    public void Restored_disconnect_expires_only_after_saved_remaining_duration()
    {
        var first = Guid.NewGuid();
        var second = Guid.NewGuid();
        var room = CreateRoom(first, second);
        room.MarkPlayerDisconnected(first);
        var restored = BattleRoom.Restore(room.Capture(), CombatCardCatalog.CreatePrototype(), 77);
        restored.Advance(TimeSpan.FromSeconds(14));
        Assert.NotEqual(RoomPlayerPhase.Dead, restored.GetPlayer(first).Phase);
        restored.Advance(TimeSpan.FromSeconds(1));
        Assert.Equal(RoomPlayerPhase.Dead, restored.GetPlayer(first).Phase);
        Assert.NotEqual(RoomPlayerPhase.Dead, restored.GetPlayer(second).Phase);
    }

    [Fact]
    public void Initializing_map_assigns_distinct_outer_spawns_and_starts_independent_pve()
    {
        var firstId = Guid.NewGuid();
        var secondId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), 77);
        room.AddPlayer(new BattleRoomPlayerSetup(firstId, HeroClass.Mage, Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));
        room.AddPlayer(new BattleRoomPlayerSetup(secondId, HeroClass.Priest, Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));

        room.InitializeMap(ChaosMapGenerator.Generate(77, 2));

        Assert.NotNull(room.GetPlayer(firstId).Pve);
        Assert.NotNull(room.GetPlayer(secondId).Pve);
        Assert.NotEqual(room.GetPlayer(firstId).Position, room.GetPlayer(secondId).Position);
        Assert.All(room.Capture().Players, player => Assert.Equal(RoomPlayerPhase.Pve, player.Phase));
    }

    [Fact]
    public void Surviving_duel_restores_complete_player_and_pve_snapshots()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = CreateRoom(firstId, lateId);
        var first = room.GetPlayer(firstId);
        first.Combat.TakeDamage(11);
        first.Combat.GainShield(7);
        first.Combat.SetFenxian(CardElement.Fire, 2);
        first.Combat.AddDrawCharge(0.45);
        first.Combat.ApplyDrawSpeed(TimeSpan.FromSeconds(6), -0.25);
        first.Combat.ApplyStun(TimeSpan.FromSeconds(1.4));
        first.Combat.ApplyDrawBlock(TimeSpan.FromSeconds(2.8));
        first.Combat.SetTargetStunWindow("monster-1", TimeSpan.FromSeconds(4.2), 2);

        var monster = Assert.Single(first.Pve!.Monsters);
        monster.TakeDamage(13);
        monster.GainShield(3);
        monster.SetRuntimeState(
            intentIndex: 1,
            intervalProgress: TimeSpan.FromSeconds(1.3),
            windupRemaining: TimeSpan.FromSeconds(0.4),
            isCharging: true,
            empowerBonus: 2,
            stunRemaining: TimeSpan.FromSeconds(0.7),
            statusRemaining: new Dictionary<string, TimeSpan>
            {
                ["burn"] = TimeSpan.FromSeconds(3.1)
            });

        var before = room.CapturePlayer(firstId);
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UnixEpoch);

        Assert.Equal(PveBattlePhase.Frozen, first.Pve.Phase);
        Assert.Equal(3, first.Combat.Deck.Hand.Count);
        Assert.Equal(0, first.Combat.Deck.DrawCharge);
        Assert.Equal(0, first.Combat.FenxianCombo);

        first.Combat.TakeDamage(19);
        first.Combat.ApplyStun(TimeSpan.FromSeconds(9));
        room.Advance(TimeSpan.FromSeconds(2));
        for (var cycle = 0; cycle < 5; cycle++)
        {
            var played = first.Combat.Deck.SelectFromHand(
                first.Combat.Deck.Hand.Select(card => card.InstanceId).ToArray());
            first.Combat.Deck.DiscardPlayed(played);
            first.Combat.DrawImmediate(CombatDeck.HandLimit);
        }
        room.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave);

        var after = room.CapturePlayer(firstId);
        Assert.Equivalent(before, after, strict: true);
    }

    [Fact]
    public void Room_snapshot_round_trips_active_duel_state_and_room_rng()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = CreateRoom(firstId, lateId);
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UnixEpoch);
        room.RequestDuelEscape(duel.DuelId, firstId);
        room.MarkPlayerDisconnected(lateId);
        var snapshot = room.Capture();

        var restored = BattleRoom.Restore(snapshot, catalog, seed: 9173);

        Assert.Equivalent(snapshot, restored.Capture(), strict: true);
    }

    [Fact]
    public void Lethal_duel_restores_winner_but_never_restores_dead_player()
    {
        var winnerId = Guid.NewGuid();
        var loserId = Guid.NewGuid();
        var room = CreateRoom(winnerId, loserId);
        room.GetPlayer(winnerId).Combat.TakeDamage(8);
        var winnerBefore = room.CapturePlayer(winnerId);
        var duel = room.StartDuel(winnerId, loserId, DateTimeOffset.UnixEpoch);

        room.EndDuelWithDeath(duel.DuelId, loserId);

        Assert.Equivalent(winnerBefore, room.CapturePlayer(winnerId), strict: true);
        var loser = room.GetPlayer(loserId);
        Assert.Equal(RoomPlayerPhase.Dead, loser.Phase);
        Assert.Equal(0, loser.Combat.Hp);
        Assert.Null(loser.Pve);
    }

    [Fact]
    public void Death_creates_a_relic_pile_from_unsafe_backpack_items_and_worn_armor()
    {
        var loserId = Guid.NewGuid();
        var winnerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), 77);
        room.AddPlayer(new BattleRoomPlayerSetup(
            loserId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            CreatePve(),
            WornArmor: [new ExplorationItem("armor-1", ExplorationItemKind.Equipment)]));
        room.AddPlayer(new BattleRoomPlayerSetup(
            winnerId,
            HeroClass.Guardian,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            CreatePve()));
        room.InitializeMap(ChaosMapGenerator.Generate(77, 2));

        var loser = room.GetPlayer(loserId);
        loser.Inventory.TryAdd(new ExplorationItem("safe-gold", ExplorationItemKind.Gold, 10, IsSafe: true));
        loser.Inventory.TryAdd(new ExplorationItem("unsafe-potion", ExplorationItemKind.HealthPotion));
        var duel = room.StartDuel(loserId, winnerId, DateTimeOffset.UnixEpoch);

        room.EndDuelWithDeath(duel.DuelId, loserId);

        var pile = Assert.Single(room.GetRelicPilesAt(loser.Position!.Value));
        Assert.Contains(pile.Items, item => item.ItemId == "unsafe-potion");
        Assert.Contains(pile.Items, item => item.ItemId == "armor-1");
        Assert.DoesNotContain(pile.Items, item => item.ItemId == "safe-gold");
        Assert.Contains(loser.Inventory.Items, item => item.ItemId == "safe-gold");
    }

    [Fact]
    public void Entering_an_occupied_cell_starts_a_duel_automatically()
    {
        var firstId = Guid.NewGuid();
        var secondId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), 77);
        room.AddPlayer(new BattleRoomPlayerSetup(firstId, HeroClass.Mage, Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));
        room.AddPlayer(new BattleRoomPlayerSetup(secondId, HeroClass.Priest, Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(77, 2));
        var first = room.GetPlayer(firstId);
        var second = room.GetPlayer(secondId);
        foreach (var monster in first.Pve!.Monsters) monster.TakeDamage(10_000);
        foreach (var monster in second.Pve!.Monsters) monster.TakeDamage(10_000);
        Assert.True(room.TryEnterActionBar(firstId));
        Assert.True(room.TryEnterActionBar(secondId));

        var map = room.Map!;
        var firstPath = FindPath(map, first.Position!.Value, second.Position!.Value);
        var movingId = firstPath.Count > 0 ? firstId : secondId;
        var path = firstPath.Count > 0 ? firstPath : FindPath(map, second.Position!.Value, first.Position!.Value);
        Assert.NotEmpty(path);
        RoomMoveResult? move = null;
        foreach (var target in path)
        {
            move = room.MovePlayerAndPair(movingId, target, room.Revision, DateTimeOffset.UnixEpoch);
            if (move.StartedDuel is not null) break;
            foreach (var monster in room.GetPlayer(movingId).Pve!.Monsters) monster.TakeDamage(10_000);
            Assert.True(room.TryEnterActionBar(movingId));
        }

        Assert.NotNull(move?.StartedDuel);
        Assert.Equal(movingId, move.StartedDuel.LatePlayerId);
        Assert.All(room.GetPlayer(movingId).Pve!.Monsters, monster => Assert.False(monster.IsDead));
        Assert.Equal(RoomPlayerPhase.Pvp, room.GetPlayer(firstId).Phase);
        Assert.Equal(RoomPlayerPhase.Pvp, room.GetPlayer(secondId).Phase);
        var enteredBattle = room.GetPlayer(movingId).Pve!.BattleId;
        room.EndDuelSurvived(move.StartedDuel.DuelId, DuelEndReason.MutualLeave);
        Assert.Equal(RoomPlayerPhase.Pve, room.GetPlayer(movingId).Phase);
        Assert.Equal(enteredBattle, room.GetPlayer(movingId).Pve!.BattleId);
        Assert.All(room.GetPlayer(movingId).Pve!.Monsters, monster => Assert.False(monster.IsDead));
    }


    [Fact]
    public void Frozen_pve_monsters_do_not_advance_during_duel()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = CreateRoom(firstId, lateId);
        var before = room.CapturePlayer(firstId).Pve!.Monsters;
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UnixEpoch);

        room.Advance(TimeSpan.FromSeconds(12));

        var frozen = room.CapturePlayer(firstId).Pve!;
        Assert.Equal(PveBattlePhase.Frozen, frozen.Phase);
        Assert.Equivalent(before, frozen.Monsters, strict: true);
        room.EndDuelSurvived(duel.DuelId, DuelEndReason.Escaped);
    }

    [Fact]
    public void Duel_leave_requires_both_players_within_eight_seconds()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = CreateRoom(firstId, lateId);
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UnixEpoch);

        Assert.False(room.RequestDuelLeave(duel.DuelId, firstId, DateTimeOffset.UnixEpoch.AddSeconds(1)));
        Assert.Equal(RoomPlayerPhase.Pvp, room.GetPlayer(firstId).Phase);
        Assert.Throws<DomainValidationException>(() => room.RequestDuelLeave(
            duel.DuelId, lateId, DateTimeOffset.UnixEpoch.AddSeconds(8.1)));

        Assert.True(room.RequestDuelLeave(duel.DuelId, lateId, DateTimeOffset.UnixEpoch.AddSeconds(7.9)));
        Assert.Equal(RoomPlayerPhase.Pve, room.GetPlayer(firstId).Phase);
        Assert.Equal(RoomPlayerPhase.Pve, room.GetPlayer(lateId).Phase);
        Assert.False(room.CanPairPlayers(firstId, lateId));
        room.Advance(TimeSpan.FromSeconds(45));
        Assert.True(room.CanPairPlayers(firstId, lateId));
    }

    [Fact]
    public void Escape_reading_is_interrupted_only_by_life_damage()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = CreateRoom(firstId, lateId);
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UnixEpoch);
        var first = room.GetPlayer(firstId);
        first.Combat.GainShield(5);

        room.RequestDuelEscape(duel.DuelId, firstId);
        first.Combat.TakeDamage(1);
        room.Advance(TimeSpan.FromSeconds(1));
        Assert.Equal(RoomPlayerPhase.Pvp, first.Phase);

        first.Combat.TakeDamage(5);
        room.Advance(TimeSpan.FromSeconds(1));
        Assert.Equal(RoomPlayerPhase.Pvp, first.Phase);
        room.RequestDuelEscape(duel.DuelId, firstId);
    }

    [Fact]
    public void Disconnect_pauses_a_duel_and_kills_the_disconnected_player_after_fifteen_seconds()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = CreateRoom(firstId, lateId);
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UnixEpoch);
        var before = room.CapturePlayer(firstId);

        room.MarkPlayerDisconnected(firstId);
        Assert.Throws<DomainValidationException>(() => room.PlayCards(
            lateId, duel.DuelId, firstId.ToString("D"),
            [room.GetPlayer(lateId).Combat.Deck.Hand[0].InstanceId], room.Revision,
            DateTimeOffset.UnixEpoch.AddSeconds(1)));
        room.Advance(TimeSpan.FromSeconds(14.9));
        Assert.Equal(RoomPlayerPhase.Pvp, room.GetPlayer(firstId).Phase);
        Assert.Equivalent(before.Combat, room.CapturePlayer(firstId).Combat, strict: true);

        room.Advance(TimeSpan.FromSeconds(0.1));

        Assert.Equal(RoomPlayerPhase.Dead, room.GetPlayer(firstId).Phase);
        Assert.Equal(RoomPlayerPhase.Pve, room.GetPlayer(lateId).Phase);
    }

    [Fact]
    public void Rejected_play_command_does_not_mutate_attacker_state()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = CreateRoom(firstId, lateId);
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UnixEpoch);
        var before = room.CapturePlayer(firstId);
        var revision = room.Revision;
        var cardId = room.GetPlayer(firstId).Combat.Deck.Hand[0].InstanceId;

        Assert.Throws<DomainValidationException>(() => room.PlayCards(
            firstId,
            duel.DuelId,
            Guid.NewGuid().ToString("D"),
            [cardId],
            revision,
            DateTimeOffset.UnixEpoch.AddSeconds(1)));

        Assert.Equal(revision, room.Revision);
        Assert.Equivalent(before, room.CapturePlayer(firstId), strict: true);
    }

    private static BattleRoom CreateRoom(Guid firstId, Guid lateId)
    {
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", catalog, seed: 9173);
        room.AddPlayer(new BattleRoomPlayerSetup(
            firstId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            CreatePve()));
        room.AddPlayer(new BattleRoomPlayerSetup(
            lateId,
            HeroClass.Guardian,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            CreatePve()));
        return room;
    }

    private static PveBattleState CreatePve() =>
        new(
            Guid.NewGuid(),
            "monster-1",
            [
                new MonsterCombatState(
                    "monster-1",
                    maximumHp: 84,
                    hp: 84,
                    shield: 0,
                    attackInterval: TimeSpan.FromSeconds(4),
                    intents:
                    [
                        new MonsterIntentState(MonsterIntentKind.Attack, 3, CardElement.Wood),
                        new MonsterIntentState(MonsterIntentKind.Empower, 2, CardElement.None)
                    ])
            ]);

    private static List<MapPosition> FindPath(ChaosMapState map, MapPosition start, MapPosition target)
    {
        var queue = new Queue<MapPosition>([start]);
        var previous = new Dictionary<MapPosition, MapPosition?> { [start] = null };
        while (queue.Count > 0)
        {
            var current = queue.Dequeue();
            if (current == target) break;
            foreach (var next in map.GetNeighbors(current).Where(next => map.CanMove(current, next)))
            {
                if (previous.ContainsKey(next)) continue;
                previous[next] = current;
                queue.Enqueue(next);
            }
        }
        if (!previous.ContainsKey(target)) return [];
        var path = new List<MapPosition>();
        for (var current = target; current != start; current = previous[current]!.Value) path.Add(current);
        path.Reverse();
        return path;
    }
}
