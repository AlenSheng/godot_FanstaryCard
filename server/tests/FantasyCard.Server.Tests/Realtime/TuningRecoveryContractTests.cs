using System.Globalization;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Realtime;

// Controlled legal-deck boundaries. These are actual room/router/protocol
// executions, not representative expeditions, capacity or balance estimates.
public sealed class TuningRecoveryContractTests
{
    private static readonly DateTimeOffset Now = DateTimeOffset.UnixEpoch.AddSeconds(10);
    private static readonly JsonSerializerOptions Json = new() { DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull };
    private static readonly string[] Common = ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11", "C15", "ET-FIRE-G", "ET-WATER-G"];
    private static readonly (string Case, string Name, string[] Cards)[] Recipes =
    [
        ("T01", "tuning-first", ["ET-FIRE-G", "C01", "C06"]),
        ("T01", "water-first", ["C06", "ET-FIRE-G", "C01"]),
        ("T01", "direct-before-tuning", ["C11", "ET-FIRE-G", "C01", "C06"]),
        ("T02", "same-core-no-counter", ["ET-FIRE-G", "C01", "C02"]),
        ("T02", "same-core-with-counter", ["ET-FIRE-G", "C01", "C02", "C06"]),
        ("T02", "non-core-tuning", ["C01", "C02", "ET-WATER-G"]),
        ("T03", "conflict-only", ["C01", "C06"]),
        ("T03", "ordinary-plus-conflict", ["C01", "C06", "C15"])
    ];

