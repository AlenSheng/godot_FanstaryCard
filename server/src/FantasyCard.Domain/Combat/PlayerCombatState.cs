using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Combat;

public sealed class PlayerCombatState
{
    private readonly CombatRandom _random;
    private readonly Dictionary<string, TargetStunWindowSnapshot> _targetStunWindows =
        new(StringComparer.Ordinal);

    public PlayerCombatState(
        HeroClass heroClass,
        IReadOnlyList<string> cardIds,
        Random random,
        int weaponLevel = 0,
        CombatEquipmentProfile? equipment = null)
    {
        HeroClass = heroClass;
        MaximumHp = heroClass switch
        {
            HeroClass.Priest => 80,
            HeroClass.Mage => 70,
            HeroClass.Guardian => 100,
            _ => throw new DomainValidationException("Unknown hero class.")
        };
        Hp = MaximumHp;
        WeaponLevel = Math.Clamp(weaponLevel, 0, 5);
        Equipment = equipment ?? CombatEquipmentProfile.Empty;
        ArgumentNullException.ThrowIfNull(random);
        _random = new CombatRandom(random.Next());
        Deck = CombatDeck.Create(cardIds, _random);
    }

    public HeroClass HeroClass { get; }
    public int MaximumHp { get; }
    public int Hp { get; private set; }
    public int Shield { get; private set; }
    public int WeaponLevel { get; }
    public CombatEquipmentProfile Equipment { get; }
    public int EffectiveMaximumHp => Math.Min(
        (int)Math.Floor(MaximumHp * (1 + Equipment.VitalityOvercapBonus)),
        (int)Math.Floor(MaximumHp * 1.40));
    public CombatDeck Deck { get; }
    public int FenxianCombo { get; private set; }
    public CardElement? LastFenxianCore { get; private set; }
    public TimeSpan DrawSpeedRemaining { get; private set; }
    public double DrawSpeedModifier { get; private set; }
    public TimeSpan StunRemaining { get; private set; }
    public TimeSpan DrawBlockRemaining { get; private set; }
    public bool IsDead => Hp <= 0;

    public (int ShieldDamage, int HpDamage) TakeDamage(int damage)
    {
        if (damage <= 0)
        {
            return (0, 0);
        }

        var shieldDamage = Math.Min(Shield, damage);
        Shield -= shieldDamage;
        var hpDamage = Math.Min(Hp, damage - shieldDamage);
        Hp -= hpDamage;
        return (shieldDamage, hpDamage);
    }

    public int Heal(int amount)
    {
        var applied = Math.Min(Math.Max(0, amount), EffectiveMaximumHp - Hp);
        Hp += applied;
        return applied;
    }

    public int GainShield(int amount)
    {
        var maximumShield = MaximumHp / 2;
        var applied = Math.Min(Math.Max(0, amount), maximumShield - Shield);
        Shield += applied;
        return applied;
    }

    public int ResolveRecovery(int amount) =>
        (int)Math.Floor(Math.Max(0, amount) * (1 + Equipment.VitalityHealBonus));

    public void ClearShield() => Shield = 0;

    public void PayHealthCost(int amount)
    {
        if (amount > 0)
        {
            Hp = Math.Max(1, Hp - amount);
        }
    }

    public void AddDrawCharge(double amount) => Deck.AddCharge(amount, _random);

    public void DrawImmediate(int count) => Deck.DrawImmediate(count, _random);

    public void ApplyDrawSpeed(TimeSpan duration, double modifier)
    {
        if (duration > DrawSpeedRemaining || modifier < DrawSpeedModifier)
        {
            DrawSpeedRemaining = duration;
            DrawSpeedModifier = modifier;
        }
    }

    public void ApplyStun(TimeSpan duration)
    {
        if (duration > StunRemaining)
        {
            StunRemaining = duration;
        }
    }

    public void ApplyDrawBlock(TimeSpan duration)
    {
        if (duration > DrawBlockRemaining)
        {
            DrawBlockRemaining = duration;
        }
    }

    public void SetFenxian(CardElement? core, int combo)
    {
        LastFenxianCore = core;
        FenxianCombo = Math.Max(0, combo);
    }

    public (double Charge, int Draw) UpdateFenxian(CardElement? core, int coreCount)
    {
        if (HeroClass != HeroClass.Mage || core is null || coreCount <= 0)
        {
            if (HeroClass == HeroClass.Mage)
            {
                SetFenxian(null, 0);
            }
            return (0, 0);
        }

        FenxianCombo = LastFenxianCore == core ? FenxianCombo + 1 : 1;
        LastFenxianCore = core;
        var rhythm = Math.Min(5, coreCount + FenxianCombo - 1);
        var (charge, draw) = rhythm switch
        {
            1 => (0.12, 0),
            2 => (0.24, 0),
            3 => (0.36, 1),
            4 => (0.48, 1),
            _ => (0.50, 2)
        };
        charge = Math.Min(0.50, charge + WeaponPercentBonus());
        return (charge, draw);
    }

    public int ResolveHeal(int cardHeal)
    {
        var value = (double)cardHeal;
        if (HeroClass == HeroClass.Priest)
        {
            var missingRatio = Math.Clamp(1 - (double)Hp / MaximumHp, 0, 1);
            value = Math.Floor(value * (1 + 0.80 * missingRatio));
            value = Math.Floor(value * (1 + WeaponPercentBonus()));
        }
        return (int)Math.Floor(value * (1 + Equipment.VitalityHealBonus));
    }

