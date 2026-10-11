using System.Text.Json;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Realtime;

// B09.3: real typed client/server command path around one controlled O1 finishing
// boundary. This is not a live session, natural expedition, capacity experiment,
// automatic PVP matching, renderer, or MAIN acceptance fixture.
public sealed class MonsterPoolLegalRouteWireTests
{
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();
    private static readonly int[] Seeds = [473001, 474001, 475001];
    private static readonly HeroClass[] Heroes = [HeroClass.Mage, HeroClass.Priest, HeroClass.Guardian];
    private static readonly string[] FinalOperations = ["leave-first", "leave-second", "terminal-late"];
    private static CancellationToken Token => TestContext.Current.CancellationToken;

    [Fact]
    public async Task Legal_kill_choice_replay_restore_duel_return_and_terminal_use_original_typed_wire()
    {
        var phase = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_LEGAL_ROUTE_PHASE");
        if (string.IsNullOrEmpty(phase))
        {
            // Ordinary CI has a real native router smoke test. The independent
            // cloud profile rejects this fallback and requires Godot-produced wire.
            var row = Prepare(HeroClass.Mage, Seeds[0], "native-ci");
            await using var session = Session.Open(row);
            var command = DescribeKill(row);
            var response = await session.Route(command, NativeWire(command));
            AssertKill(row, session.Room, response);
            var candidate = Assert.Single(session.Room.GetPlayer(row.OwnerId).MonsterPool.Pending);
            var choose = DescribeChoice(row with { Snapshot = session.Room.Capture(), CandidateId = candidate.InstanceId }, "accept", row.OwnerId, true);
            var bytes = NativeWire(choose);
            var before = session.Room.Capture();
            var first = await session.Route(choose, bytes);
            var duplicate = await session.Route(choose, bytes);
            Assert.Equivalent(first, duplicate, strict: true);
            Assert.Equal(before.Revision + 1, session.Room.Revision);
            Assert.Equal(21, All(session.Room.GetPlayer(row.OwnerId).Combat.Deck).Count());
            return;
        }

        Assert.True(OperatingSystem.IsLinux(), "The PR13 native evidence profile runs only on the cloud Linux test host.");
        var directory = Required("FANTASYCARD_PR13_LEGAL_ROUTE_DIRECTORY");
        var source = Required("FANTASYCARD_PR13_SOURCE_SHA");
        Assert.Matches("^[0-9a-f]{40}$", source);
        Directory.CreateDirectory(directory);
        switch (phase)
        {
            case "prepare":
                var rows = Heroes.SelectMany(hero => Seeds.Select(seed => Prepare(hero, seed, source))).ToArray();
                WriteRows(directory, "kill-inputs.jsonl", rows);
                WriteRows(directory, "kill-descriptors.jsonl", rows.Select(DescribeKill));
                Receipt(directory, phase, source, 9, 9, 0);
                break;
            case "kill":
                await RouteKills(directory, source);
                break;
            case "choose":
                await RouteChoices(directory, source);
                break;
            case "final":
                await RouteFinal(directory, source);
                break;
            default:
                throw new InvalidOperationException("Unknown PR13 legal route phase.");
        }
    }

    private static async Task RouteKills(string directory, string source)
    {
        var rows = ReadRows<FixtureRow>(directory, "kill-inputs.jsonl");
        AssertMatrix(rows, source);
        var commands = ReadCommands(directory, "kill-godot-commands.jsonl", source, 9);
        var next = new List<FixtureRow>();
        var descriptors = new List<CommandDescriptor>();
        var evidence = new List<object>();
        foreach (var row in rows)
        {
            await using var session = Session.Open(row);
            var descriptor = DescribeKill(row);
            var initial = session.Baseline(row.OwnerId);
            var wire = Take(commands, descriptor);
            var before = session.Room.Capture();
            var deliveries = await Task.WhenAll(session.Route(descriptor, wire), session.Route(descriptor, wire));
            Assert.Equivalent(deliveries[0], deliveries[1], strict: true);
            Assert.Equal(deliveries[0].Select(Wire), deliveries[1].Select(Wire));
            AssertKill(row, session.Room, deliveries[0]);
            var candidate = Assert.Single(session.Room.GetPlayer(row.OwnerId).MonsterPool.Pending);
            var chosen = row with { Snapshot = session.Room.Capture(), CandidateId = candidate.InstanceId };
            next.Add(chosen);
            descriptors.Add(DescribeChoice(chosen, "foreign", row.OtherId, true));
            descriptors.Add(DescribeChoice(chosen, "accept", row.OwnerId, true));
            descriptors.Add(DescribeChoice(chosen, "fingerprint-mismatch", row.OwnerId, false));
            evidence.Add(Evidence(row, descriptor, wire, before, session.Room.Capture(), initial, deliveries[0], deliveries[1]));
        }
        Assert.Empty(commands);
        WriteRows(directory, "kill-events.jsonl", evidence);
        WriteRows(directory, "choose-inputs.jsonl", next);
        WriteRows(directory, "choose-descriptors.jsonl", descriptors);
        Receipt(directory, "kill", source, rows.Length, evidence.Count, 18);
    }

