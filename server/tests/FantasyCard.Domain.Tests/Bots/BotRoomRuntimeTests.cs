using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Bots;

public sealed class BotRoomRuntimeTests
{
    [Fact]
    public void Bot_pve_uses_layer_timer_and_fixed_hp_loss_without_monster_ticks()
    {
        var (room, botId) = CreateBotRoom();
        var before = room.CapturePlayer(botId);

        room.Advance(TimeSpan.FromSeconds(31.9));

        var waiting = room.CapturePlayer(botId);
        Assert.Equal(RoomPlayerPhase.Pve, waiting.Phase);
        Assert.Equal(TimeSpan.FromMilliseconds(100), waiting.BotPveRemaining);
        Assert.Equal(before.Combat.Hp, waiting.Combat.Hp);
        Assert.Equivalent(before.Pve!.Monsters, waiting.Pve!.Monsters, strict: true);

        room.Advance(TimeSpan.FromMilliseconds(100));

        var completed = room.CapturePlayer(botId);
        Assert.Equal(RoomPlayerPhase.Choice, completed.Phase);
        Assert.Equal(58, completed.Combat.Hp);
        Assert.All(completed.Pve!.Monsters, monster => Assert.Equal(0, monster.Hp));
        Assert.NotNull(completed.RewardChoice);
        Assert.Null(completed.BotPveRemaining);
    }

    [Fact]
    public void Bot_claims_reward_according_to_frozen_choice_priority()
    {
        var (room, botId) = CreateBotRoom();
        room.Advance(TimeSpan.FromSeconds(32));

        room.Advance(TimeSpan.FromMilliseconds(100));

        var bot = room.CapturePlayer(botId);
        Assert.Equal(RoomPlayerPhase.ActionBar, bot.Phase);
        Assert.Null(bot.RewardChoice);
        Assert.Contains(bot.Inventory!.Items, item => item.Kind == ExplorationItemKind.Equipment);
    }