    public int ResolveShield(int cardShield)
    {
        var value = (double)cardShield;
        if (HeroClass == HeroClass.Guardian)
        {
            var hpRatio = Math.Clamp((double)Hp / MaximumHp, 0, 1);
            value = Math.Floor(value * (1 + 0.45 * hpRatio));
        }
        value = Math.Floor(value * (1 + Equipment.BulwarkShieldBonus));
        if (HeroClass == HeroClass.Guardian)
        {
            value += WeaponLevel >= 4 ? 3 : WeaponLevel >= 2 ? 2 : 1;
        }
        return (int)value;
    }

    public int ResolveIncomingDamage(int damage) => HeroClass == HeroClass.Guardian
        ? (int)Math.Floor(Math.Max(0, damage) * (1 - Equipment.BulwarkDamageReduction))
        : Math.Max(0, damage);

    public double ElementalResistance(CardElement element) => Equipment.Resistance(element);

    public TimeSpan ResolveControl(TimeSpan cardControl)
    {
        if (HeroClass != HeroClass.Priest || cardControl <= TimeSpan.Zero)
        {
            return cardControl;
        }
        var missingRatio = Math.Clamp(1 - (double)Hp / MaximumHp, 0, 1);
        var seconds = Math.Floor(cardControl.TotalSeconds * (1 + 0.40 * missingRatio) * 1000) / 1000;
        seconds = Math.Floor(seconds * (1 + WeaponPercentBonus()) * 1000) / 1000;
        return TimeSpan.FromSeconds(seconds);
    }

    public void SetTargetStunWindow(string targetId, TimeSpan remaining, int count)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(targetId);
        _targetStunWindows[targetId] = new TargetStunWindowSnapshot(targetId, remaining, Math.Max(0, count));
    }

    public void PrepareForDuel(Random random)
    {
        Deck.ResetForDuel(random);
        FenxianCombo = 0;
        LastFenxianCore = null;
        DrawSpeedRemaining = TimeSpan.Zero;
        DrawSpeedModifier = 0;
        StunRemaining = TimeSpan.Zero;
        DrawBlockRemaining = TimeSpan.Zero;
        _targetStunWindows.Clear();
    }

    public void Advance(TimeSpan delta, bool drawEnabled)
    {
        if (delta <= TimeSpan.Zero)
        {
            return;
        }

        StunRemaining = Reduce(StunRemaining, delta);
        DrawBlockRemaining = Reduce(DrawBlockRemaining, delta);
        DrawSpeedRemaining = Reduce(DrawSpeedRemaining, delta);
        if (DrawSpeedRemaining == TimeSpan.Zero)
        {
            DrawSpeedModifier = 0;
        }

        foreach (var (targetId, window) in _targetStunWindows.ToArray())
        {
            var remaining = Reduce(window.Remaining, delta);
            if (remaining == TimeSpan.Zero)
            {
                _targetStunWindows.Remove(targetId);
            }
            else
            {
                _targetStunWindows[targetId] = window with { Remaining = remaining };
            }
        }

        if (drawEnabled && StunRemaining == TimeSpan.Zero && DrawBlockRemaining == TimeSpan.Zero)
        {
            var minimum = Equipment.HasRapidDraw ? 1.5 : 1.8;
            var intervalSeconds = Math.Clamp(
                4 * (1 + Equipment.DrawIntervalModifier) * (1 + DrawSpeedModifier),
                minimum,
                6.0);
            Deck.AddCharge(delta.TotalSeconds / intervalSeconds, _random);
        }
    }

    public PlayerCombatSnapshot Capture() =>
        new(
            MaximumHp,
            Hp,
            Shield,
            WeaponLevel,
            _random.State,
            Deck.Capture(),
            FenxianCombo,
            LastFenxianCore,
            DrawSpeedRemaining,
            DrawSpeedModifier,
            StunRemaining,
            DrawBlockRemaining,
            _targetStunWindows.Values.OrderBy(value => value.TargetId, StringComparer.Ordinal).ToArray(),
            Equipment);

    public void Restore(PlayerCombatSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        if (snapshot.MaximumHp != MaximumHp || snapshot.WeaponLevel != WeaponLevel ||
            snapshot.Equipment is not null && snapshot.Equipment != Equipment)
        {
            throw new DomainValidationException("A player combat snapshot cannot change immutable combat attributes.");
        }

        Hp = snapshot.Hp;
        Shield = snapshot.Shield;
        _random.Restore(snapshot.RandomState);
        Deck.Restore(snapshot.Deck);
        FenxianCombo = snapshot.FenxianCombo;
        LastFenxianCore = snapshot.LastFenxianCore;
        DrawSpeedRemaining = snapshot.DrawSpeedRemaining;
        DrawSpeedModifier = snapshot.DrawSpeedModifier;
        StunRemaining = snapshot.StunRemaining;
        DrawBlockRemaining = snapshot.DrawBlockRemaining;
        _targetStunWindows.Clear();
        foreach (var window in snapshot.TargetStunWindows)
        {
            _targetStunWindows[window.TargetId] = window;
        }
    }

    public void MarkDead() => Hp = 0;

    private double WeaponPercentBonus() => WeaponLevel switch
    {
        0 => 0.06,
        1 => 0.08,
        2 => 0.10,
        3 => 0.11,
        4 => 0.13,
        _ => 0.14
    };

    private static TimeSpan Reduce(TimeSpan value, TimeSpan delta) =>
        value <= delta ? TimeSpan.Zero : value - delta;
}
