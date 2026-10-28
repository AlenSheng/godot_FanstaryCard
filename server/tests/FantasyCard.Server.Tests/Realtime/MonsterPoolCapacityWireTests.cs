using System.IO.Compression;
using System.Text;
using System.Text.Json;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Tests.Realtime;

// The real O1 finishing action establishes Choice. Further offers and pile
// relocation are explicit OFFLINE fixtures, not expedition benefit evidence.
public sealed class MonsterPoolCapacityWireTests
{
    private static readonly int[] Seeds = [460001, 461001, 462001];
    private static readonly string[] Piles = ["Hand", "Library", "Discard"];
    private static readonly bool[] Occupancies = [false, true];
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();
    public static TheoryData<HeroClass, int> Profiles => new()
    {
        { HeroClass.Mage, 3 }, { HeroClass.Mage, 5 }, { HeroClass.Mage, 8 },
        { HeroClass.Priest, 3 }, { HeroClass.Priest, 5 }, { HeroClass.Priest, 8 },
        { HeroClass.Guardian, 3 }, { HeroClass.Guardian, 5 }, { HeroClass.Guardian, 8 }
    };

    [Theory]
    [MemberData(nameof(Profiles))]
    public void Every_not_full_occupancy_accepts_into_discard_without_drawing(HeroClass hero, int capacity)
    {
        using var evidence = new Evidence("T01", hero, capacity);
        foreach (var seed in Seeds)
        {
            var fixture = Create(hero, capacity, seed); var room = fixture.Room; var player = fixture.Player;
            for (var occupancy = 0; occupancy < capacity; occupancy++)
            {
                var candidate = occupancy == 0 ? Assert.Single(player.MonsterPool.Pending) : Offer(player, $"controlled-fill-{occupancy}");
                var before = room.Capture(); var deck = player.Combat.Deck.Capture();
                var requestWire = ExecuteWire(room, player, candidate, true, null, $"accept-{occupancy}");
                Assert.Equal(deck.Hand, player.Combat.Deck.Hand); Assert.Equal(deck.Library, player.Combat.Deck.Library);
                Assert.Equal(deck.Discard.Append(candidate), player.Combat.Deck.Discard);
                Assert.Equal(occupancy + 1, player.MonsterPool.Active.Count);
                UnchangedOutsideDecision(before, room.Capture()); BasePreserved(fixture);
                evidence.Write(new { seed, hero = hero.ToString(), capacity, occupancy, fixture.Base, fixture.Kill, candidate,
                    before, after = room.Capture(), fixture_scope = "actual first kill; later server-issued controlled offers" }, requestWire);
            }
        }
        Assert.Equal(capacity * Seeds.Length, evidence.Count);
    }

    [Theory]
    [MemberData(nameof(Profiles))]
    public void Full_replacement_removes_only_selected_monster_from_each_pile(HeroClass hero, int capacity)
    {
        using var evidence = new Evidence("T02", hero, capacity);
        foreach (var seed in Seeds)
        foreach (var pile in Piles)
        {
            var fixture = Create(hero, capacity, seed); var room = fixture.Room; var player = fixture.Player;
            Fill(room, player, capacity);
            var replacement = player.MonsterPool.Active[0]; var candidate = Offer(player, "controlled-replacement");
            Relocate(player.Combat.Deck, replacement, pile); var before = room.Capture(); var deck = player.Combat.Deck.Capture();
            Assert.Throws<DomainValidationException>(() => room.DecideMonsterCard(player.PlayerId, candidate.InstanceId, true, null, "full-missing", room.Revision));
            var missingReplacementAfter = room.Capture(); Assert.Equivalent(before, missingReplacementAfter, strict: true);
            Assert.Throws<DomainValidationException>(() => room.DecideMonsterCard(player.PlayerId, candidate.InstanceId, true, fixture.Base[0].InstanceId, "base-replacement", room.Revision));
            var baseReplacementAfter = room.Capture(); Assert.Equivalent(before, baseReplacementAfter, strict: true);
            var requestWire = ExecuteWire(room, player, candidate, true, replacement.InstanceId, "replace-monster");
            Assert.Equal(deck.Hand.Where(c => c.InstanceId != replacement.InstanceId), player.Combat.Deck.Hand);
            Assert.Equal(deck.Library.Where(c => c.InstanceId != replacement.InstanceId), player.Combat.Deck.Library);
            Assert.Equal(deck.Discard.Where(c => c.InstanceId != replacement.InstanceId).Append(candidate), player.Combat.Deck.Discard);
            Assert.DoesNotContain(replacement, All(player.Combat.Deck)); Assert.Contains(candidate, player.Combat.Deck.Discard);
            Assert.Equal(capacity, player.MonsterPool.Active.Count);
            Assert.Equal(20 + capacity, All(player.Combat.Deck).Count());
            UnchangedOutsideDecision(before, room.Capture()); BasePreserved(fixture);
            evidence.Write(new { seed, hero = hero.ToString(), capacity, pile, fixture.Base, fixture.Kill, candidate, replacement,
                before, after = room.Capture(), missing_replacement_rejected = true, base_replacement_rejected = true,
                missing_replacement_after = missingReplacementAfter, base_replacement_after = baseReplacementAfter,
                fixture_scope = "controlled full pool and pile relocation" }, requestWire);
        }
        Assert.Equal(Seeds.Length * 3, evidence.Count);
    }

