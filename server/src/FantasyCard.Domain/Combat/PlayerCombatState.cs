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
        CombatEquipmentProfile? equipment = null,
        IReadOnlyList<int>? cardLevels = null,
        FenxianImmediateDrawPolicy fenxianImmediateDrawPolicy = FenxianImmediateDrawPolicy.CurrentRhythm,
        GuardianShieldBonusPolicy guardianShieldBonusPolicy = GuardianShieldBonusPolicy.CurrentSteps)
    {
        if (!Enum.IsDefined(fenxianImmediateDrawPolicy))
        {
            throw new DomainValidationException("Unknown Fenxian immediate draw policy.");
        }
        if (!Enum.IsDefined(guardianShieldBonusPolicy))
        {
            throw new DomainValidationException("Unknown Guardian shield bonus policy.");
        }

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
        FenxianDrawPolicy = fenxianImmediateDrawPolicy;
        GuardianShieldPolicy = guardianShieldBonusPolicy;
        Equipment = equipment ?? CombatEquipmentProfile.Empty;
        ArgumentNullException.ThrowIfNull(random);
        _random = new CombatRandom(random.Next());
        Deck = CombatDeck.Create(cardIds, _random, cardLevels);
    }

    public HeroClass HeroClass { get; }
    public int MaximumHp { get; }
    public int Hp { get; private set; }
    public int Shield { get; private set; }
    public int WeaponLevel { get; }
    public FenxianImmediateDrawPolicy FenxianDrawPolicy { get; }
    public GuardianShieldBonusPolicy GuardianShieldPolicy { get; }
    public int GuardianShieldRemainderTenths { get; private set; }
    public CombatEquipmentProfile Equipment { get; private set; }
    public int EffectiveMaximumHp => Math.Min(
        (int)Math.Floor(MaximumHp * (1 + Equipment.VitalityOvercapBonus)),
        (int)Math.Floor(MaximumHp * 1.40));
    public CombatDeck Deck { get; }
    public int FenxianCombo { get; private set; }
    public CardElement? LastFenxianCore { get; private set; }
    public int FenxianChargeLevel { get; private set; }
    public TimeSpan DrawSpeedRemaining { get; private set; }
    public double DrawSpeedModifier { get; private set; }
    public TimeSpan StunRemaining { get; private set; }
    public TimeSpan DrawBlockRemaining { get; private set; }
    public TimeSpan DrawBlockSpeedRemaining { get; private set; }
    public bool IsDead => Hp <= 0;
    public double DrawIntervalSeconds => Math.Clamp(
        4 * (1 + Equipment.DrawIntervalModifier) * (1 + DrawSpeedModifier),
        Equipment.HasRapidDraw ? 1.5 : 1.8, 6.0) / (DrawBlockSpeedRemaining > TimeSpan.Zero ? 2 : 1);

    public CombatPassiveInfo GetPassiveInfo()
    {
        var hpRatio = Math.Clamp((double)Hp / MaximumHp, 0, 1);
        return HeroClass switch
        {
            HeroClass.Priest => new("LinYuan", 0, null, .80 * (1 - hpRatio), .40 * (1 - hpRatio), 0, WeaponPercentBonus(), 0),
            HeroClass.Mage => new("FenXian", FenxianCombo, LastFenxianCore, 0, 0, 0, WeaponPercentBonus(), 0, FenxianChargeLevel),
            HeroClass.Guardian => new("ZaiYue", 0, null, 0, 0, .45 * hpRatio, 0, GuardianShieldFlatBonus()),
            _ => throw new DomainValidationException("Unknown hero class.")
        };
    }

    public void UpdateEquipment(CombatEquipmentProfile equipment)
    {
        Equipment = equipment ?? throw new ArgumentNullException(nameof(equipment));
        Hp = Math.Min(Hp, EffectiveMaximumHp);
    }

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

    public void ClearShield()
    {
        Shield = 0;
        GuardianShieldRemainderTenths = 0;
    }

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

    public void ApplyDrawBlockSpeed(TimeSpan duration)
    {
        if (duration > DrawBlockSpeedRemaining) DrawBlockSpeedRemaining = duration;
    }

    public TimeSpan ResolveTargetStun(string targetId, TimeSpan duration)
    {
        if (duration <= TimeSpan.Zero) return TimeSpan.Zero;
        if (!_targetStunWindows.TryGetValue(targetId, out var window))
        {
            SetTargetStunWindow(targetId, TimeSpan.FromSeconds(8), 1);
            return duration;
        }
        _targetStunWindows[targetId] = window with { Count = window.Count + 1 };
        return window.Count == 1 ? duration / 2 : TimeSpan.Zero;
    }

    public void SetFenxian(CardElement? core, int combo, int chargeLevel = 0)
    {
        LastFenxianCore = core;
        FenxianCombo = Math.Max(0, combo);
        FenxianChargeLevel = Math.Clamp(chargeLevel, 0, 5);
    }

    public (double Charge, int Draw) UpdateFenxian(CardElement? core, int coreCount)
    {
        if (HeroClass != HeroClass.Mage || core is null || coreCount <= 0)
        {
            if (HeroClass == HeroClass.Mage)
            {
                SetFenxian(null, 0, 0);
            }
            return (0, 0);
        }

        FenxianCombo = LastFenxianCore == core ? FenxianCombo + 1 : 1;
        LastFenxianCore = core;
        var rhythm = Math.Min(5, coreCount + FenxianCombo - 1);
        FenxianChargeLevel = rhythm;
        var charge = rhythm switch
        {
            1 => 0.12,
            2 => 0.24,
            3 => 0.36,
            4 => 0.48,
            _ => 0.50
        };
        var draw = FenxianDrawPolicy switch
        {
            FenxianImmediateDrawPolicy.CurrentRhythm => rhythm switch
            {
                1 or 2 => 0,
                3 or 4 => 1,
                _ => 2
            },
            FenxianImmediateDrawPolicy.CoreCardsSpent => coreCount switch
            {
                <= 2 => 0,
                3 or 4 => 1,
                _ => 2
            },
            _ => throw new DomainValidationException("Unknown Fenxian immediate draw policy.")
        };
        charge = Math.Min(0.50, charge + WeaponPercentBonus());
        return (charge, draw);
    }

    public int ResolveHeal(double cardHeal)
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

    public int ResolveShield(int cardShield, int healthCost = 0) =>
        PreviewShield(cardShield, healthCost).Shield;

    public GuardianShieldResolutionDraft PreviewShield(int cardShield, int healthCost = 0)
    {
        if (cardShield <= 0) return new(0, null);
        var value = (double)cardShield;
        if (HeroClass == HeroClass.Guardian)
        {
            var hpRatio = Math.Clamp((double)Math.Max(1, Hp - Math.Max(0, healthCost)) / MaximumHp, 0, 1);
            value *= 1 + 0.45 * hpRatio;
        }
        value = Math.Floor(value * (1 + Equipment.BulwarkShieldBonus));
        if (HeroClass != HeroClass.Guardian)
        {
            return new((int)value, null);
        }

        if (GuardianShieldPolicy == GuardianShieldBonusPolicy.CurrentSteps)
        {
            return new((int)value + GuardianShieldFlatBonus(), null);
        }

        var maximumShield = MaximumHp / 2;
        if (Shield >= maximumShield)
        {
            return new((int)value, null);
        }

        var x = GuardianShieldBonusTenths() + GuardianShieldRemainderTenths;
        var bonus = x / 10;
        var nextRemainder = x % 10;
        var resolved = (int)value + bonus;
        var remainingCapacity = maximumShield - Shield;
        return new(resolved, resolved > remainingCapacity ? 0 : nextRemainder);
    }

    public void CommitGuardianShieldRemainder(int? remainderTenthsAfter)
    {
        if (remainderTenthsAfter is null) return;
        if (GuardianShieldPolicy != GuardianShieldBonusPolicy.FractionalRemainder ||
            remainderTenthsAfter is < 0 or > 9)
        {
            throw new DomainValidationException("Guardian shield remainder commit is invalid.");
        }
        GuardianShieldRemainderTenths = remainderTenthsAfter.Value;
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
        var missingRatio = Math.Clamp(1 - (decimal)Hp / MaximumHp, 0, 1);
        var milliseconds = decimal.Floor((decimal)cardControl.TotalMilliseconds * (1 + .40m * missingRatio));
        milliseconds = decimal.Floor(milliseconds * (1 + (decimal)WeaponPercentBonus()));
        return TimeSpan.FromMilliseconds((double)milliseconds);
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
        FenxianChargeLevel = 0;
        DrawSpeedRemaining = TimeSpan.Zero;
        DrawSpeedModifier = 0;
        StunRemaining = TimeSpan.Zero;
        DrawBlockRemaining = TimeSpan.Zero;
        DrawBlockSpeedRemaining = TimeSpan.Zero;
        _targetStunWindows.Clear();
    }

    public void Advance(TimeSpan delta, bool drawEnabled)
    {
        if (delta <= TimeSpan.Zero)
        {
            return;
        }

        if (drawEnabled)
        {
            var boundaries = new[] { TimeSpan.Zero, delta, StunRemaining, DrawBlockRemaining, DrawSpeedRemaining, DrawBlockSpeedRemaining }
                .Where(value => value >= TimeSpan.Zero && value <= delta).Distinct().Order().ToArray();
            for (var index = 1; index < boundaries.Length; index++)
            {
                var start = boundaries[index - 1];
                if (start < StunRemaining || start < DrawBlockRemaining) continue;
                var speed = start < DrawSpeedRemaining ? DrawSpeedModifier : 0;
                var interval = Math.Clamp(4 * (1 + Equipment.DrawIntervalModifier) * (1 + speed),
                    Equipment.HasRapidDraw ? 1.5 : 1.8, 6.0);
                var rate = start < DrawBlockSpeedRemaining ? 2 : 1;
                Deck.AddCharge((boundaries[index] - start).TotalSeconds / interval * rate, _random);
            }
        }

        StunRemaining = Reduce(StunRemaining, delta);
        DrawBlockRemaining = Reduce(DrawBlockRemaining, delta);
        DrawBlockSpeedRemaining = Reduce(DrawBlockSpeedRemaining, delta);
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
            Equipment,
            DrawBlockSpeedRemaining,
            FenxianChargeLevel,
            GuardianShieldRemainderTenths);

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
        FenxianChargeLevel = Math.Clamp(snapshot.FenxianChargeLevel, 0, 5);
        if (snapshot.GuardianShieldRemainderTenths is < 0 or > 9)
        {
            throw new DomainValidationException("Guardian shield remainder snapshot is invalid.");
        }
        GuardianShieldRemainderTenths = GuardianShieldPolicy == GuardianShieldBonusPolicy.FractionalRemainder
            ? snapshot.GuardianShieldRemainderTenths
            : 0;
        DrawSpeedRemaining = snapshot.DrawSpeedRemaining;
        DrawSpeedModifier = snapshot.DrawSpeedModifier;
        StunRemaining = snapshot.StunRemaining;
        DrawBlockRemaining = snapshot.DrawBlockRemaining;
        DrawBlockSpeedRemaining = snapshot.DrawBlockSpeedRemaining;
        _targetStunWindows.Clear();
        foreach (var window in snapshot.TargetStunWindows)
        {
            _targetStunWindows[window.TargetId] = window;
        }
    }

    public void MarkDead() => Hp = 0;

    private int GuardianShieldFlatBonus() => GuardianShieldPolicy switch
    {
        GuardianShieldBonusPolicy.CurrentSteps => WeaponLevel >= 4 ? 3 : WeaponLevel >= 2 ? 2 : 1,
        GuardianShieldBonusPolicy.FractionalRemainder => (GuardianShieldBonusTenths() + GuardianShieldRemainderTenths) / 10,
        _ => throw new DomainValidationException("Unknown Guardian shield bonus policy.")
    };

    private int GuardianShieldBonusTenths() => WeaponLevel switch
    {
        0 => 10,
        1 => 14,
        2 => 18,
        3 => 22,
        4 => 26,
        _ => 30
    };

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
