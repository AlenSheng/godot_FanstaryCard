using System.IO.Compression;
using System.Text;
using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Combat;

// Legal equipment and real advancing combat-state boundaries. These are OFFLINE
// witnesses, not complete encounters, balance estimates or render acceptance.
public sealed class CapEffectiveContractTests
{
    private static readonly int[] Seeds = [430001, 431001, 432001];
    private static readonly string[] Slots = ["Head", "Chest", "Hands", "Legs", "Feet"];
    private static readonly string[] Common = ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11", "C15", "ET-FIRE-G", "ET-WATER-G"];
    private static readonly string[] ShieldPositions = ["empty", "half", "full"];
    private static readonly int[] ShieldRequests = [0, 9, 100];
    private static readonly bool[] Upgrades = [false, true];

    [Theory]
    [InlineData(HeroClass.Mage)]
    [InlineData(HeroClass.Priest)]
    [InlineData(HeroClass.Guardian)]
    public void Legal_equipment_resistance_above_sixty_percent_has_zero_marginal_gain(HeroClass hero)
    {
        using var evidence = new Evidence("T01", hero);
        foreach (var seed in Seeds)
        foreach (var element in Enum.GetValues<CardElement>().Where(e => e != CardElement.None))
        for (var level = 0; level <= 5; level++)
        {
            var before = Items(seed, element, level, false); var after = Items(seed, element, level, true);
            var a = EquipmentCombatRules.Calculate(before); var b = EquipmentCombatRules.Calculate(after);
            var rawA = RawResistance(before); var rawB = RawResistance(after);
            Assert.Equal(Math.Min(.60, rawA), a.Resistance(element), 9);
            Assert.Equal(Math.Min(.60, rawB), b.Resistance(element), 9);
            var stateA = State(hero, seed, a); var stateB = State(hero, seed, b);
            Assert.Equal(a.Resistance(element), stateA.ElementalResistance(element), 9);
            Assert.Equal(b.Resistance(element), stateB.ElementalResistance(element), 9);
            if (rawA >= .60) Assert.Equal(0, stateB.ElementalResistance(element) - stateA.ElementalResistance(element), 9);
            evidence.Write(new { seed, hero = hero.ToString(), element = element.ToString(), level, before = Display(before), after = Display(after), raw_before = rawA, raw_after = rawB, effective_before = a.Resistance(element), effective_after = b.Resistance(element), capped_before = Math.Max(0, rawA - .6), capped_after = Math.Max(0, rawB - .6), marginal_effective = b.Resistance(element) - a.Resistance(element) });
        }
        Assert.Equal(90, evidence.Count);
    }

    [Theory]
    [InlineData(HeroClass.Mage)]
    [InlineData(HeroClass.Priest)]
    [InlineData(HeroClass.Guardian)]
    public void Equipment_clamp_card_speed_and_post_clamp_conversion_keep_separate_stages(HeroClass hero)
    {
        using var evidence = new Evidence("T02", hero);
        foreach (var seed in Seeds)
        for (var level = 0; level <= 5; level++)
        foreach (var upgraded in Upgrades)
        {
            var items = Items(seed, CardElement.Fire, level, upgraded); var profile = EquipmentCombatRules.Calculate(items); var state = State(hero, seed, profile);
            var raw = 4 * (1 + profile.DrawIntervalModifier); var interval = Math.Clamp(raw, 1.8, 6);
            Assert.Equal(interval, state.DrawIntervalSeconds, 9);
            state.Advance(TimeSpan.FromSeconds(.1), drawEnabled: true); var normalCharge = state.Deck.DrawCharge;
            Assert.Equal(.1 / interval, normalCharge, 9);
            state.ApplyDrawSpeed(TimeSpan.FromSeconds(.2), -.25); var cardInterval = Math.Clamp(raw * .75, 1.8, 6);
            Assert.Equal(cardInterval, state.DrawIntervalSeconds, 9);
            state.Advance(TimeSpan.FromSeconds(.1), drawEnabled: true); var afterCard = state.Deck.DrawCharge;
            Assert.Equal(normalCharge + .1 / cardInterval, afterCard, 9);
            state.ApplyDrawBlockSpeed(TimeSpan.FromSeconds(.15));
            Assert.Equal(cardInterval / 2, state.DrawIntervalSeconds, 9);
            state.Advance(TimeSpan.FromSeconds(.1), drawEnabled: true); var afterConverted = state.Deck.DrawCharge;
            Assert.Equal(afterCard + .2 / cardInterval, afterConverted, 9);
            Assert.Equal(interval / 2, state.DrawIntervalSeconds, 9); // card speed expired, conversion still active
            state.ApplyDrawBlock(TimeSpan.FromSeconds(.05)); state.Advance(TimeSpan.FromSeconds(.08), drawEnabled: true);
            Assert.Equal(afterConverted + .03 / interval, state.Deck.DrawCharge, 9);
            Assert.Equal(interval, state.DrawIntervalSeconds, 9);
            Assert.Equal(TimeSpan.Zero, state.DrawBlockSpeedRemaining);
            Assert.Equal(TimeSpan.Zero, state.DrawBlockRemaining);
            Assert.Equal(3, state.Deck.Hand.Count); // sub-charge observations, no hidden reshuffle or hand-cap loss
            evidence.Write(new { seed, hero = hero.ToString(), level, upgraded, items = Display(items), equipment_raw = raw, equipment_interval = interval, card_interval = cardInterval, converted_interval = cardInterval / 2, normal_charge = normalCharge, after_card_charge = afterCard, after_converted_charge = afterConverted, after_block_and_expiry_charge = state.Deck.DrawCharge, restored_interval = state.DrawIntervalSeconds, post_clamp_conversion = true });
        }
        Assert.Equal(36, evidence.Count);
    }

