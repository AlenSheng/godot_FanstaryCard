using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Bots;

public sealed class BotOnlyRoomTerminationTests
{
    private static readonly Guid FirstBot = Guid.Parse("10000000-0000-4000-8000-000000000001");
    private static readonly Guid SecondBot = Guid.Parse("10000000-0000-4000-8000-000000000002");
    private static readonly Guid Human = Guid.Parse("10000000-0000-4000-8000-000000000003");

    [Fact]
    public void Bot_only_room_ends_on_first_authoritative_tick()
    {
        var room = CreateRoom(includeHuman: false, initializeMap: true);

        room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch);

        Assert.All(room.Capture().Players, player =>
        {
            Assert.True(player.IsBot);
            Assert.Equal(RoomPlayerPhase.Extracted, player.Phase);
            Assert.Null(player.Pve);
            Assert.Null(player.BotPveRemaining);
            Assert.Null(player.RewardChoice);
        });
    }

    [Fact]
    public void Restored_snapshot_without_its_last_human_ends_remaining_bots()
    {
        var original = CreateRoom(includeHuman: true, initializeMap: true);
        var snapshot = original.Capture();
        snapshot = snapshot with { Players = snapshot.Players.Where(player => player.IsBot).ToArray() };
        var room = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), 771);

        room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch);

        Assert.Equal(2, room.Capture().Players.Count);
        Assert.All(room.Capture().Players, player => Assert.Equal(RoomPlayerPhase.Extracted, player.Phase));
        Assert.Empty(room.Capture().Duels);
    }

    [Fact]
    public void No_human_bot_duel_is_cleared_without_waiting_for_simulated_combat()
    {
        var room = CreateRoom(includeHuman: false, initializeMap: false);
        room.StartDuel(FirstBot, SecondBot, DateTimeOffset.UnixEpoch);

        room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch.AddMilliseconds(100));

        var snapshot = room.Capture();
        Assert.Empty(snapshot.Duels);
        Assert.Empty(snapshot.BotDuelTimers!);
        Assert.All(snapshot.Players, player =>
        {
            Assert.Equal(RoomPlayerPhase.Extracted, player.Phase);
            Assert.Null(player.CurrentDuelId);
        });
    }

    [Fact]
    public void An_active_human_keeps_the_room_and_bot_simulation_running()
    {
        var room = CreateRoom(includeHuman: true, initializeMap: true);

        room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch);

        Assert.Equal(RoomPlayerPhase.Pve, room.GetPlayer(Human).Phase);
        Assert.All(room.Capture().Players.Where(player => player.IsBot), player =>
        {
            Assert.Equal(RoomPlayerPhase.Pve, player.Phase);
            Assert.NotNull(player.BotPveRemaining);
        });
    }

    [Fact]
    public void Empty_room_tick_has_no_player_or_duel_side_effect()
    {
        var room = new BattleRoom(Guid.NewGuid(), "no-human-lifecycle", CombatCardCatalog.CreatePrototype(), 771);

        room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch);

        Assert.Empty(room.Capture().Players);
        Assert.Empty(room.Capture().Duels);
        Assert.Empty(room.Capture().BotDuelTimers!);
    }

    private static BattleRoom CreateRoom(bool includeHuman, bool initializeMap)
    {
        var room = new BattleRoom(Guid.NewGuid(), "no-human-lifecycle", CombatCardCatalog.CreatePrototype(), 771);
        var cards = Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray();
        room.AddPlayer(new(FirstBot, HeroClass.Mage, cards, null, IsBot: true));
        room.AddPlayer(new(SecondBot, HeroClass.Guardian, cards, null, IsBot: true));
        if (includeHuman)
            room.AddPlayer(new(Human, HeroClass.Priest, cards, null));
        if (initializeMap)
            room.InitializeMap(ChaosMapGenerator.Generate(771, includeHuman ? 3 : 2));
        return room;
    }
}