    [Theory]
    [MemberData(nameof(Profiles))]
    public void Skip_at_empty_and_full_occupancy_gives_no_compensation(HeroClass hero, int capacity)
    {
        using var evidence = new Evidence("T03", hero, capacity);
        foreach (var seed in Seeds)
        foreach (var full in Occupancies)
        {
            var fixture = Create(hero, capacity, seed); var room = fixture.Room; var player = fixture.Player;
            if (full) Fill(room, player, capacity);
            var candidate = full ? Offer(player, "controlled-skip") : Assert.Single(player.MonsterPool.Pending);
            var before = room.Capture(); var deck = player.Combat.Deck.Capture();
            var requestWire = ExecuteWire(room, player, candidate, false, null, "skip");
            Assert.Equivalent(deck, player.Combat.Deck.Capture(), strict: true);
            Assert.Equal(full ? capacity : 0, player.MonsterPool.Active.Count);
            UnchangedOutsideDecision(before, room.Capture()); BasePreserved(fixture);
            evidence.Write(new { seed, hero = hero.ToString(), capacity, full, fixture.Base, fixture.Kill, candidate,
                before, after = room.Capture(), fixture_scope = "no-compensation OFFLINE boundary" }, requestWire);
        }
        Assert.Equal(Seeds.Length * 2, evidence.Count);
    }

    private static byte[] ExecuteWire(BattleRoom room, RoomPlayerState player, CombatCardInstance candidate, bool accept, Guid? replacement, string request)
    {
        var command = new ClientCommand("monster.choose", request, room.Revision,
            new MonsterCardChooseCommandPayload(candidate.InstanceId, accept, replacement), room.RoomId);
        var wire = RealtimeProtobufCodec.EncodeClient(command); var decoded = RealtimeProtobufCodec.DecodeClient(wire);
        Assert.Equivalent(command, decoded, strict: true);
        var choice = Assert.IsType<MonsterCardChooseCommandPayload>(decoded.Payload);
        room.DecideMonsterCard(player.PlayerId, choice.CandidateId, choice.Accept, choice.ReplaceInstanceId, decoded.RequestId!, decoded.ExpectedRevision!.Value);
        return wire;
    }