    [Theory]
    [InlineData(HeroClass.Mage)]
    [InlineData(HeroClass.Priest)]
    [InlineData(HeroClass.Guardian)]
    public void Class_applicability_shield_cap_and_overflow_do_not_activate_candidates(HeroClass hero)
    {
        using var evidence = new Evidence("T03", hero);
        foreach (var seed in Seeds)
        for (var weapon = 0; weapon <= 5; weapon++)
        foreach (var position in ShieldPositions)
        foreach (var request in ShieldRequests)
        {
            var items = Items(seed, CardElement.Fire, 5, false); var profile = EquipmentCombatRules.Calculate(items); var state = State(hero, seed, profile, weapon);
            var maximum = state.MaximumHp / 2; var initial = position switch { "half" => maximum / 2, "full" => maximum, _ => 0 }; state.GainShield(initial);
            var draft = state.PreviewShield(request); var effective = state.GainShield(draft.Shield); var overflow = draft.Shield - effective;
            Assert.Equal(Math.Min(draft.Shield, maximum - initial), effective);
            Assert.Equal(hero switch { HeroClass.Mage => 35, HeroClass.Priest => 40, _ => 50 }, maximum); Assert.Equal(initial + effective, state.Shield); Assert.True(state.Shield <= maximum);
            if (request == 0) Assert.Equal(0, draft.Shield);
            Assert.Equal(draft.Shield, effective + overflow);
            Assert.Equal(hero == HeroClass.Guardian ? (int)Math.Floor(100 * (1 - profile.BulwarkDamageReduction)) : 100, state.ResolveIncomingDamage(100));
            Assert.Equal(FenxianImmediateDrawPolicy.CurrentRhythm, state.FenxianDrawPolicy);
            Assert.Equal(GuardianShieldBonusPolicy.CurrentSteps, state.GuardianShieldPolicy);
            var inactive = EquipmentCombatRules.Calculate([items[0]]); Assert.Equal(0, inactive.BulwarkDamageReduction);
            evidence.Write(new { seed, hero = hero.ToString(), weapon, position, card_shield = request, items = Display(items), inactive_items = Display([items[0]]), bulwark_profile_effective = profile.BulwarkDamageReduction, bulwark_class_applicable = hero == HeroClass.Guardian, incoming_damage = state.ResolveIncomingDamage(100), base_maximum_hp = state.MaximumHp, shield_cap = maximum, shield_before = initial, requested_shield = draft.Shield, effective_shield = effective, shield_overflow = overflow, shield_after = state.Shield, candidate_activation = false });
        }
        Assert.Equal(162, evidence.Count);
    }

    private static CombatEquipmentItem[] Items(int seed, CardElement element, int level, bool upgraded) => Slots.Select((slot, index) => new CombatEquipmentItem(new Guid(seed, 0, 0, 0, 0, 0, 0, 0, 0, 0, (byte)(index + 1)), slot, upgraded && index == 0 ? "Orange" : "Purple", level, element, "Bulwark", "DrawInterval")).ToArray();
    private static double RawResistance(CombatEquipmentItem[] items) => items.Sum(item => GameConfigCatalog.Current.EquipmentQuality(item.Quality).Resistance + item.Level * GameConfigCatalog.Current.EquipmentQuality(item.Quality).ResistancePerLevel);
    private static object[] Display(CombatEquipmentItem[] items) => items.Select(item => (object)new { instanceId = item.ItemId, slot = item.Slot, quality = item.Quality, element = item.Element.ToString(), level = item.Level, effectAffix = item.EffectAffix, secondaryTrait = item.SecondaryTrait }).ToArray();
    private static PlayerCombatState State(HeroClass hero, int seed, CombatEquipmentProfile profile, int weapon = 0)
    {
        var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", _ => "GUA" }; var cards = Common.Concat(Enumerable.Range(1, 6).Select(i => $"{prefix}-{i:D2}")).ToArray();
        var owned = GameConfigCatalog.Current.Cards.Where(c => c.Enabled && c.IsCodex && c.MonsterType is null).ToDictionary(c => c.CardId, c => new OwnedCard(c.CardId, c.HeroClass, (CardRarity)c.Rarity, 1, false));
        DeckRules.Validate(hero, cards, owned); return new PlayerCombatState(hero, cards, new Random(seed), weapon, profile);
    }
    private sealed class Evidence : IDisposable
    {
        private readonly GZipStream? _gzip;
        private readonly string? _source = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_SOURCE_SHA");
        private readonly string _case;
        public int Count { get; private set; }
        public Evidence(string caseName, HeroClass hero)
        {
            _case = "PR13-B08.4-" + caseName; var directory = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_CAP_EVIDENCE");
            if (string.IsNullOrWhiteSpace(directory)) return;
            Directory.CreateDirectory(directory); _gzip = new GZipStream(new FileStream(Path.Combine(directory, $"{_case}-{hero}.jsonl.gz"), FileMode.CreateNew), CompressionLevel.Fastest);
        }
        public void Write(object actual)
        {
            var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { case_id = _case, source_sha = _source, actual }) + "\n"); _gzip?.Write(bytes); Count++;
        }
        public void Dispose() => _gzip?.Dispose();
    }
}