    [Fact]
    public void Bot_pve_timer_survives_room_snapshot_restore()
    {
        var (room, botId) = CreateBotRoom();
        room.Advance(TimeSpan.FromSeconds(11));
        var snapshot = room.Capture();

        var restored = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), seed: 991);

        Assert.True(restored.CapturePlayer(botId).IsBot);
        Assert.Equal(TimeSpan.FromSeconds(21), restored.CapturePlayer(botId).BotPveRemaining);
        restored.Advance(TimeSpan.FromSeconds(21));
        Assert.Equal(RoomPlayerPhase.Choice, restored.GetPlayer(botId).Phase);
    }

    [Fact]
    public void Bot_versus_bot_duel_resolves_after_ten_seconds_without_card_simulation()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = CreateDuelRoom(firstId, firstIsBot: true, lateId, lateIsBot: true);
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UnixEpoch);

        room.Advance(TimeSpan.FromSeconds(9.9), DateTimeOffset.UnixEpoch.AddSeconds(9.9));
        Assert.Equal(RoomPlayerPhase.Pvp, room.GetPlayer(firstId).Phase);
        Assert.Equal(TimeSpan.FromMilliseconds(100), Assert.Single(room.Capture().BotDuelTimers!).Remaining);

        room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch.AddSeconds(10));

        Assert.Empty(room.Capture().Duels);
        Assert.Empty(room.Capture().BotDuelTimers!);
        Assert.Equal(RoomPlayerPhase.ActionBar, room.GetPlayer(firstId).Phase);
        Assert.Equal(RoomPlayerPhase.ActionBar, room.GetPlayer(lateId).Phase);
        Assert.Equal(60, room.GetPlayer(firstId).Combat.Hp);
        Assert.Equal(65, room.GetPlayer(lateId).Combat.Hp);
        Assert.NotEqual(Guid.Empty, duel.DuelId);
    }

    [Fact]
    public void Bot_uses_medium_card_ai_against_a_human()
    {
        var humanId = Guid.NewGuid();
        var botId = Guid.NewGuid();
        var room = CreateDuelRoom(humanId, firstIsBot: false, botId, lateIsBot: true);
        room.StartDuel(humanId, botId, DateTimeOffset.UnixEpoch);
        var hpBefore = room.GetPlayer(humanId).Combat.Hp;

        room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch.AddSeconds(1));

        Assert.True(room.GetPlayer(humanId).Combat.Hp < hpBefore);
        Assert.NotEmpty(room.GetPlayer(botId).Combat.Deck.Discard);
    }

    [Fact]
    public void Bot_action_bar_moves_to_a_legal_non_outward_cell()
    {
        var botId = Guid.NewGuid();
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), "bot-action-test", catalog, 144);
        room.AddPlayer(new BattleRoomPlayerSetup(
            botId,
            HeroClass.Mage,
            Enumerable.Repeat("common-01", 20).ToArray(),
            null,
            IsBot: true));
        room.InitializeMap(ChaosMapGenerator.Generate(144, 1));
        var snapshot = room.Capture();
        var start = snapshot.Map!.Cells.First(cell =>
            cell.Layer == ChaosMapLayer.Outer && !cell.HasSpring && !cell.HasEvacuation).Position;
        snapshot = snapshot with
        {
            Players = snapshot.Players.Select(player => player with
            {
                Position = start,
                Phase = RoomPlayerPhase.ActionBar,
                Pve = null,
                BotPveRemaining = null
            }).ToArray()
        };
        room = BattleRoom.Restore(snapshot, catalog, 144);

        room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch);

        var destination = room.GetPlayer(botId).Position!.Value;
        Assert.Contains(destination, room.Map!.GetNeighbors(start));
        Assert.True(room.Map.GetCell(destination).Layer >= room.Map.GetCell(start).Layer);
    }

    [Fact]
    public void Room_terminates_bots_when_the_last_real_player_is_terminal()
    {
        var humanId = Guid.NewGuid();
        var botId = Guid.NewGuid();
        var room = CreateDuelRoom(humanId, firstIsBot: false, botId, lateIsBot: true);
        var duel = room.StartDuel(humanId, botId, DateTimeOffset.UnixEpoch);
        room.EndDuelWithDeath(duel.DuelId, humanId);

        room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch.AddSeconds(1));

        Assert.Equal(RoomPlayerPhase.Dead, room.GetPlayer(humanId).Phase);
        Assert.Equal(RoomPlayerPhase.Extracted, room.GetPlayer(botId).Phase);
    }

    [Fact]
    public void Bot_disconnect_notifications_are_ignored()
    {
        var (room, botId) = CreateBotRoom();

        room.MarkPlayerDisconnected(botId);

        Assert.Null(room.CapturePlayer(botId).DisconnectedRemaining);
    }

    [Fact]
    public void Killed_bot_destroys_loot_instead_of_creating_a_relic_pile()
    {
        var humanId = Guid.NewGuid();
        var botId = Guid.NewGuid();
        var room = CreateDuelRoom(humanId, firstIsBot: false, botId, lateIsBot: true);
        room.GetPlayer(botId).Inventory.TryAdd(new ExplorationItem(
            "bot-loot",
            ExplorationItemKind.EquipmentFragments,
            4));
        var duel = room.StartDuel(humanId, botId, DateTimeOffset.UnixEpoch);

        room.EndDuelWithDeath(duel.DuelId, botId);

        Assert.Equal(RoomPlayerPhase.Dead, room.GetPlayer(botId).Phase);
        Assert.Empty(room.Capture().RelicPiles!);
    }

    private static (BattleRoom Room, Guid BotId) CreateBotRoom()
    {
        var botId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "bot-runtime-test", CombatCardCatalog.CreatePrototype(), 991);
        room.AddPlayer(new BattleRoomPlayerSetup(
            botId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            null,
            IsBot: true));
        room.InitializeMap(ChaosMapGenerator.Generate(991, 1));
        return (room, botId);
    }

    private static BattleRoom CreateDuelRoom(
        Guid firstId,
        bool firstIsBot,
        Guid lateId,
        bool lateIsBot)
    {
        var room = new BattleRoom(Guid.NewGuid(), "bot-duel-test", CombatCardCatalog.CreatePrototype(), 773);
        room.AddPlayer(new BattleRoomPlayerSetup(
            firstId,
            HeroClass.Mage,
            Enumerable.Repeat("common-01", 20).ToArray(),
            null,
            IsBot: firstIsBot));
        room.AddPlayer(new BattleRoomPlayerSetup(
            lateId,
            HeroClass.Guardian,
            Enumerable.Repeat("common-01", 20).ToArray(),
            null,
            IsBot: lateIsBot));
        return room;
    }
}
