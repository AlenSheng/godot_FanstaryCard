using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Matchmaking;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class RealtimeCommandRouterTests
{
    [Fact]
    public async Task RouteAsync_RewardRefreshReceiptPreventsDuplicateSpendAfterRouterRestart()
    {
        var playerId = Guid.NewGuid();
        var catalog = new CombatCardCatalog([new("test-hit", new CombatCardEffect(DirectDamage: 10000))]);
        var room = new BattleRoom(Guid.NewGuid(), "test", catalog, seed: 17);
        room.AddPlayer(new(playerId, HeroClass.Mage, Enumerable.Repeat("test-hit", 20).ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(17, 1));
        var roomPlayer = room.GetPlayer(playerId);
        foreach (var monster in roomPlayer.Pve!.Monsters.ToArray())
        {
            if (roomPlayer.Combat.Deck.Hand.Count == 0) roomPlayer.Combat.DrawImmediate(1);
            room.PlayCards(playerId, roomPlayer.Pve.BattleId, monster.MonsterId,
                [roomPlayer.Combat.Deck.Hand[0].InstanceId], room.Revision, DateTimeOffset.UnixEpoch);
        }
        roomPlayer.Inventory.TryAdd(new("gold", ExplorationItemKind.Gold, 100));
        var goldBefore = roomPlayer.Inventory.GoldQuantity;
        var expectedRevision = room.Revision;
        var command = new ClientCommand("choice.refresh", "refresh-router-01", expectedRevision,
            new RewardChoiceRefreshCommandPayload());
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, Guid.NewGuid(), startTicker: false);
        var player = PlayerProfile.Create(playerId, "测试玩家", DateTimeOffset.UtcNow);

        var first = await new RealtimeCommandRouter(store, TimeProvider.System, registry).RouteAsync(
            player, command, "trace", TestContext.Current.CancellationToken);
        var revisionAfterFirst = room.Revision;
        var replay = await new RealtimeCommandRouter(store, TimeProvider.System, registry).RouteAsync(
            player, command, "trace", TestContext.Current.CancellationToken);

        Assert.Equal(goldBefore - 60, roomPlayer.Inventory.GoldQuantity);
        Assert.Equal(revisionAfterFirst, room.Revision);
        Assert.Equal(revisionAfterFirst, Assert.Single(first).RoomRevision);
        Assert.Equal(revisionAfterFirst, Assert.Single(replay).RoomRevision);
        Assert.Equivalent(Assert.Single(first).Payload, Assert.Single(replay).Payload, strict: true);
    }

    [Fact]
    public async Task RouteAsync_RoomReadyReturnsPersistedLobbyProgress()
    {
        var playerId = Guid.NewGuid();
        var matchId = Guid.NewGuid();
        var roomId = Guid.NewGuid();
        var deadline = DateTimeOffset.UtcNow.AddSeconds(15);
        var ready = new StubReadyService(new(matchId, roomId, deadline, 2, 3, true));
        var store = new RealtimeEventStore(TimeProvider.System);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, roomReadyService: ready);
        var player = PlayerProfile.Create(playerId, "测试玩家", DateTimeOffset.UtcNow);

        var response = await router.RouteAsync(player,
            new ClientCommand("room.ready", "ready-01", null, new RoomReadyCommandPayload()),
            "trace", TestContext.Current.CancellationToken);

        Assert.Equal(playerId, ready.LastPlayerId);
        var accepted = Assert.IsType<RoomReadyAcceptedEventPayload>(Assert.Single(response).Payload);
        Assert.Equal((matchId, roomId, 2, 3),
            (accepted.MatchId, accepted.RoomId, accepted.ReadyPlayers, accepted.RequiredPlayers));
    }

    [Fact]
    public void Route_PingReturnsPongWithSequence()
    {
        var store = new RealtimeEventStore(TimeProvider.System);
        var router = new RealtimeCommandRouter(store, TimeProvider.System);
        var player = PlayerProfile.Create(Guid.NewGuid(), "测试玩家", DateTimeOffset.UtcNow);

        var response = router.Route(player, new ClientCommand("ping", null, null, null), "trace");

        var pong = Assert.Single(response);
        Assert.Equal("pong", pong.Type);
        Assert.Equal(1, pong.Sequence);
    }

    [Fact]
    public void Route_StateCommandWithoutRequestIdIsRejected()
    {
        var store = new RealtimeEventStore(TimeProvider.System);
        var router = new RealtimeCommandRouter(store, TimeProvider.System);
        var player = PlayerProfile.Create(Guid.NewGuid(), "测试玩家", DateTimeOffset.UtcNow);

        var response = router.Route(
            player,
            new ClientCommand("match.enqueue", null, null, null),
            "trace");

        Assert.Equal("error.command_rejected", Assert.Single(response).Type);
    }

    [Fact]
    public async Task RouteAsync_BattlePlayCardsExecutesInsideRegisteredRoom()
    {
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(
            Guid.NewGuid(),
            "test-config",
            CombatCardCatalog.CreatePrototype(),
            seed: 19);
        var pve = new PveBattleState(
            Guid.NewGuid(),
            "monster-1",
            [
                new MonsterCombatState(
                    "monster-1",
                    100,
                    100,
                    0,
                    TimeSpan.FromSeconds(5),
                    [new MonsterIntentState(MonsterIntentKind.Attack, 1, CardElement.Fire)])
            ]);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            pve));
        var cardId = room.CapturePlayer(playerId).Combat.Deck.Hand[0].InstanceId;
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "测试玩家", DateTimeOffset.UtcNow);

        var response = await router.RouteAsync(
            player,
            new ClientCommand(
                "battle.play_cards",
                "play-1",
                0,
                new BattlePlayCardsCommandPayload(pve.BattleId, "monster-1", [cardId])),
            "trace",
            TestContext.Current.CancellationToken);

        var resolved = Assert.Single(response);
        Assert.Equal("battle.combo_resolved", resolved.Type);
        Assert.Equal(1, resolved.RoomRevision);
        Assert.IsType<BattleComboResolvedEventPayload>(resolved.Payload);
    }

    [Fact]
    public async Task RouteAsync_BattleAbandonSettles_the_active_battle_as_dead()
    {
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), seed: 19);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            new PveBattleState(
                Guid.NewGuid(),
                "monster-1",
                [new MonsterCombatState(
                    "monster-1",
                    100,
                    100,
                    0,
                    TimeSpan.FromSeconds(5),
                    [new MonsterIntentState(MonsterIntentKind.Attack, 1, CardElement.Fire)])])));
        room.InitializeMap(ChaosMapGenerator.Generate(19, 1));
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "测试玩家", DateTimeOffset.UtcNow);

        var response = await router.RouteAsync(
            player,
            new ClientCommand("battle.abandon", "abandon-1", room.Revision, new BattleAbandonCommandPayload()),
            "trace",
            TestContext.Current.CancellationToken);

        var snapshotMessage = Assert.Single(response);
        Assert.Equal("room.snapshot", snapshotMessage.Type);
        var snapshot = Assert.IsType<RoomSnapshotEventPayload>(snapshotMessage.Payload);
        Assert.Equal(RoomPlayerPhase.Dead.ToString(), snapshot.Player.Phase);
        Assert.Equal(RoomPlayerPhase.Dead, room.GetPlayer(playerId).Phase);
    }

    [Fact]
    public async Task RouteAsync_DuelLeaveRequiresBothParticipants()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), seed: 23);
        room.AddPlayer(new BattleRoomPlayerSetup(firstId, HeroClass.Mage, Enumerable.Range(1, 20).Select(i => $"common-{i:D2}").ToArray(), null));
        room.AddPlayer(new BattleRoomPlayerSetup(lateId, HeroClass.Priest, Enumerable.Range(1, 20).Select(i => $"common-{i:D2}").ToArray(), null));
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UtcNow);
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(firstId, "测试玩家", DateTimeOffset.UtcNow);

        var response = await router.RouteAsync(
            player,
            new ClientCommand("duel.leave", "leave-01", room.Revision, new DuelLeaveCommandPayload(duel.DuelId)),
            "trace",
            TestContext.Current.CancellationToken);

        var acknowledged = Assert.Single(response);
        Assert.Equal("duel.leave_ack", acknowledged.Type);
        Assert.False(Assert.IsType<DuelLeaveEventPayload>(acknowledged.Payload).Completed);
        Assert.Equal(RoomPlayerPhase.Pvp, room.GetPlayer(firstId).Phase);
    }

    [Fact]
    public async Task RouteAsync_ActionSpringStartsAuthoritativeReadBar()
    {
        var playerId = Guid.NewGuid();
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", catalog, seed: 31);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            null));
        room.InitializeMap(ChaosMapGenerator.Generate(31, 1));
        var snapshot = room.Capture();
        var spring = snapshot.Map!.Cells.First(cell => !cell.IsBoss).Position;
        snapshot = snapshot with
        {
            Map = snapshot.Map with
            {
                Cells = snapshot.Map.Cells.Select(cell =>
                    cell.Position == spring ? cell with { HasSpring = true } : cell).ToArray()
            },
            Players = snapshot.Players.Select(value => value with
            {
                Position = spring,
                Phase = RoomPlayerPhase.ActionBar,
                Pve = null
            }).ToArray()
        };
        room = BattleRoom.Restore(snapshot, catalog, 31);
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "测试玩家", DateTimeOffset.UtcNow);

        var response = await router.RouteAsync(
            player,
            new ClientCommand("action.spring", "spring-01", room.Revision, new ActionSpringCommandPayload()),
            "trace",
            TestContext.Current.CancellationToken);

        var started = Assert.Single(response);
        Assert.Equal("action.spring_started", started.Type);
        Assert.Equal(TimeSpan.FromSeconds(1.2), Assert.IsType<ActionSpringEventPayload>(started.Payload).Remaining);
        Assert.NotNull(room.CapturePlayer(playerId).SpringDrink);

        var snapshotResponse = await router.RouteAsync(
            player,
            new ClientCommand("room.snapshot.read", "spring-snapshot-01", null, new RoomSnapshotCommandPayload()),
            "trace",
            TestContext.Current.CancellationToken);
        var snapshotPayload = Assert.IsType<RoomSnapshotEventPayload>(Assert.Single(snapshotResponse).Payload);
        Assert.Equal(1200, snapshotPayload.SpringRemainingMs);
        Assert.Empty(snapshotPayload.AllowedActions);
    }

    [Fact]
    public async Task RouteAsync_ActionPotionConsumesAndHealsImmediately()
    {
        var playerId = Guid.NewGuid();
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", catalog, seed: 33);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            null));
        room.InitializeMap(ChaosMapGenerator.Generate(33, 1));
        var snapshot = room.Capture();
        snapshot = snapshot with
        {
            Players = snapshot.Players.Select(value => value with
            {
                Phase = RoomPlayerPhase.ActionBar,
                Pve = null
            }).ToArray()
        };
        room = BattleRoom.Restore(snapshot, catalog, 33);
        var roomPlayer = room.GetPlayer(playerId);
        roomPlayer.Inventory.TryAdd(new ExplorationItem("health_potion:1", ExplorationItemKind.HealthPotion));
        roomPlayer.Combat.TakeDamage(30);
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "测试玩家", DateTimeOffset.UtcNow);

        var before = await router.RouteAsync(
            player,
            new ClientCommand("room.snapshot.read", "potion-snapshot-01", null, new RoomSnapshotCommandPayload()),
            "trace",
            TestContext.Current.CancellationToken);
        Assert.Contains("action.potion", Assert.IsType<RoomSnapshotEventPayload>(Assert.Single(before).Payload).AllowedActions);

        var response = await router.RouteAsync(
            player,
            new ClientCommand("action.potion", "potion-01", room.Revision, new ActionPotionCommandPayload()),
            "trace",
            TestContext.Current.CancellationToken);

        var used = Assert.Single(response);
        Assert.Equal("action.potion_used", used.Type);
        var payload = Assert.IsType<ActionPotionEventPayload>(used.Payload);
        Assert.Equal("health_potion:1", payload.ItemId);
        Assert.Equal(14, payload.Healed);
        Assert.Equal(54, roomPlayer.Combat.Hp);
        Assert.DoesNotContain(roomPlayer.Inventory.Items, item => item.Kind == ExplorationItemKind.HealthPotion);
        Assert.Null(room.CapturePlayer(playerId).SpringDrink);
    }

    [Fact]
    public async Task RouteAsync_RoomSnapshotReturnsOnlyPlayerProjectionAndAllowedActions()
    {
        var playerId = Guid.NewGuid();
        var otherId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), seed: 37);
        room.AddPlayer(new BattleRoomPlayerSetup(playerId, HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));
        room.AddPlayer(new BattleRoomPlayerSetup(otherId, HeroClass.Guardian,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(37, 2));
        var matchId = Guid.NewGuid();
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, matchId, startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "测试玩家", DateTimeOffset.UtcNow);

        var response = await router.RouteAsync(
            player,
            new ClientCommand("room.snapshot.read", null, null, new RoomSnapshotCommandPayload()),
            "trace",
            TestContext.Current.CancellationToken);

        var message = Assert.Single(response);
        Assert.Equal("room.snapshot", message.Type);
        var snapshot = Assert.IsType<RoomSnapshotEventPayload>(message.Payload);
        Assert.Equal(matchId, snapshot.MatchId);
        Assert.Equal(playerId, snapshot.Player.PlayerId);
        Assert.Equal(36, snapshot.Map.Count);
        Assert.Contains("battle.play_cards", snapshot.AllowedActions);
        Assert.Contains("battle.abandon", snapshot.AllowedActions);
        Assert.DoesNotContain(snapshot.AllowedActions, action => action == "action.potion");
        Assert.NotEqual(room.GetPlayer(otherId).Position,
            new MapPosition(snapshot.Self.Row, snapshot.Self.Column));
        Assert.All(snapshot.Map, cell =>
        {
            Assert.InRange(cell.Row, 0, 5);
            Assert.InRange(cell.Column, 0, 5);
        });
    }

    [Fact]
    public async Task RouteAsync_ResumeGapReturnsSessionAndRoomSnapshots()
    {
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), seed: 41);
        room.AddPlayer(new BattleRoomPlayerSetup(playerId, HeroClass.Priest,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(41, 1));
        var store = new RealtimeEventStore(TimeProvider.System);
        for (var index = 0; index < 260; index++) store.Create(playerId, "old", "trace", null);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, Guid.NewGuid(), startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "测试玩家", DateTimeOffset.UtcNow);

        var response = await router.RouteAsync(
            player,
            new ClientCommand("session.resume", "resume-gap-01", null, new SessionResumeCommandPayload(0)),
            "trace",
            TestContext.Current.CancellationToken);

        Assert.Collection(
            response,
            message => Assert.Equal("session.snapshot", message.Type),
            message =>
            {
                Assert.Equal("room.snapshot", message.Type);
                Assert.IsType<RoomSnapshotEventPayload>(message.Payload);
            });
    }

    [Fact]
    public async Task RouteAsync_ResumeUsesRoomRevisionToAvoidUnnecessarySnapshot()
    {
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), seed: 43);
        room.AddPlayer(new BattleRoomPlayerSetup(playerId, HeroClass.Priest,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(43, 1));
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, Guid.NewGuid(), startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "测试玩家", DateTimeOffset.UtcNow);

        var current = await router.RouteAsync(
            player,
            new ClientCommand("session.resume", "resume-current-01", null,
                new SessionResumeCommandPayload(0, room.RoomId, room.Revision)),
            "trace",
            TestContext.Current.CancellationToken);
        var stale = await router.RouteAsync(
            player,
            new ClientCommand("session.resume", "resume-stale-01", null,
                new SessionResumeCommandPayload(0, room.RoomId, room.Revision - 1)),
            "trace",
            TestContext.Current.CancellationToken);

        Assert.Empty(current);
        Assert.Equal("room.snapshot", Assert.Single(stale).Type);
    }

    [Fact]
    public async Task RouteAsync_ConcurrentDuplicateExecutesRoomMutationOnceAndReplaysFullResponse()
    {
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), seed: 29);
        var pve = new PveBattleState(
            Guid.NewGuid(),
            "monster-1",
            [new MonsterCombatState("monster-1", 100, 100, 0, TimeSpan.FromSeconds(5),
                [new MonsterIntentState(MonsterIntentKind.Attack, 1, CardElement.Fire)])]);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            pve));
        var cardId = room.CapturePlayer(playerId).Combat.Deck.Hand[0].InstanceId;
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "测试玩家", DateTimeOffset.UtcNow);
        var command = new ClientCommand(
            "battle.play_cards",
            "same-request-01",
            0,
            new BattlePlayCardsCommandPayload(pve.BattleId, "monster-1", [cardId]));

        var responses = await Task.WhenAll(Enumerable.Range(0, 8).Select(_ =>
            router.RouteAsync(player, command, "trace", TestContext.Current.CancellationToken).AsTask()));

        Assert.Equal(1, room.Revision);
        var events = responses.Select(Assert.Single).ToArray();
        Assert.Single(events.Select(message => message.EventId).Distinct());
        Assert.Single(events.Select(message => message.Sequence).Distinct());
        Assert.All(events, message => Assert.Equal("battle.combo_resolved", message.Type));
    }

    [Fact]
    public async Task RouteAsync_RejectsRequestIdReusedForDifferentCommand()
    {
        var store = new RealtimeEventStore(TimeProvider.System);
        var router = new RealtimeCommandRouter(store, TimeProvider.System);
        var player = PlayerProfile.Create(Guid.NewGuid(), "测试玩家", DateTimeOffset.UtcNow);
        await router.RouteAsync(
            player,
            new ClientCommand("ping", "same-request-02", null, null),
            "trace",
            TestContext.Current.CancellationToken);

        var response = await router.RouteAsync(
            player,
            new ClientCommand("match.enqueue", "same-request-02", null, null),
            "trace",
            TestContext.Current.CancellationToken);

        var rejected = Assert.Single(response);
        Assert.Equal("error.command_rejected", rejected.Type);
        Assert.Equal("REQUEST_ID_REUSED", Assert.IsType<CommandRejectedEventPayload>(rejected.Payload).Code);
    }

    [Fact]
    public async Task RouteAsync_SelectTargetUpdatesAuthoritativePveTarget()
    {
        var playerId = Guid.NewGuid();
        var battleId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), seed: 83);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            new PveBattleState(battleId, "monster-1",
            [
                new MonsterCombatState("monster-1", 100, 100, 0, TimeSpan.FromSeconds(5),
                    [new MonsterIntentState(MonsterIntentKind.Attack, 1, CardElement.Fire)]),
                new MonsterCombatState("monster-2", 100, 100, 0, TimeSpan.FromSeconds(5),
                    [new MonsterIntentState(MonsterIntentKind.Attack, 1, CardElement.Water)])
            ])));
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "测试玩家", DateTimeOffset.UtcNow);

        var response = await router.RouteAsync(
            player,
            new ClientCommand("battle.select_target", "target-01", room.Revision,
                new BattleSelectTargetCommandPayload(battleId, "monster-2")),
            "trace",
            TestContext.Current.CancellationToken);

        var selected = Assert.Single(response);
        Assert.Equal("battle.target_selected", selected.Type);
        Assert.Equal("monster-2", Assert.IsType<BattleTargetSelectedEventPayload>(selected.Payload).TargetId);
        Assert.Equal("monster-2", room.CapturePlayer(playerId).Pve!.CurrentTargetId);
    }

    [Fact]
    public async Task RouteAsync_SnapshotAllowsSelectingLastSurvivorAfterTargetDies()
    {
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), seed: 37);
        room.AddPlayer(new(playerId, HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(37, 1));
        var pve = room.GetPlayer(playerId).Pve!;
        var dead = new MonsterCombatState("defeated", 100, 0, 0, TimeSpan.FromSeconds(5),
            [new(MonsterIntentKind.Attack, 1, CardElement.Fire)]);
        var survivor = new MonsterCombatState("survivor", 100, 100, 0, TimeSpan.FromSeconds(5),
            [new(MonsterIntentKind.Attack, 1, CardElement.Water)]);
        pve.Restore(pve.Capture() with
        {
            CurrentTargetId = dead.MonsterId,
            Monsters = [dead.Capture(), survivor.Capture()]
        });
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "Target test", DateTimeOffset.UtcNow);

        var response = await router.RouteAsync(player,
            new ClientCommand("room.snapshot.read", null, null, new RoomSnapshotCommandPayload()),
            "trace", TestContext.Current.CancellationToken);

        var snapshot = Assert.IsType<RoomSnapshotEventPayload>(Assert.Single(response).Payload);
        Assert.Contains("battle.select_target", snapshot.AllowedActions);
        var selected = await router.RouteAsync(player,
            new ClientCommand("battle.select_target", "last-survivor", room.Revision,
                new BattleSelectTargetCommandPayload(pve.BattleId, survivor.MonsterId)),
            "trace", TestContext.Current.CancellationToken);
        Assert.Equal("battle.target_selected", Assert.Single(selected).Type);
        Assert.Equal(survivor.MonsterId, room.CapturePlayer(playerId).Pve!.CurrentTargetId);
    }

    [Fact]
    public async Task RouteAsync_BossPhaseChangesOnlyAfterTheAuthoritativeStepCompletes()
    {
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), seed: 37);
        room.AddPlayer(new(playerId, HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(37, 1));
        var pve = room.GetPlayer(playerId).Pve!;
        var boss = new MonsterCombatState("annihilation-core", 280, 280, 0, TimeSpan.FromSeconds(4.4),
            [new(MonsterIntentKind.Attack, 4, CardElement.Fire)]);
        boss.TakeDamage(140);
        pve.Restore(pve.Capture() with { CurrentTargetId = boss.MonsterId, Monsters = [boss.Capture()] });
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "Boss phase test", DateTimeOffset.UtcNow);

        var pending = await ReadMonster();
        Assert.Equal(140, pending.Hp);
        Assert.Equal(1, pending.BossPhase);

        var activeBoss = Assert.Single(pve.Monsters);
        activeBoss.ResolveIntentDamage(activeBoss.Intents[0]);

        var transitioned = await ReadMonster();
        Assert.Equal(140, transitioned.Hp);
        Assert.Equal(2, transitioned.BossPhase);
        Assert.Equal("Metal", transitioned.IntentElement);

        async Task<RoomMonsterPayload> ReadMonster()
        {
            var response = await router.RouteAsync(player,
                new ClientCommand("room.snapshot.read", null, null, new RoomSnapshotCommandPayload()),
                "trace", TestContext.Current.CancellationToken);
            var snapshot = Assert.IsType<RoomSnapshotEventPayload>(Assert.Single(response).Payload);
            return Assert.Single(snapshot.Pve!.Monsters);
        }
    }

    private sealed class StubReadyService(ReadyLobbyView result) : IRoomReadyService
    {
        public Guid? LastPlayerId { get; private set; }
        public Task<ReadyLobbyView?> GetAsync(Guid playerId, CancellationToken cancellationToken) =>
            Task.FromResult<ReadyLobbyView?>(result);
        public Task<ReadyLobbyView> ReadyAsync(Guid playerId, CancellationToken cancellationToken)
        {
            LastPlayerId = playerId;
            return Task.FromResult(result);
        }
    }
}