    private static Fixture Create(HeroClass hero, int capacity, int seed)
    {
        var config = GameConfigCatalog.Current; Assert.False(config.Numerics.OptionalMonsterPool);
        var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", _ => "GUA" };
        var cards = Enumerable.Range(1, 13).Select(i => $"C{i:D2}").Concat(Enumerable.Range(1, 7).Select(i => $"{prefix}-{i:D2}")).ToArray();
        var owned = config.Cards.Where(c => c.Enabled && c.IsCodex && c.MonsterType is null).ToDictionary(c => c.CardId, c => new OwnedCard(c.CardId, c.HeroClass, (CardRarity)c.Rarity, 1, false));
        DeckRules.Validate(hero, cards, owned);
        var rules = config.Numerics with { OptionalMonsterPool = true, MonsterCapacity = capacity };
        Assert.Equal(config.Numerics, rules with { OptionalMonsterPool = false, MonsterCapacity = config.Numerics.MonsterCapacity });
        var room = new BattleRoom(Guid.NewGuid(), config.Version, Catalog, seed, rules);
        var playerId = Guid.NewGuid(); room.AddPlayer(new(playerId, hero, cards, null));
        var map = ChaosMapGenerator.Generate(seed, 1).Capture(); var cell = map.Cells.First(c => c.Layer == ChaosMapLayer.Outer && !c.IsBoss);
        var selected = cell with { MonsterGroupId = "O1", HasSpring = false };
        room.InitializeMap(ChaosMapState.Restore(map with { Cells = map.Cells.Select(c => c.Position == cell.Position ? selected : c).ToArray(), SpawnPositions = [cell.Position] }));
        var player = room.GetPlayer(playerId); var basis = All(player.Combat.Deck).ToArray(); var pve = player.Pve!;
        var target = Assert.Single(pve.Monsters); target.TakeDamage(target.Hp + target.Shield - 1);
        CombatCardInstance? card = null;
        for (var tick = 0; tick < 300 && card is null; tick++)
        {
            card = player.Combat.Deck.Hand.FirstOrDefault(c => CombatResolver.Resolve([Catalog.Get(c.CardId, c.Level, c.ElementOverride)], player.Combat, target.ElementalResistance).Damage > 0);
            if (card is null) room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch.AddMilliseconds((tick + 1) * 100));
        }
        Assert.NotNull(card); Assert.False(player.Combat.IsDead);
        var resolution = room.PlayCards(playerId, pve.BattleId, target.MonsterId, [card.InstanceId], room.Revision, DateTimeOffset.UnixEpoch);
        Assert.True(resolution.TargetDefeated); Assert.Equal(RoomPlayerPhase.Choice, player.Phase);
        var offered = Assert.Single(player.MonsterPool.Pending); Assert.Equal("M-FIREBAT", offered.CardId);
        Assert.Equal(20, All(player.Combat.Deck).Count());
        return new(room, player, basis, new { actor_id = playerId, battle_id = pve.BattleId, target_id = target.MonsterId, played = card, resolution, offered });
    }

    private static CombatCardInstance Offer(RoomPlayerState player, string source)
    {
        var card = new CombatCardInstance(Guid.NewGuid(), "M-FIREBAT");
        _ = Catalog.Get(card.CardId, card.Level); player.MonsterPool.Offer(source, card); return card;
    }
    private static void Fill(BattleRoom room, RoomPlayerState player, int capacity)
    {
        for (var i = 0; i < capacity; i++)
        {
            var card = i == 0 ? Assert.Single(player.MonsterPool.Pending) : Offer(player, $"controlled-fill-{i}");
            room.DecideMonsterCard(player.PlayerId, card.InstanceId, true, null, $"fill-{i}", room.Revision);
        }
    }
    private static void Relocate(CombatDeck deck, CombatCardInstance card, string pile)
    {
        var snapshot = deck.Capture();
        deck.Restore(snapshot with
        {
            Hand = snapshot.Hand.Where(c => c != card).Concat(pile == "Hand" ? [card] : Array.Empty<CombatCardInstance>()).ToArray(),
            Library = snapshot.Library.Where(c => c != card).Concat(pile == "Library" ? [card] : Array.Empty<CombatCardInstance>()).ToArray(),
            Discard = snapshot.Discard.Where(c => c != card).Concat(pile == "Discard" ? [card] : Array.Empty<CombatCardInstance>()).ToArray()
        });
        Assert.True(deck.Hand.Count <= CombatDeck.HandLimit);
    }
    private static void BasePreserved(Fixture fixture)
    {
        var all = All(fixture.Player.Combat.Deck).ToArray();
        Assert.All(fixture.Base, card => Assert.Contains(card, all)); Assert.Equal(all.Length, all.Select(c => c.InstanceId).Distinct().Count());
    }
    private static void UnchangedOutsideDecision(BattleRoomSnapshot before, BattleRoomSnapshot after)
    {
        Assert.Equal(before.Revision + 1, after.Revision);
        var old = Assert.Single(before.Players); var current = Assert.Single(after.Players);
        Assert.Equal(old.Combat.Deck.DrawCharge, current.Combat.Deck.DrawCharge);
        Assert.Equivalent(before, after with { Revision = before.Revision, Players = [current with
            { Combat = current.Combat with { Deck = old.Combat.Deck }, MonsterPool = old.MonsterPool }] }, strict: true);
        var pool = current.MonsterPool!; var previous = old.MonsterPool!;
        Assert.Equal(previous.GrantedSources, pool.GrantedSources);
        Assert.Equal(previous.Receipts.Count + 1, pool.Receipts.Count); Assert.Equal(previous.Pending.Count - 1, pool.Pending.Count);
    }
    private static IEnumerable<CombatCardInstance> All(CombatDeck deck) => deck.Hand.Concat(deck.Library).Concat(deck.Discard);
    private sealed record Fixture(BattleRoom Room, RoomPlayerState Player, CombatCardInstance[] Base, object Kill);
    private sealed class Evidence : IDisposable
    {
        private readonly GZipStream? _gzip;
        private readonly string _case;
        private readonly string? _source = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_SOURCE_SHA");
        public int Count { get; private set; }
        public Evidence(string name, HeroClass hero, int capacity)
        {
            _case = "PR13-B09.2-" + name;
            var directory = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_POOL_CAPACITY_WIRE_EVIDENCE");
            if (string.IsNullOrWhiteSpace(directory)) return;
            Directory.CreateDirectory(directory);
            _gzip = new(new FileStream(Path.Combine(directory, $"{_case}-{hero}-{capacity}.jsonl.gz"), FileMode.CreateNew), CompressionLevel.Fastest);
        }
        public void Write(object actual, byte[] requestWire)
        {
            var document = JsonSerializer.SerializeToElement(actual);
            var before = document.GetProperty("before").Deserialize<BattleRoomSnapshot>()!;
            var after = document.GetProperty("after").Deserialize<BattleRoomSnapshot>()!;
            var beforeWire = Project(before); var afterWire = Project(after);
            var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { case_id = _case, source_sha = _source, actual,
                request_wire = Convert.ToBase64String(requestWire), request_wire_bytes = requestWire.Length,
                before_wire = Convert.ToBase64String(beforeWire), before_wire_bytes = beforeWire.Length,
                after_wire = Convert.ToBase64String(afterWire), after_wire_bytes = afterWire.Length,
                projection_scope = "original native room snapshots restored and projected; OFFLINE only" }) + "\n");
            _gzip?.Write(bytes); Count++;
        }
        private static byte[] Project(BattleRoomSnapshot state)
        {
            var room = BattleRoom.Restore(state, Catalog, 0); var actor = state.Players.Single().PlayerId;
            var payload = RoomSnapshotProjection.Build(new GetRoomClientStateCommand(actor).Execute(room), actor, null, DateTimeOffset.UnixEpoch);
            var message = new ServerEvent("room.snapshot", "pool-capacity", payload, "pool-capacity-event", 1, DateTimeOffset.UnixEpoch);
            var wire = RealtimeProtobufCodec.EncodeServer(message); var decoded = RealtimeProtobufCodec.DecodeServer(wire);
            Assert.Equal(wire, RealtimeProtobufCodec.EncodeServer(decoded));
            var roundtrip = Assert.IsType<RoomSnapshotEventPayload>(decoded.Payload);
            Assert.Equal(payload.Player.Hand, roundtrip.Player.Hand);
            Assert.Equal(payload.Player.LibraryCount, roundtrip.Player.LibraryCount); Assert.Equal(payload.Player.DiscardCount, roundtrip.Player.DiscardCount);
            Assert.Equivalent(payload.Player.MonsterPool, roundtrip.Player.MonsterPool, strict: true);
            Assert.Equal(payload.AllowedActions, roundtrip.AllowedActions); Assert.True(wire.Length <= 16 * 1024);
            return wire;
        }
        public void Dispose() => _gzip?.Dispose();
    }
}