    [Theory]
    [InlineData("T01", HeroClass.Mage)]
    [InlineData("T01", HeroClass.Priest)]
    [InlineData("T01", HeroClass.Guardian)]
    [InlineData("T02", HeroClass.Mage)]
    [InlineData("T02", HeroClass.Priest)]
    [InlineData("T02", HeroClass.Guardian)]
    [InlineData("T03", HeroClass.Mage)]
    [InlineData("T03", HeroClass.Priest)]
    [InlineData("T03", HeroClass.Guardian)]
    public async Task Ordered_tuning_and_separate_recovery_match_actual_room_and_wire(string caseName, HeroClass hero)
    {
        var directory = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_TUNING_EVIDENCE");
        var source = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_SOURCE_SHA");
        if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);
        using var file = string.IsNullOrWhiteSpace(directory) ? null : new FileStream(Path.Combine(directory, $"PR13-B08.3-{caseName}-{hero}.jsonl.gz"), FileMode.CreateNew);
        using var gzip = file is null ? null : new GZipStream(file, CompressionLevel.Fastest);
        using var digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        var count = 0; long bytes = 0;
        foreach (var seed in new[] { 410001, 411001, 412001 })
        foreach (var group in new[] { "O1", "O6", "E1", "BOSS" })
        for (var weapon = 0; weapon <= 5; weapon++)
        foreach (var health in new[] { "one", "quarter", "half", "full" })
        foreach (var vitality in new[] { false, true })
        foreach (var recipe in Recipes.Where(r => r.Case == caseName))
        {
            var record = await Execute(hero, weapon, health, vitality, group, seed, recipe.Name, recipe.Cards, caseName, source);
            var raw = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(record, Json) + "\n");
            bytes += raw.Length;
            Assert.True(bytes <= 32 * 1024 * 1024, "Per-file raw evidence budget exceeded.");
            digest.AppendData(raw); gzip?.Write(raw); count++;
        }
        Assert.Equal(caseName == "T03" ? 1152 : 1728, count);
        if (!string.IsNullOrWhiteSpace(directory))
            File.WriteAllText(Path.Combine(directory, $"PR13-B08.3-{caseName}-{hero}.summary.json"), JsonSerializer.Serialize(new
            { passed = true, source_sha = source, case_id = "PR13-B08.3-" + caseName, hero = hero.ToString(), rows = count, raw_bytes = bytes, raw_sha256 = Convert.ToHexStringLower(digest.GetHashAndReset()) }));
    }

    private static async Task<object> Execute(HeroClass hero, int weapon, string health, bool vitality, string group, int seed, string recipe, string[] selectedCards, string caseName, string? source)
    {
        var config = GameConfigCatalog.Current; var catalog = CombatCardCatalog.CreatePrototype();
        var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", _ => "GUA" };
        var deck = Common.Concat(Enumerable.Range(1, 6).Select(i => $"{prefix}-{i:D2}")).ToArray();
        var owned = config.Cards.Where(c => c.Enabled && c.IsCodex && c.MonsterType is null)
            .ToDictionary(c => c.CardId, c => new OwnedCard(c.CardId, c.HeroClass, (CardRarity)c.Rarity, 1, false));
        DeckRules.Validate(hero, deck, owned);
        Assert.Equal(20, deck.Distinct().Count());
        CombatEquipmentItem[] equipmentItems = vitality ? new[] { "Head", "Chest", "Hands" }.Select(slot => new CombatEquipmentItem(Guid.NewGuid(), slot, "Purple", 0, CardElement.Fire, "Vitality", null)).ToArray() : [];
        var equipment = EquipmentCombatRules.Calculate(equipmentItems);
        var profile = PlayerProfile.Create(Guid.NewGuid(), "Contract boundary", Now);
        var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, seed, config.Numerics);
        room.AddPlayer(new(profile.UserId, hero, deck, null, WeaponLevel: weapon, Equipment: equipment));
        var map = ChaosMapGenerator.Generate(seed, 1).Capture(); var cell = map.Cells.First(c => c.Layer == ChaosMapLayer.Outer && !c.IsBoss);
        room.InitializeMap(ChaosMapState.Restore(map with { Cells = map.Cells.Select(c => c.Position == cell.Position ? c with { MonsterGroupId = group, IsBoss = group == "BOSS", HasSpring = false } : c).ToArray(), SpawnPositions = [cell.Position] }));
        var state = room.Capture(); var playerState = state.Players.Single(); var combat = playerState.Combat;
        var pool = combat.Deck.Hand.Concat(combat.Deck.Library).Concat(combat.Deck.Discard).ToArray();
        Assert.Equal(20, pool.Select(c => c.InstanceId).Distinct().Count());
        var selected = selectedCards.Select(id => pool.Single(c => c.CardId == id)).ToArray();
        var hand = selected.Concat(pool.Except(selected).Take(5 - selected.Length)).ToArray();
        combat = combat with { Hp = health switch { "one" => 1, "quarter" => combat.MaximumHp / 4, "half" => combat.MaximumHp / 2, _ => combat.MaximumHp }, Shield = 0,
            Deck = new(hand, pool.Except(hand).ToArray(), [], 0) };
        var pve = playerState.Pve! with { Monsters = playerState.Pve!.Monsters.Select(m => m with { MaximumHp = 100000, Hp = 100000, Shield = 0 }).ToArray() };
        room = BattleRoom.Restore(state with { Players = [playerState with { Combat = combat, Pve = pve }] }, catalog, seed);
        var player = room.GetPlayer(profile.UserId); var target = player.Pve!.Monsters[0]; player.Pve.SelectTarget(target.MonsterId);
        var cards = selected.Select(c => catalog.Get(c.CardId, 0)).ToArray(); var oracle = Oracle(cards, player.Combat, target.ElementalResistance);
        var draft = CombatResolver.Resolve(cards, player.Combat, target.ElementalResistance);
        Assert.Equal((oracle.Core, oracle.R, oracle.P, oracle.K, oracle.D, oracle.Damage, oracle.OrdinaryHeal + oracle.ConflictHeal),
            (draft.CoreElement, draft.CoreCount, draft.ConflictPairCount, draft.ResonanceMultiplier, draft.ConflictCancellation, draft.Damage, draft.Heal));
        var before = JsonSerializer.Serialize(room.Capture()); var ids = selected.Select(c => c.InstanceId).ToArray();
        var command = new ClientCommand("combat.preview", Guid.NewGuid().ToString("N"), room.Revision, new BattlePlayCardsCommandPayload(player.Pve.BattleId, target.MonsterId, ids));
        var commandWire = RealtimeProtobufCodec.EncodeClient(command); var decoded = RealtimeProtobufCodec.DecodeClient(commandWire);
        Assert.Equal(ids, Assert.IsType<BattlePlayCardsCommandPayload>(decoded.Payload).CardInstanceIds);
        await using var registry = new RoomRegistry(new FrozenClock()); registry.Register(room, Guid.NewGuid(), startTicker: false);
        var clock = new FrozenClock(); var router = new RealtimeCommandRouter(new RealtimeEventStore(clock), clock, registry);
        var response = Assert.Single(await router.RouteAsync(profile, decoded, "tuning-contract", TestContext.Current.CancellationToken));
        Assert.Equal("combat.previewed", response.Type); Assert.Equal(before, JsonSerializer.Serialize(room.Capture()));
        var responseWire = RealtimeProtobufCodec.EncodeServer(response); var roundtrip = RealtimeProtobufCodec.DecodeServer(responseWire);
        Assert.Equivalent(response, roundtrip, strict: true);
        var preview = Assert.IsType<BattleComboResolvedEventPayload>(roundtrip.Payload); Assert.Equal(ids, preview.CardInstanceIds);
        var actual = room.PlayCards(profile.UserId, player.Pve.BattleId, target.MonsterId, ids, room.Revision, Now);
        Assert.Equal((actual.CoreElement?.ToString(), actual.CoreCount, actual.Damage, actual.HpDamage, actual.ShieldDamage, actual.Heal, actual.ShieldGain),
            (preview.CoreElement, preview.CoreCount, preview.Damage, preview.HpDamage, preview.ShieldDamage, preview.Heal, preview.ShieldGain));
        Assert.Equal(actual.ResonanceMultiplier, double.Parse(preview.ResonanceMultiplier!, CultureInfo.InvariantCulture));
        Assert.Equal(actual.ConflictPairCount, preview.ConflictPairCount);
        Assert.Equal(actual.ConflictCancellation, double.Parse(preview.ConflictCancellation!, CultureInfo.InvariantCulture));
        Assert.Equal(20, player.Combat.Deck.Hand.Concat(player.Combat.Deck.Capture().Library).Concat(player.Combat.Deck.Capture().Discard).Select(c => c.InstanceId).Distinct().Count());
        var after = JsonSerializer.Serialize(room.Capture());
        var bonuses = new Dictionary<string,double> { ["vitality_heal"] = equipment.VitalityHealBonus, ["vitality_overcap"] = equipment.VitalityOvercapBonus };
        foreach (var element in Enum.GetValues<CardElement>()) bonuses["damage_" + element] = equipment.DamageBonus(element);
        var intent = target.Intents[target.IntentIndex % target.Intents.Count];
        var input = new { room_id = room.RoomId, room_revision = command.ExpectedRevision, allowed_actions = new[] { "battle.play_cards" },
            player = new { player_id = profile.UserId, hero_class = hero.ToString(), weapon_level = weapon, combat = new { hp = combat.Hp, shield = combat.Shield, maximum_hp = combat.MaximumHp },
                hand = hand.Select(c => new { instance_id = c.InstanceId, card_id = c.CardId, level = 0 }),
                battle_status = new { combo = 0, core_element = "", bonuses = bonuses.Select(v => new { key = v.Key, value = v.Value }) },
                numerical_state = new { fenxian_policy = combat.FenxianPolicy.ToString(), guardian_policy = combat.GuardianPolicy.ToString(), guardian_remainder_tenths = 0 } },
            pve = new { battle_id = pve.BattleId, current_target_id = target.MonsterId, monsters = new[] { new { monster_id = target.MonsterId, hp = 100000, shield = 0, maximum_hp = 100000, intent_element = intent.Element.ToString(), boss_phase = target.BossPhase } } } };
        return new { schema = "actual_tuning_recovery_v1", source_sha = source, case_id = "PR13-B08.3-" + caseName, hero = hero.ToString(), seed, group, weapon_level = weapon, hp_boundary = health, equipment_profile = vitality ? "VitalitySet" : "Empty", equipment_items = equipmentItems, equipment, recipe,
            deck, selected_cards = selectedCards, ids, input_room = input, command_wire = Convert.ToBase64String(commandWire), response_wire = Convert.ToBase64String(responseWire), oracle, draft, actual,
            requested_heal = draft.Heal, effective_heal = actual.Heal, heal_overflow = draft.Heal - actual.Heal,
            before_state_sha256 = Hash(before), after_state_sha256 = Hash(after),
            before_state = seed == 410001 && group == "O1" && health == "quarter" && weapon is 0 or 5 ? before : null,
            after_state = seed == 410001 && group == "O1" && health == "quarter" && weapon is 0 or 5 ? after : null,
            expected = new { damage = actual.Damage, hp_damage = actual.HpDamage, shield_damage = actual.ShieldDamage, heal = actual.Heal, shield_gain = actual.ShieldGain, core_element = actual.CoreElement?.ToString() ?? "", core_count = actual.CoreCount, resonance_multiplier = actual.ResonanceMultiplier, conflict_pair_count = actual.ConflictPairCount, conflict_cancellation = actual.ConflictCancellation,
                draw_charge = actual.DrawCharge, immediate_draw = actual.ImmediateDraw, health_cost = actual.HealthCost, stun_seconds = actual.StunSeconds, draw_block_seconds = actual.DrawBlockSeconds, draw_block_speed_seconds = actual.DrawBlockSpeedSeconds },
            passed = true, scope = "Controlled current room boundary with owned legal twenty-card pool; not LIVE or representative expedition" };
    }

    private static ContractOracle Oracle(CombatCardDefinition[] cards, PlayerCombatState attacker, Func<CardElement,double> resistance)
    {
        var eligible = cards.Where(c => c.Effect.ElementalDamage > 0 && c.Effect.Element != CardElement.None && c.Effect.SecondaryElementalDamage == 0).ToArray();
        var core = eligible[0].Effect.Element; var r = eligible.Count(c => c.Effect.Element == core);
        // Frozen recipes use only Fire/Water: their current conflict is explicit,
        // independent of the resolver's private conflict set.
        Assert.All(eligible, c => Assert.Contains(c.Effect.Element, new[] { CardElement.Fire, CardElement.Water }));
        var p = eligible.Count(c => c.Effect.Element != core && !c.Effect.IsElementTuning);
        var b = cards.Any(c => c.Effect.ResonanceBonus > 0) ? 1 : 0;
        var k = 1 + .20 * Math.Max(0, r - 1 + b - p); var d = p == 0 ? 0 : Math.Min(.80, .20 * p + cards.Max(c => c.Effect.ConflictCancelBonus));
        var shared = (1 + attacker.Equipment.DamageBonus(core)) * (1 - resistance(core));
        var damage = eligible.Sum(c => (int)Math.Floor(c.Effect.ElementalDamage * shared * (c.Effect.Element == core ? k : c.Effect.IsElementTuning ? 1 : 1 - d))) + cards.Sum(c => c.Effect.DirectDamage);
        var e0 = eligible.Where(c => c.Effect.Element == core && !c.Effect.IsElementTuning).Sum(c => c.Effect.ElementalDamage) * shared * k;
        var coefficient = Math.Max(.50, cards.Max(c => c.Effect.ConflictHealCoefficient));
        var rawConflict = p == 0 ? 0 : (int)Math.Floor(e0 * d * coefficient) + 2 * p;
        var conflict = (int)Math.Floor(rawConflict * (1 + attacker.Equipment.VitalityHealBonus));
        var ordinary = cards.Sum(c => c.Effect.Heal) * (1 + .25 * p);
        var priest = attacker.HeroClass == HeroClass.Priest;
        var missing = Math.Clamp(1 - (double)attacker.Hp / attacker.MaximumHp, 0, 1);
        var weapon = new[] { .06, .08, .10, .11, .13, .14 }[attacker.WeaponLevel];
        if (priest) { ordinary = Math.Floor(ordinary * (1 + .80 * missing)); ordinary = Math.Floor(ordinary * (1 + weapon)); }
        ordinary = Math.Floor(ordinary * (1 + attacker.Equipment.VitalityHealBonus));
        var wrongConflict = priest ? (int)Math.Floor(Math.Floor(Math.Floor(rawConflict * (1 + .80 * missing)) * (1 + weapon)) * (1 + attacker.Equipment.VitalityHealBonus)) : conflict;
        return new(core, r, p, b, k, d, shared, e0, rawConflict, (int)ordinary, conflict, damage, wrongConflict);
    }

    private static string Hash(string raw) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(raw)));
    private sealed record ContractOracle(CardElement Core, int R, int P, int B, double K, double D, double SharedMultiplier, double E0, int RawConflictHeal, int OrdinaryHeal, int ConflictHeal, int Damage, int IncorrectPriestConflictHeal);
    private sealed class FrozenClock : TimeProvider { public override DateTimeOffset GetUtcNow() => Now; }
}
