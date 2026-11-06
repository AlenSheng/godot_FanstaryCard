using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Combat;

public sealed class PlayerCombatState
{
    private readonly CombatRandom _random;
    private Guid? _lastOpeningBattleId;
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
        GuardianShieldBonusPolicy guardianShieldBonusPolicy = GuardianShieldBonusPolicy.CurrentSteps,
        int? fenxianReturnRateBasisPoints = null)
    {
        if (!Enum.IsDefined(fenxianImmediateDrawPolicy))
        {
            throw new DomainValidationException("Unknown Fenxian immediate draw policy.");
        }
        if (!Enum.IsDefined(guardianShieldBonusPolicy))
        {
            throw new DomainValidationException("Unknown Guardian shield bonus policy.");
        }
        if(fenxianReturnRateBasisPoints is { } rate&&(fenxianImmediateDrawPolicy!=FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm||rate is <1 or >1000))
            throw new DomainValidationException("The return rate is invalid for this numerical policy.");

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
        FenxianReturnCredit = fenxianImmediateDrawPolicy==FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm?0:null;
        FenxianReturnRateBasisPoints=fenxianReturnRateBasisPoints;
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
    public FenxianImmediateDrawPolicy FenxianDrawPolicy { get; private set; }
    public GuardianShieldBonusPolicy GuardianShieldPolicy { get; private set; }
    public int GuardianShieldRemainderTenths { get; private set; }
    public CombatEquipmentProfile Equipment { get; private set; }
    public int EffectiveMaximumHp => Math.Min(
        (int)Math.Floor(MaximumHp * (1 + Equipment.VitalityOvercapBonus)),
        (int)Math.Floor(MaximumHp * 1.40));
    public CombatDeck Deck { get; }
    public int FenxianCombo { get; private set; }
    public CardElement? LastFenxianCore { get; private set; }
    public int FenxianChargeLevel { get; private set; }
    public double? FenxianReturnCredit { get; private set; }
    public int? FenxianReturnRateBasisPoints { get; private set; }
    public TimeSpan DrawSpeedRemaining { get; private set; }
    public double DrawSpeedModifier { get; private set; }
    public TimeSpan StunRemaining { get; private set; }
    public TimeSpan DrawBlockRemaining { get; private set; }
    public TimeSpan DrawBlockSpeedRemaining { get; private set; }
    public bool IsDead => Hp <= 0;
    private double MinimumDrawInterval => Equipment.MinimumDrawInterval??(Equipment.HasRapidDraw?1.5:1.8);
    private double MaximumDrawInterval => Equipment.MaximumDrawInterval??6;
    public double NaturalDrawIntervalSeconds => Math.Clamp(4*(1+Equipment.DrawIntervalModifier),MinimumDrawInterval,MaximumDrawInterval);
    public double DrawIntervalSeconds => Math.Clamp(
        4 * (1 + Equipment.DrawIntervalModifier) * (1 + DrawSpeedModifier),
        MinimumDrawInterval, MaximumDrawInterval) / (DrawBlockSpeedRemaining > TimeSpan.Zero ? 2 : 1);

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

    public (double Charge, int Draw) UpdateFenxian(CardElement? core, int coreCount, int? cardsSpent = null)
    {
        if (HeroClass != HeroClass.Mage || core is null || coreCount <= 0)
        {
            if (HeroClass == HeroClass.Mage)
            {
                SetFenxian(null, 0, 0);
            }
            return (0, 0);
        }

        if (FenxianDrawPolicy is FenxianImmediateDrawPolicy.SeasonBoundedRhythm or FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm)
        {
            if (cardsSpent is null or < 1 or > CombatDeck.HandLimit || coreCount > cardsSpent.Value)
                throw new DomainValidationException("Season Fenxian requires the actual consumed card count.");
            if (coreCount < 2)
            {
                SetFenxian(null, 0, 1);
                return ApplyFenxianReturnBudget(Math.Min(.50, .12 + WeaponPercentBonus()),0);
            }
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
            FenxianImmediateDrawPolicy.SeasonBoundedRhythm or FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm => Math.Min(rhythm is < 3 ? 0 : rhythm < 5 ? 1 : 2, cardsSpent!.Value - 1),
            _ => throw new DomainValidationException("Unknown Fenxian immediate draw policy.")
        };
        charge = Math.Min(0.50, charge + WeaponPercentBonus());
        return ApplyFenxianReturnBudget(charge,draw);
    }

    /// <summary>Opt-in candidate only: passive returns spend a saved credit; printed card draws are never truncated.</summary>
    private (double Charge,int Draw) ApplyFenxianReturnBudget(double charge,int draw)
    {
        if(FenxianDrawPolicy!=FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm)return(charge,draw);
        var available=FenxianReturnCredit!.Value;
        if(draw>0)
        {
            // Retain fractional credit for a future instant return instead of silently consuming it as charge.
            var granted=Math.Min(draw,(int)Math.Floor(available+1e-10));
            FenxianReturnCredit=Math.Max(0,available-granted);
            return(0,granted);
        }
        var budgeted=Math.Min(charge,available);
        FenxianReturnCredit=Math.Max(0,available-budgeted);
        return(budgeted,0);
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
        // Fractional shield also overflows when the integer part exactly fills the cap.
        return new(resolved, resolved >= remainingCapacity ? 0 : nextRemainder);
    }

    public void CommitGuardianShieldRemainder(int? remainderTenthsAfter)
    {
        if (remainderTenthsAfter is null) return;
        if (HeroClass != HeroClass.Guardian ||
            GuardianShieldPolicy != GuardianShieldBonusPolicy.FractionalRemainder ||
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

    /// <summary>Only a real PVE damage hit may receive the seasonal post-mitigation floor.</summary>
    public int ResolvePveIntentDamage(int mitigatedDamage, MonsterIntentState intent, bool positiveMinimum,
        bool hit = true, bool immune = false, int? effectiveBaseValue = null)
    {
        ArgumentNullException.ThrowIfNull(intent);
        if (mitigatedDamage < 0) throw new DomainValidationException("PVE mitigated damage cannot be negative.");
        if (!hit || immune || IsDead || intent.Kind is not (MonsterIntentKind.Attack or MonsterIntentKind.Direct)) return 0;
        var damage = ResolveIncomingDamage(mitigatedDamage);
        return positiveMinimum && (effectiveBaseValue ?? intent.Value) > 0 ? Math.Max(1, damage) : damage;
    }

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

    public void PrepareForDuel(Random random,Guid? battleId=null)
    {
        if(Equipment.StatsVersion is not null && battleId is not null && _lastOpeningBattleId==battleId)return;
        Deck.ResetForDuel(random);
        BeginBattle(battleId??Guid.NewGuid());
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

    /// <summary>One opening grant per new battle; restoring an existing combat snapshot grants nothing.</summary>
    public bool BeginBattle(Guid battleId)
    {
        if(battleId==Guid.Empty)throw new DomainValidationException("An opening draw requires a battle identity.");
        if(_lastOpeningBattleId==battleId || Equipment.StatsVersion is null&&FenxianDrawPolicy!=FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm)return false;
        _lastOpeningBattleId=battleId;
        if(FenxianDrawPolicy==FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm)FenxianReturnCredit=0;
        Deck.DrawImmediate(Equipment.OpeningDrawCount,_random);
        return true;
    }

    private void OnNaturalDraw()
    {
        if(Equipment.ChainDrawBasisPoints>0 && Deck.Hand.Count<CombatDeck.HandLimit && _random.Next(10000)<Equipment.ChainDrawBasisPoints)
            Deck.DrawImmediate(1,_random);
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
                    MinimumDrawInterval, MaximumDrawInterval);
                if(HeroClass==HeroClass.Mage&&FenxianDrawPolicy==FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm)
                    FenxianReturnCredit=Math.Min(2,FenxianReturnCredit!.Value+(boundaries[index]-start).TotalSeconds/NaturalDrawIntervalSeconds*(FenxianReturnRateBasisPoints??1000)/10000d);
                var rate = start < DrawBlockSpeedRemaining ? 2 : 1;
                Deck.AddCharge((boundaries[index] - start).TotalSeconds / interval * rate, _random,
                    Equipment.ChainDrawBasisPoints>0?OnNaturalDraw:null);
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
            GuardianShieldRemainderTenths,
            FenxianDrawPolicy,
            GuardianShieldPolicy,_lastOpeningBattleId,FenxianReturnCredit,FenxianReturnRateBasisPoints);

    // Only authoritative save/room snapshots may call Restore. Client commands must not supply policies.
    // A restored preview/room inherits the saved policy, never the constructor's current default.
    public void Restore(PlayerCombatSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        if (snapshot.MaximumHp != MaximumHp || snapshot.WeaponLevel != WeaponLevel ||
            snapshot.Equipment is not null && snapshot.Equipment != Equipment)
        {
            throw new DomainValidationException("A player combat snapshot cannot change immutable combat attributes.");
        }

        var fenxianPolicy = snapshot.FenxianPolicy == 0
            ? FenxianImmediateDrawPolicy.CurrentRhythm : snapshot.FenxianPolicy;
        var guardianPolicy = snapshot.GuardianPolicy == 0
            ? GuardianShieldBonusPolicy.CurrentSteps : snapshot.GuardianPolicy;
        if (!Enum.IsDefined(fenxianPolicy) || !Enum.IsDefined(guardianPolicy) ||
            snapshot.FenxianReturnRateBasisPoints is { } savedRate&&(fenxianPolicy!=FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm||savedRate is <1 or >1000) ||
            (fenxianPolicy==FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm
                ?snapshot.FenxianReturnCredit is not { } credit||!double.IsFinite(credit)||credit is <0 or >2
                :snapshot.FenxianReturnCredit is not null) ||
            snapshot.LastOpeningBattleId==Guid.Empty ||
            snapshot.GuardianShieldRemainderTenths is < 0 or > 9 ||
            snapshot.GuardianShieldRemainderTenths != 0 &&
                (HeroClass != HeroClass.Guardian || guardianPolicy != GuardianShieldBonusPolicy.FractionalRemainder))
        {
            throw new DomainValidationException("A numerical policy or shield remainder snapshot is invalid.");
        }

        // Check all new fields before mutating HP, piles, random state or policy.
        Hp = snapshot.Hp;
        Shield = snapshot.Shield;
        _random.Restore(snapshot.RandomState);
        Deck.Restore(snapshot.Deck);
        _lastOpeningBattleId=snapshot.LastOpeningBattleId;
        FenxianReturnCredit=snapshot.FenxianReturnCredit;
        FenxianReturnRateBasisPoints=snapshot.FenxianReturnRateBasisPoints;
        FenxianCombo = snapshot.FenxianCombo;
        LastFenxianCore = snapshot.LastFenxianCore;
        FenxianChargeLevel = Math.Clamp(snapshot.FenxianChargeLevel, 0, 5);
        FenxianDrawPolicy = fenxianPolicy;
        GuardianShieldPolicy = guardianPolicy;
        GuardianShieldRemainderTenths = snapshot.GuardianShieldRemainderTenths;
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