    private static async Task RouteChoices(string directory, string source)
    {
        var rows = ReadRows<FixtureRow>(directory, "choose-inputs.jsonl");
        AssertMatrix(rows, source);
        var commands = ReadCommands(directory, "choose-godot-commands.jsonl", source, 27);
        var next = new List<FixtureRow>();
        var descriptors = new List<CommandDescriptor>();
        var evidence = new List<object>();
        foreach (var row in rows)
        {
            await using var session = Session.Open(row);
            var foreign = DescribeChoice(row, "foreign", row.OtherId, true);
            var foreignInitial = session.Baseline(row.OtherId);
            var foreignWire = Take(commands, foreign);
            var foreignBefore = session.Room.Capture();
            var foreignPlayer = foreignBefore.Players.Single(player => player.PlayerId == row.OtherId);
            Assert.Equal(RoomPlayerPhase.Choice, foreignPlayer.Phase);
            Assert.Null(foreignPlayer.ExtractionRemaining);
            Assert.Null(foreignPlayer.SpringDrink);
            Assert.Null(foreignPlayer.DisconnectedRemaining);
            var foreignPool = foreignPlayer.MonsterPool!;
            Assert.Equal(row.OtherCandidateId, Assert.Single(foreignPool.Pending).InstanceId);
            Assert.Equal(row.OtherSourceKey, Assert.Single(foreignPool.GrantedSources));
            Assert.NotEqual(row.OtherSourceKey, row.SourceKey);
            Assert.NotEqual(row.OtherCandidateId, row.CandidateId!.Value);
            Assert.DoesNotContain(foreignPool.Pending, card => card.InstanceId == row.CandidateId);
            var rejected = await session.Route(foreign, foreignWire);
            var rejection = Assert.IsType<CommandRejectedEventPayload>(Assert.Single(rejected).Payload);
            Assert.Equal("COMMAND_REJECTED", rejection.Code);
            Assert.Equal("The monster candidate no longer exists.", rejection.Detail);
            Assert.Equivalent(foreignBefore, session.Room.Capture(), strict: true);
            evidence.Add(Evidence(row, foreign, foreignWire, foreignBefore, session.Room.Capture(), foreignInitial, rejected));

            var accept = DescribeChoice(row, "accept", row.OwnerId, true);
            var initial = session.Baseline(row.OwnerId);
            var originalWire = Take(commands, accept);
            var before = session.Room.Capture();
            // Concurrent duplicate delivery uses the same authenticated owner and
            // the same complete original Godot wire, including revision and scope.
            var deliveries = await Task.WhenAll(session.Route(accept, originalWire), session.Route(accept, originalWire));
            Assert.Equivalent(deliveries[0], deliveries[1], strict: true);
            Assert.Equal(deliveries[0].Select(Wire), deliveries[1].Select(Wire));
            var after = session.Room.Capture();
            AssertChoice(row, before, after, accept.RequestId);
            evidence.Add(Evidence(row, accept, originalWire, before, after, initial, deliveries[0], deliveries[1]));

            var mismatch = DescribeChoice(row, "fingerprint-mismatch", row.OwnerId, false);
            var changedWire = Take(commands, mismatch);
            var changedResponse = await session.Route(mismatch, changedWire);
            Assert.Equal("REQUEST_ID_REUSED", Assert.IsType<CommandRejectedEventPayload>(Assert.Single(changedResponse).Payload).Code);
            Assert.Equivalent(after, session.Room.Capture(), strict: true);
            // Keep the original sequence stream and the accepted snapshot before
            // the rejected changed request. No synthetic client state dictionaries.
            evidence.Add(Evidence(row, mismatch, changedWire, before, after, initial,
                deliveries[0].Concat(changedResponse).ToArray()));

            var accepted = row with { Snapshot = after };
            await using (var restored = Session.Open(accepted))
            {
                var restoredInitial = restored.Baseline(row.OwnerId);
                var restoredBefore = restored.Room.Capture();
                var receiptReplay = await restored.Route(accept, originalWire);
                Assert.Single(receiptReplay);
                Assert.Equal("room.snapshot", receiptReplay[0].Type);
                Assert.Equivalent(restoredBefore, restored.Room.Capture(), strict: true);
                Assert.Single(restored.Room.GetPlayer(row.OwnerId).MonsterPool.Active);
                evidence.Add(Evidence(row, accept with { Operation = "restore-receipt" }, originalWire,
                    restoredBefore, restored.Room.Capture(), restoredInitial, receiptReplay));
            }

            // An explicit actor control starts the duel. This fixture does not
            // claim evidence for natural movement or automatic same-cell matching.
            var duel = await session.Actor.ExecuteAsync(new StartRoomDuelCommand(row.OwnerId, row.OtherId, session.Clock.GetUtcNow()), Token);
            var pvp = accepted with { Snapshot = session.Room.Capture(), FrozenSnapshot = after, DuelId = duel.DuelId };
            next.Add(pvp);
            descriptors.Add(DescribeFinal(pvp, "leave-first"));
            descriptors.Add(DescribeFinal(pvp, "leave-second"));
            descriptors.Add(DescribeFinal(pvp, "terminal-late"));
        }
        Assert.Empty(commands);
        WriteRows(directory, "choose-events.jsonl", evidence);
        WriteRows(directory, "final-inputs.jsonl", next);
        WriteRows(directory, "final-descriptors.jsonl", descriptors);
        Receipt(directory, "choose", source, rows.Length, evidence.Count, 45);
    }

