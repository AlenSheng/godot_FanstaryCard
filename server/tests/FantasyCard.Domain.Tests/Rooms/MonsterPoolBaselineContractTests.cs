using System.IO.Compression;
using System.Text;
using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

// Legal base cards and actual finishing PlayCards. Reduced target HP is a
// declared OFFLINE boundary; the recycle control is not expedition benefit.
public sealed class MonsterPoolBaselineContractTests
{
    private static readonly int[] Seeds = [450001, 451001, 452001];
    private static readonly string[] Groups = ["O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8", "M1", "M2", "M3", "M4", "M5", "E1", "E2", "E3", "E4", "E5", "E6", "BOSS"];
    private static readonly IReadOnlyDictionary<string, string> Species = new Dictionary<string, string>
    {
        ["fire-bat"] = "FireBat", ["thorn-mite"] = "ThornMite", ["murk-snail"] = "MudHydra",
        ["sand-lizard"] = "SandLizard", ["rust-rat"] = "RustRat", ["box-spirit"] = "BoxSpirit",
        ["metal-guard"] = "GoldGuard", ["fire-herald"] = "FireReaver", ["marsh-mother"] = "SwampMother",
        ["stone-guard"] = "StoneGuard", ["thorn-guard"] = "ThornGuard", ["annihilation-core"] = "VoidCore"
    };
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();

    [Theory]
    [InlineData(HeroClass.Mage)]
    [InlineData(HeroClass.Priest)]
    [InlineData(HeroClass.Guardian)]
    public void Current_room_policy_stays_automatic_after_legal_kills(HeroClass hero)
    {
        using var evidence = new Evidence("T01", hero);
        Assert.False(GameConfigCatalog.Current.Numerics.OptionalMonsterPool);
        foreach (var seed in Seeds)
        foreach (var scenario in Scenarios())
        {
            var room = Create(hero, seed, scenario.Group, scenario.Element); var player = room.GetPlayer(room.Capture().Players.Single().PlayerId);
            var original = All(player.Combat.Deck).ToArray(); var kills = Finish(room, player);
            Assert.False(room.Numerics.OptionalMonsterPool); Assert.Empty(player.MonsterPool.Active); Assert.Empty(player.MonsterPool.Pending);
            Assert.Equal(20 + kills.Count, All(player.Combat.Deck).Count());
            Assert.All(original, card => Assert.Contains(card, All(player.Combat.Deck)));
            var before = JsonSerializer.Serialize(room.Capture());
            Assert.Throws<DomainValidationException>(() => room.DecideMonsterCard(player.PlayerId, Guid.NewGuid(), true, null, "disabled-choice", room.Revision));
            Assert.Equal(before, JsonSerializer.Serialize(room.Capture()));
            evidence.Write(new { seed, hero = hero.ToString(), group = scenario.Group, box_element = scenario.Element?.ToString(), effective_optional_policy = room.Numerics.OptionalMonsterPool,
                before_base = original, after_state = room.Capture(), actual_kills = kills, disabled_choice_rejected_without_mutation = true });
        }
        Assert.Equal(78, evidence.Count);
    }

    [Theory]
    [InlineData(HeroClass.Mage)]
    [InlineData(HeroClass.Priest)]
    [InlineData(HeroClass.Guardian)]
    public void Every_actual_generated_monster_kill_has_one_legal_card_source(HeroClass hero)
    {
        using var evidence = new Evidence("T02", hero);
        foreach (var seed in Seeds)
        foreach (var scenario in Scenarios())
        {
            var room = Create(hero, seed, scenario.Group, scenario.Element); var player = room.GetPlayer(room.Capture().Players.Single().PlayerId);
            foreach (var kill in Finish(room, player)) evidence.Write(new { seed, hero = hero.ToString(), group = scenario.Group, box_element = scenario.Element?.ToString(), actual = kill });
            var snapshot = room.Capture(); var restored = BattleRoom.Restore(snapshot, Catalog, 999);
            Assert.Equivalent(snapshot, restored.Capture(), strict: true);
        }
        Assert.True(evidence.Count >= 78);
    }