    private static async Task RouteFinal(string directory, string source)
    {
        var rows = ReadRows<FixtureRow>(directory, "final-inputs.jsonl");
        AssertMatrix(rows, source);
        var commands = ReadCommands(directory, "final-godot-commands.jsonl", source, 27);
        var evidence = new List<object>();
        foreach (var row in rows)
        {
            Assert.NotNull(row.FrozenSnapshot);
            await using (var session = Session.Open(row))
            {
                foreach (var operation in FinalOperations.Take(2))
                {
                    var descriptor = DescribeFinal(row, operation);
                    Assert.Equal(session.Room.Revision, descriptor.ExpectedRevision);
                    var before = session.Room.Capture();
                    var initial = session.Baseline(descriptor.ActorId);
                    var bytes = Take(commands, descriptor);
                    var response = await session.Route(descriptor, bytes);
                    Assert.Equal(operation == "leave-second", Assert.IsType<DuelLeaveEventPayload>(response[0].Payload).Completed);
                    Assert.Equal("room.snapshot", response[^1].Type);
                    evidence.Add(Evidence(row, descriptor, bytes, before, session.Room.Capture(), initial, response));
                }
                Assert.Empty(session.Room.Capture().Duels);
                foreach (var playerId in new[] { row.OwnerId, row.OtherId })
                {
                    var frozen = row.FrozenSnapshot!.Players.Single(player => player.PlayerId == playerId);
                    var returned = session.Room.Capture().Players.Single(player => player.PlayerId == playerId);
                    Assert.Equal(frozen.Phase, returned.Phase);
                    Assert.Equivalent(frozen.Combat, returned.Combat, strict: true);
                    Assert.Equivalent(frozen.Pve, returned.Pve, strict: true);
                    Assert.Equivalent(frozen.MonsterPool, returned.MonsterPool, strict: true);
                }
                Assert.Single(All(session.Room.GetPlayer(row.OwnerId).Combat.Deck).Where(card => card.InstanceId == row.CandidateId));
                AssertBasis(row, session.Room);
            }

            await using (var terminal = Session.Open(row))
            {
                // Register while active, then end through the serialized actor.
                // Registering an already terminal room would remove its player route.
                await terminal.Actor.ExecuteAsync(new AbandonBattleCommand(row.OwnerId), Token);
                var before = terminal.Room.Capture();
                Assert.Equal(RoomPlayerPhase.Dead, terminal.Room.GetPlayer(row.OwnerId).Phase);
                Assert.Empty(terminal.Room.GetPlayer(row.OwnerId).MonsterPool.Active);
                Assert.Equal(20, All(terminal.Room.GetPlayer(row.OwnerId).Combat.Deck).Count());
                var descriptor = DescribeFinal(row, "terminal-late");
                Assert.Equal(before.Revision, descriptor.ExpectedRevision);
                var initial = terminal.Baseline(row.OwnerId);
                var bytes = Take(commands, descriptor);
                var response = await terminal.Route(descriptor, bytes);
                var cancelled = Assert.IsType<RoomCommandCancelledEventPayload>(response[0].Payload);
                Assert.Equal((row.Snapshot.RoomId, row.MatchId, "monster.choose", "RoomEndedBeforeApply"),
                    (cancelled.RoomId, cancelled.MatchId, cancelled.CommandType, cancelled.Reason));
                Assert.Equal("room.snapshot", response[1].Type);
                Assert.Equivalent(before, terminal.Room.Capture(), strict: true);
                var replay = await terminal.Route(descriptor, bytes);
                Assert.Equivalent(response, replay, strict: true);
                evidence.Add(Evidence(row, descriptor, bytes, before, terminal.Room.Capture(), initial, response, replay));
            }
        }
        Assert.Empty(commands);
        WriteRows(directory, "final-events.jsonl", evidence);
        Receipt(directory, "final", source, rows.Length, evidence.Count, 36);
    }