    [Theory]
    [InlineData(HeroClass.Mage)]
    [InlineData(HeroClass.Priest)]
    [InlineData(HeroClass.Guardian)]
    public void Automatically_expanded_legal_pool_keeps_printed_power_separate_from_key_arrival(HeroClass hero)
    {
        using var evidence = new Evidence("T03", hero);
        foreach (var roomSeed in Seeds)
        {
            var room = Create(hero, roomSeed, "O6", null); var player = room.GetPlayer(room.Capture().Players.Single().PlayerId);
            var basis = All(player.Combat.Deck).ToArray(); var kills = Finish(room, player); var expanded = All(player.Combat.Deck).ToArray();
            Assert.Equal(20, basis.Length); Assert.Equal(22, expanded.Length); Assert.Equal(2, kills.Count);
            var basePower = PrintedDamage(basis); var expandedPower = PrintedDamage(expanded); Assert.True(expandedPower > basePower);
            long baseKeys = 0, expandedKeys = 0;
            foreach (var start in Seeds)
            for (var seed = start; seed < start + 1000; seed++)
            {
                var a = Arrival(basis, seed); var b = Arrival(expanded, seed); baseKeys += a.Key; expandedKeys += b.Key;
                evidence.Write(new { room_seed = roomSeed, seed, hero = hero.ToString(), baseline_pool = basis.Length, expanded_pool = expanded.Length,
                    baseline_printed_damage = basePower, expanded_printed_damage = expandedPower, baseline_key_ordinal = a.Key, expanded_key_ordinal = b.Key,
                    baseline_second_fire_ordinal = a.SecondFire, expanded_second_fire_ordinal = b.SecondFire, kill_sources = kills,
                    scope = "native legal-pool recycle control; not natural encounter benefit or full expedition", no_balance_candidate = true });
            }
            Assert.True(expandedKeys > baseKeys); // This fixed controlled counterexample does not declare a population benefit.
        }
        Assert.Equal(9000, evidence.Count);
    }

    private static IEnumerable<(string Group, CardElement? Element)> Scenarios()
    {
        foreach (var group in Groups) yield return (group, null);
        foreach (var element in Enum.GetValues<CardElement>()) yield return ("BOX", element);
    }
    private static BattleRoom Create(HeroClass hero, int seed, string group, CardElement? element)
    {
        var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", _ => "GUA" };
        var cards = Enumerable.Range(1, 13).Select(i => $"C{i:D2}").Concat(Enumerable.Range(1, 7).Select(i => $"{prefix}-{i:D2}")).ToArray();
        var config = GameConfigCatalog.Current;
        var owned = config.Cards.Where(c => c.Enabled && c.IsCodex && c.MonsterType is null).ToDictionary(c => c.CardId, c => new OwnedCard(c.CardId, c.HeroClass, (CardRarity)c.Rarity, 1, false));
        DeckRules.Validate(hero, cards, owned);
        var room = new BattleRoom(Guid.NewGuid(), config.Version, Catalog, seed, config.Numerics);
        room.AddPlayer(new(Guid.NewGuid(), hero, cards, null));
        var map = ChaosMapGenerator.Generate(seed, 1).Capture();
        var layer = group == "BOSS" ? ChaosMapLayer.Core : group.StartsWith('E') || group.StartsWith('M') ? ChaosMapLayer.Middle : ChaosMapLayer.Outer;
        var cell = group == "BOSS" ? map.Cells.Single(c => c.IsBoss) : map.Cells.First(c => c.Layer == layer && !c.IsBoss);
        var selected = cell with { MonsterGroupId = group, TreasureElement = element, HasSpring = false, IsBoss = group == "BOSS" };
        room.InitializeMap(ChaosMapState.Restore(map with { Cells = map.Cells.Select(c => c.Position == cell.Position ? selected : c).ToArray(), SpawnPositions = [cell.Position] }));
        return room;
    }
    private static List<object> Finish(BattleRoom room, RoomPlayerState player)
    {
        var kills = new List<object>(); var pve = player.Pve!;
        // The prepared boundary leaves the original species, intents, battle and
        // legal owned instances intact. Only the final remaining HP is controlled.
        foreach (var monster in pve.Monsters) monster.TakeDamage(monster.Hp + monster.Shield - 1);
        foreach (var monster in pve.Monsters)
        {
            CombatCardInstance? card = null;
            for (var tick = 0; tick < 300 && card is null; tick++)
            {
                card = player.Combat.Deck.Hand.FirstOrDefault(c => CombatResolver.Resolve([Catalog.Get(c.CardId, c.Level, c.ElementOverride)], player.Combat, monster.ElementalResistance).Damage > 0);
                if (card is null) room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch.AddMilliseconds((tick + 1) * 100));
            }
            Assert.NotNull(card); Assert.False(player.Combat.IsDead);
            var before = All(player.Combat.Deck).ToArray(); var source = monster.MonsterId;
            var species = source.EndsWith("-a", StringComparison.Ordinal) || source.EndsWith("-b", StringComparison.Ordinal) ? source[..^2] : source;
            var expected = GameConfigCatalog.Current.Cards.Single(c => c.MonsterType == Species[species]);
            var result = room.PlayCards(player.PlayerId, pve.BattleId, source, [card.InstanceId], room.Revision, DateTimeOffset.UnixEpoch);
            Assert.True(result.TargetDefeated); Assert.True(monster.IsDead);
            var after = All(player.Combat.Deck).ToArray(); var granted = Assert.Single(after.Where(c => before.All(old => old.InstanceId != c.InstanceId)));
            Assert.Equal(expected.CardId, granted.CardId); Assert.Equal(0, granted.Level); Assert.Contains(granted, player.Combat.Deck.Discard);
            Assert.Equal(species == "box-spirit" ? monster.Intents[0].Element : (CardElement?)null, granted.ElementOverride);
            Assert.All(before, old => Assert.Contains(old, after)); Assert.Equal(before.Length + 1, after.Length);
            Assert.Equal(after.Length, after.Select(c => c.InstanceId).Distinct().Count());
            kills.Add(new { actor_id = player.PlayerId, battle_id = pve.BattleId, source_monster_id = source, monster_type = expected.MonsterType,
                actual_played = card, granted, before_pool = before.Length, after_pool = after.Length, after_discard = player.Combat.Deck.Discard.ToArray(), actual_resolution = result });
        }
        return kills;
    }
    private static IEnumerable<CombatCardInstance> All(CombatDeck deck) => deck.Hand.Concat(deck.Library).Concat(deck.Discard);
    private static int PrintedDamage(CombatCardInstance[] cards) => cards.Sum(c =>
    {
        var effect = Catalog.Get(c.CardId, c.Level, c.ElementOverride).Effect;
        return effect.ElementalDamage + effect.SecondaryElementalDamage + effect.DirectDamage;
    });
    private static (int Key, int SecondFire) Arrival(CombatCardInstance[] cards, int seed)
    {
        var deck = CombatDeck.Create(cards.Select(c => c.CardId).ToArray(), new Random(1));
        deck.Restore(new([], [], cards, 0)); var random = new Random(seed); var key = 0; var fires = 0; var secondFire = 0;
        for (var ordinal = 1; ordinal <= cards.Length; ordinal++)
        {
            deck.DrawImmediate(1, random); var card = Assert.Single(deck.Hand);
            if (card.CardId == "C01") key = ordinal;
            if (Catalog.Get(card.CardId, card.Level, card.ElementOverride).Effect.Element == CardElement.Fire && ++fires == 2) secondFire = ordinal;
            deck.DiscardPlayed([card]);
        }
        Assert.True(key > 0 && secondFire > 0); return (key, secondFire);
    }
    private sealed class Evidence : IDisposable
    {
        private readonly GZipStream? _gzip;
        private readonly string _case;
        private readonly string? _source = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_SOURCE_SHA");
        public int Count { get; private set; }
        public Evidence(string name, HeroClass hero)
        {
            _case = "PR13-B09.1-" + name;
            var directory = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_POOL_EVIDENCE");
            if (string.IsNullOrWhiteSpace(directory)) return;
            Directory.CreateDirectory(directory); _gzip = new(new FileStream(Path.Combine(directory, $"{_case}-{hero}.jsonl.gz"), FileMode.CreateNew), CompressionLevel.Fastest);
        }
        public void Write(object actual)
        {
            var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { case_id = _case, source_sha = _source, actual }) + "\n"); _gzip?.Write(bytes); Count++;
        }
        public void Dispose() => _gzip?.Dispose();
    }
}