    private static FixtureRow Prepare(HeroClass hero, int seed, string source)
    {
        var config = GameConfigCatalog.Current;
        Assert.False(config.Numerics.OptionalMonsterPool);
        var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", _ => "GUA" };
        var cards = Enumerable.Range(1, 13).Select(index => $"C{index:D2}")
            .Concat(Enumerable.Range(1, 7).Select(index => $"{prefix}-{index:D2}")).ToArray();
        var owned = config.Cards.Where(card => card.Enabled && card.IsCodex && card.MonsterType is null)
            .ToDictionary(card => card.CardId, card => new OwnedCard(card.CardId, card.HeroClass, (CardRarity)card.Rarity, 1, false));
        DeckRules.Validate(hero, cards, owned);
        var rules = config.Numerics with { OptionalMonsterPool = true, MonsterCapacity = 5 };
        Assert.Equal(config.Numerics, rules with { OptionalMonsterPool = false, MonsterCapacity = config.Numerics.MonsterCapacity });
        var room = new BattleRoom(Guid.NewGuid(), config.Version, Catalog, seed, rules);
        var owner = Guid.NewGuid(); var other = Guid.NewGuid();
        room.AddPlayer(new(owner, hero, cards, null));
        room.AddPlayer(new(other, hero, cards, null));
        var map = ChaosMapGenerator.Generate(seed, 2).Capture();
        var cells = map.Cells.Where(cell => cell.Layer == ChaosMapLayer.Outer && !cell.IsBoss).Take(2).ToArray();
        room.InitializeMap(ChaosMapState.Restore(map with
        {
            Cells = map.Cells.Select(cell => cells.Any(selected => selected.Position == cell.Position)
                ? cell with { MonsterGroupId = "O1", HasSpring = false } : cell).ToArray(),
            SpawnPositions = cells.Select(cell => cell.Position).ToArray()
        }));
        var player = room.GetPlayer(owner);
        var basis = All(player.Combat.Deck).ToArray();
        var pve = player.Pve!; var target = Assert.Single(pve.Monsters);
        target.TakeDamage(target.Hp + target.Shield - 1);
        CombatCardInstance? selectedCard = null;
        for (var tick = 0; tick < 300 && selectedCard is null; tick++)
        {
            selectedCard = player.Combat.Deck.Hand.FirstOrDefault(card =>
                CombatResolver.Resolve([Catalog.Get(card.CardId, card.Level, card.ElementOverride)], player.Combat, target.ElementalResistance).Damage > 0);
            if (selectedCard is null)
                room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch.AddMilliseconds((tick + 1) * 100));
        }
        Assert.NotNull(selectedCard);
        Assert.False(player.Combat.IsDead);
        // An eligible peer is necessary for the foreign-candidate negative
        // control to reach ownership lookup rather than failing the phase gate.
        // This preparatory peer finishing action is native Domain control, not
        // evidence of an additional Godot request or a natural expedition.
        var peer = room.GetPlayer(other); var peerPve = peer.Pve!;
        var peerTarget = Assert.Single(peerPve.Monsters);
        CombatCardInstance? peerCard = null;
        for (var tick = 0; tick < 300 && peerCard is null; tick++)
        {
            peerCard = peer.Combat.Deck.Hand.FirstOrDefault(card =>
                CombatResolver.Resolve([Catalog.Get(card.CardId, card.Level, card.ElementOverride)], peer.Combat, peerTarget.ElementalResistance).Damage > 0);
            if (peerCard is null)
                room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch.AddSeconds(30).AddMilliseconds((tick + 1) * 100));
        }
        Assert.NotNull(peerCard);
        Assert.False(peer.Combat.IsDead);
        Assert.False(player.Combat.IsDead);
        peerTarget.TakeDamage(peerTarget.Hp + peerTarget.Shield - 1);
        Assert.True(room.PlayCards(other, peerPve.BattleId, peerTarget.MonsterId, [peerCard.InstanceId], room.Revision,
            DateTimeOffset.UnixEpoch.AddMinutes(1)).TargetDefeated);
        Assert.Equal(RoomPlayerPhase.Choice, peer.Phase);
        var peerCandidate = Assert.Single(peer.MonsterPool.Pending);
        Assert.Equal("M-FIREBAT", peerCandidate.CardId);
        Assert.Equal($"{peerPve.BattleId:D}:{peerTarget.MonsterId}", Assert.Single(peer.MonsterPool.Capture().GrantedSources));
        Assert.Equal(20, All(peer.Combat.Deck).Count());
        Assert.Contains(selectedCard, player.Combat.Deck.Hand);
        target.TakeDamage(target.Hp + target.Shield - 1);
        Assert.Empty(player.MonsterPool.Pending);
        Assert.Empty(player.MonsterPool.Capture().GrantedSources);
        Assert.Equal(20, basis.Length);
        Assert.Equal(20, basis.Select(card => card.CardId).Distinct().Count());
        return new($"{hero}-{seed}", source, hero.ToString(), seed, owner, other, Guid.NewGuid(), room.Capture(), basis,
            pve.BattleId, target.MonsterId, selectedCard.InstanceId, $"{pve.BattleId:D}:{target.MonsterId}",
            peerCandidate.InstanceId, $"{peerPve.BattleId:D}:{peerTarget.MonsterId}");
    }

    private static void AssertKill(FixtureRow row, BattleRoom room, IReadOnlyList<ServerEvent> response)
    {
        Assert.Equal("battle.combo_resolved", response[0].Type);
        Assert.True(Assert.IsType<BattleComboResolvedEventPayload>(response[0].Payload).TargetDefeated);
        Assert.Equal("room.snapshot", response[^1].Type);
        var player = room.GetPlayer(row.OwnerId);
        Assert.Equal(RoomPlayerPhase.Choice, player.Phase);
        Assert.Equal("M-FIREBAT", Assert.Single(player.MonsterPool.Pending).CardId);
        Assert.Equal(row.SourceKey, Assert.Single(player.MonsterPool.Capture().GrantedSources));
        Assert.Empty(player.MonsterPool.Active);
        Assert.Equal(20, All(player.Combat.Deck).Count());
        AssertBasis(row, room);
    }

    private static void AssertChoice(FixtureRow row, BattleRoomSnapshot before, BattleRoomSnapshot after, string requestId)
    {
        Assert.Equal(before.Revision + 1, after.Revision);
        var previous = before.Players.Single(player => player.PlayerId == row.OwnerId);
        var current = after.Players.Single(player => player.PlayerId == row.OwnerId);
        var previousPool = previous.MonsterPool!;
        var currentPool = current.MonsterPool!;
        var candidate = Assert.Single(previousPool.Pending);
        Assert.Equal(row.CandidateId, candidate.InstanceId);
        Assert.Equal(previous.Combat.Deck.Hand, current.Combat.Deck.Hand);
        Assert.Equal(previous.Combat.Deck.Library, current.Combat.Deck.Library);
        Assert.Equal(previous.Combat.Deck.Discard.Append(candidate), current.Combat.Deck.Discard);
        Assert.Empty(currentPool.Pending);
        Assert.Equal(candidate, Assert.Single(currentPool.Active));
        Assert.Equal(new MonsterCardDecisionReceipt(requestId, candidate.InstanceId, true, null), Assert.Single(currentPool.Receipts));
        Assert.Equal(previousPool.GrantedSources, currentPool.GrantedSources);
        // Outside the pool and its deck insertion the complete native snapshot
        // must be exactly unchanged, including rewards and the other owner.
        Assert.Equivalent(before, after with
        {
            Revision = before.Revision,
            Players = after.Players.Select(player => player.PlayerId == row.OwnerId
                ? current with { Combat = current.Combat with { Deck = previous.Combat.Deck }, MonsterPool = previous.MonsterPool } : player).ToArray()
        }, strict: true);
    }

    private static void AssertBasis(FixtureRow row, BattleRoom room)
    {
        var all = All(room.GetPlayer(row.OwnerId).Combat.Deck).ToArray();
        Assert.All(row.BaseCards, card => Assert.Contains(card, all));
        Assert.Equal(all.Length, all.Select(card => card.InstanceId).Distinct().Count());
    }

    private static CommandDescriptor DescribeKill(FixtureRow row) => new(row.Id, row.SourceSha, "kill", row.OwnerId,
        "battle.play_cards", "BattlePlayCardsCommand", $"legal-kill-{row.Id}", row.Snapshot.Revision, row.Snapshot.RoomId, row.MatchId,
        JsonSerializer.SerializeToElement(new { battle_id = row.BattleId.ToString("D"), target_id = row.TargetId,
            card_instance_ids = new[] { row.PlayedInstanceId.ToString("D") } }));

    private static CommandDescriptor DescribeChoice(FixtureRow row, string operation, Guid actor, bool accept) => new(row.Id, row.SourceSha,
        operation, actor, "monster.choose", "MonsterCardChooseCommand",
        operation == "foreign" ? $"legal-foreign-{row.Id}" : $"legal-choose-{row.Id}",
        row.Snapshot.Revision, row.Snapshot.RoomId, row.MatchId,
        JsonSerializer.SerializeToElement(new { candidate_id = row.CandidateId!.Value.ToString("D"), accept }));

    private static CommandDescriptor DescribeFinal(FixtureRow row, string operation)
    {
        var terminal = operation == "terminal-late";
        return new(row.Id, row.SourceSha, operation, operation == "leave-second" ? row.OtherId : row.OwnerId,
            terminal ? "monster.choose" : "duel.leave", terminal ? "MonsterCardChooseCommand" : "DuelLeaveCommand",
            $"legal-{operation}-{row.Id}", row.Snapshot.Revision + (operation == "leave-first" ? 0 : 1), row.Snapshot.RoomId, row.MatchId,
            terminal ? JsonSerializer.SerializeToElement(new { candidate_id = row.CandidateId!.Value.ToString("D"), accept = true })
                : JsonSerializer.SerializeToElement(new { duel_id = row.DuelId!.Value.ToString("D") }));
    }

    private static object Evidence(FixtureRow row, CommandDescriptor command, byte[] request, BattleRoomSnapshot before,
        BattleRoomSnapshot after, ServerEvent initial, IReadOnlyList<ServerEvent> response, IReadOnlyList<ServerEvent>? replay = null) => new
    {
        case_id = "PR13-B09.3", source_sha = row.SourceSha, row_id = row.Id, hero = row.Hero, seed = row.Seed,
        operation = command.Operation, actor_id = command.ActorId, owner_id = row.OwnerId, other_id = row.OtherId,
        source_key = row.SourceKey, base_cards = row.BaseCards, candidate_id = row.CandidateId,
        peer_control_candidate_id = row.OtherCandidateId, peer_control_source_key = row.OtherSourceKey,
        command, request_wire = Convert.ToBase64String(request), request_wire_bytes = request.Length,
        before, after, initial_wire = Wire(initial), response_wires = response.Select(Wire).ToArray(),
        replay_response_wires = (replay ?? []).Select(Wire).ToArray(),
        scope = "OFFLINE legal base deck, controlled O1 HP1; original Godot command -> native router -> serialized actor -> original server event -> Godot gateway/store"
    };

    private static string Wire(ServerEvent message)
    {
        var bytes = RealtimeProtobufCodec.EncodeServer(message);
        Assert.True(bytes.Length <= 16 * 1024);
        Assert.Equal(bytes, RealtimeProtobufCodec.EncodeServer(RealtimeProtobufCodec.DecodeServer(bytes)));
        return Convert.ToBase64String(bytes);
    }

    private static byte[] NativeWire(CommandDescriptor descriptor)
    {
        object payload = descriptor.Type == "battle.play_cards"
            ? new BattlePlayCardsCommandPayload(Guid.Parse(descriptor.Payload.GetProperty("battle_id").GetString()!),
                descriptor.Payload.GetProperty("target_id").GetString()!,
                descriptor.Payload.GetProperty("card_instance_ids").EnumerateArray().Select(value => Guid.Parse(value.GetString()!)).ToArray())
            : new MonsterCardChooseCommandPayload(Guid.Parse(descriptor.Payload.GetProperty("candidate_id").GetString()!), descriptor.Payload.GetProperty("accept").GetBoolean());
        return RealtimeProtobufCodec.EncodeClient(new(descriptor.Type, descriptor.RequestId, descriptor.ExpectedRevision,
            payload, descriptor.RoomId, descriptor.MatchId));
    }

    private static Dictionary<(string Row, string Operation), JsonElement> ReadCommands(string directory, string name, string source, int expected)
    {
        var values = ReadRows<JsonElement>(directory, name);
        Assert.Equal(expected, values.Length);
        Assert.All(values, row => Assert.Equal(source, row.GetProperty("source_sha").GetString()));
        return values.ToDictionary(row => (row.GetProperty("row_id").GetString()!, row.GetProperty("operation").GetString()!));
    }

    private static byte[] Take(Dictionary<(string Row, string Operation), JsonElement> values, CommandDescriptor descriptor)
    {
        Assert.True(values.Remove((descriptor.RowId, descriptor.Operation), out var row));
        Assert.Equal(descriptor.ActorId, Guid.Parse(row.GetProperty("actor_id").GetString()!));
        var bytes = Convert.FromBase64String(row.GetProperty("wire").GetString()!);
        Assert.Equal(row.GetProperty("wire_bytes").GetInt32(), bytes.Length);
        Assert.InRange(bytes.Length, 1, 16 * 1024);
        return bytes;
    }

    private static void AssertMatrix(FixtureRow[] rows, string source)
    {
        Assert.Equal(9, rows.Length);
        Assert.All(rows, row => Assert.Equal(source, row.SourceSha));
        Assert.All(rows, row => Assert.Equal($"{row.Hero}-{row.Seed}", row.Id));
        Assert.All(rows, row => Assert.Contains(Enum.Parse<HeroClass>(row.Hero), Heroes));
        Assert.All(rows, row => Assert.Contains(row.Seed, Seeds));
        Assert.All(rows, row => Assert.True(row.Snapshot.Numerics!.OptionalMonsterPool));
        Assert.All(rows, row => Assert.Equal(5, row.Snapshot.Numerics!.MonsterCapacity));
        Assert.Equal(Heroes.SelectMany(hero => Seeds.Select(seed => $"{hero}-{seed}")).Order(), rows.Select(row => row.Id).Order());
    }

    private static T[] ReadRows<T>(string directory, string name) => File.ReadLines(Path.Combine(directory, name))
        .Where(line => !string.IsNullOrWhiteSpace(line)).Select(line => JsonSerializer.Deserialize<T>(line)!).ToArray();

    private static void WriteRows<T>(string directory, string name, IEnumerable<T> rows)
    {
        using var stream = new StreamWriter(new FileStream(Path.Combine(directory, name), FileMode.CreateNew));
        foreach (var row in rows) stream.WriteLine(JsonSerializer.Serialize(row));
    }

    private static void Receipt(string directory, string phase, string source, int fixtures, int rows, int routed) =>
        WriteRows(directory, phase + "-native-receipt.jsonl", new[] { new { ok = true, source_sha = source, phase,
            fixture_rows = fixtures, evidence_rows = rows, native_routes = routed, original_Godot_wire_required = phase != "prepare",
            native_CI_fallback_used = false, MAIN_accepted = false, LIVE_accepted = false } });

    private static string Required(string name) => Environment.GetEnvironmentVariable(name)
        ?? throw new InvalidOperationException($"Required evidence environment variable {name} is missing.");
    private static IEnumerable<CombatCardInstance> All(CombatDeck deck) => deck.Hand.Concat(deck.Library).Concat(deck.Discard);

    private sealed record FixtureRow(string Id, string SourceSha, string Hero, int Seed, Guid OwnerId, Guid OtherId, Guid MatchId,
        BattleRoomSnapshot Snapshot, CombatCardInstance[] BaseCards, Guid BattleId, string TargetId, Guid PlayedInstanceId,
        string SourceKey, Guid OtherCandidateId, string OtherSourceKey, Guid? CandidateId = null,
        BattleRoomSnapshot? FrozenSnapshot = null, Guid? DuelId = null);
    private sealed record CommandDescriptor(string RowId, string SourceSha, string Operation, Guid ActorId, string Type, string Schema,
        string RequestId, long ExpectedRevision, Guid RoomId, Guid MatchId, JsonElement Payload);

    private sealed class FixtureClock : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => DateTimeOffset.UnixEpoch.AddHours(1);
    }

    private sealed class Session : IAsyncDisposable
    {
        public BattleRoom Room { get; }
        public FixtureClock Clock { get; } = new();
        public RoomActor Actor { get; }
        private readonly RoomRegistry _registry;
        private readonly RealtimeEventStore _events;
        private readonly RealtimeCommandRouter _router;
        private readonly Guid _matchId;
        private Session(FixtureRow row)
        {
            Room = BattleRoom.Restore(row.Snapshot, Catalog, row.Seed);
            _matchId = row.MatchId;
            _events = new(Clock);
            _registry = new(Clock);
            Actor = _registry.Register(Room, row.MatchId, startTicker: false);
            _router = new(_events, Clock, _registry);
        }
        public static Session Open(FixtureRow row) => new(row);
        public ServerEvent Baseline(Guid actor) => _events.Create(actor, "room.snapshot", "legal-route-before",
            RoomSnapshotProjection.Build(new GetRoomClientStateCommand(actor).Execute(Room), actor, _matchId, Clock.GetUtcNow()),
            roomRevision: Room.Revision);
        public async Task<IReadOnlyList<ServerEvent>> Route(CommandDescriptor descriptor, byte[] wire)
        {
            var command = RealtimeProtobufCodec.DecodeClient(wire);
            Assert.Equal(descriptor.Type, command.Type);
            Assert.Equal(descriptor.RequestId, command.RequestId);
            Assert.Equal(descriptor.ExpectedRevision, command.ExpectedRevision);
            Assert.Equal(descriptor.RoomId, command.RoomId);
            Assert.Equal(descriptor.MatchId, command.MatchId);
            Assert.InRange(command.RequestId!.Length, 1, 80);
            // Re-encode validates the exact typed payload without using a second
            // manually constructed expected response or bypassing the router.
            var decodedPayload = command.Type switch
            {
                "battle.play_cards" => Assert.IsType<BattlePlayCardsCommandPayload>(command.Payload),
                "monster.choose" => (object)Assert.IsType<MonsterCardChooseCommandPayload>(command.Payload),
                "duel.leave" => Assert.IsType<DuelLeaveCommandPayload>(command.Payload),
                _ => throw new InvalidOperationException("Unsupported legal route command.")
            };
            if (decodedPayload is BattlePlayCardsCommandPayload play)
            {
                Assert.Equal(descriptor.Payload.GetProperty("battle_id").GetString(), play.BattleId.ToString("D"));
                Assert.Equal(descriptor.Payload.GetProperty("target_id").GetString(), play.TargetId);
                Assert.Equal(descriptor.Payload.GetProperty("card_instance_ids").EnumerateArray().Select(value => value.GetString()), play.CardInstanceIds.Select(value => value.ToString("D")));
            }
            else if (decodedPayload is MonsterCardChooseCommandPayload choose)
            {
                Assert.Equal(descriptor.Payload.GetProperty("candidate_id").GetString(), choose.CandidateId.ToString("D"));
                Assert.Equal(descriptor.Payload.GetProperty("accept").GetBoolean(), choose.Accept);
                Assert.Null(choose.ReplaceInstanceId);
            }
            else if (decodedPayload is DuelLeaveCommandPayload leave)
                Assert.Equal(descriptor.Payload.GetProperty("duel_id").GetString(), leave.DuelId.ToString("D"));
            return await _router.RouteAsync(PlayerProfile.Create(descriptor.ActorId, "LegalRoute", Clock.GetUtcNow()), command,
                "legal-route-" + descriptor.Operation, Token);
        }
        public ValueTask DisposeAsync() => _registry.DisposeAsync();
    }
}
