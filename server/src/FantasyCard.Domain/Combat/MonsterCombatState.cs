namespace FantasyCard.Domain.Combat;

public sealed class MonsterCombatState
{
    private readonly List<MonsterIntentState> _intents;
    private readonly Dictionary<string, TimeSpan> _statusRemaining = new(StringComparer.Ordinal);

    public MonsterCombatState(
        string monsterId,
        int maximumHp,
        int hp,
        int shield,
        TimeSpan attackInterval,
        IReadOnlyList<MonsterIntentState> intents,
        double elementalAmplification = 0)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(monsterId);
        if (maximumHp <= 0 || hp is < 0 || hp > maximumHp || shield < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maximumHp), "Monster health and shield values are invalid.");
        }
        if (attackInterval <= TimeSpan.Zero || intents.Count == 0)
        {
            throw new ArgumentException("A monster requires a positive interval and at least one intent.");
        }

        MonsterId = monsterId;
        MaximumHp = maximumHp;
        Hp = hp;
        Shield = shield;
        AttackInterval = attackInterval;
        ArgumentOutOfRangeException.ThrowIfNegative(elementalAmplification);
        ElementalAmplification = elementalAmplification;
        _intents = intents.ToList();
    }

    public string MonsterId { get; }
    public int MaximumHp { get; }
    public int Hp { get; private set; }
    public int Shield { get; private set; }
    public TimeSpan AttackInterval { get; private set; }
    public double ElementalAmplification { get; }
    public IReadOnlyList<MonsterIntentState> Intents => _intents;
    public int IntentIndex { get; private set; }
    public TimeSpan IntervalProgress { get; private set; }
    public TimeSpan WindupRemaining { get; private set; }
    public bool IsCharging { get; private set; }
    public int EmpowerBonus { get; private set; }
    public TimeSpan StunRemaining { get; private set; }
    public int BossPhase { get; private set; } = 1;
    public bool BossPhaseTransitionPending { get; private set; }
    public bool IsDead => Hp <= 0;

    public (int ShieldDamage, int HpDamage) TakeDamage(int damage)
    {
        var shieldDamage = Math.Min(Shield, Math.Max(0, damage));
        Shield -= shieldDamage;
        var hpDamage = Math.Min(Hp, Math.Max(0, damage - shieldDamage));
        Hp -= hpDamage;
        if (MonsterId == "annihilation-core" && BossPhase == 1 && Hp <= MaximumHp / 2 && !IsDead)
        {
            BossPhaseTransitionPending = true;
        }
        return (shieldDamage, hpDamage);
    }

    public int GainShield(int amount)
    {
        var applied = Math.Max(0, amount);
        Shield += applied;
        return applied;
    }

    public void ApplyStun(TimeSpan duration)
    {
        if (duration > StunRemaining)
        {
            StunRemaining = duration;
        }
        var cancelledCurrentStep = WindupRemaining > TimeSpan.Zero;
        WindupRemaining = TimeSpan.Zero;
        IntervalProgress = TimeSpan.Zero;
        IsCharging = false;
        EmpowerBonus = 0;
        if (cancelledCurrentStep)
        {
            IntentIndex = (IntentIndex + 1) % _intents.Count;
            CompleteBossStep();
        }
    }

    public void SetRuntimeState(
        int intentIndex,
        TimeSpan intervalProgress,
        TimeSpan windupRemaining,
        bool isCharging,
        int empowerBonus,
        TimeSpan stunRemaining,
        IReadOnlyDictionary<string, TimeSpan> statusRemaining,
        int bossPhase = 1,
        bool bossPhaseTransitionPending = false)
    {
        IntentIndex = Math.Abs(intentIndex) % _intents.Count;
        IntervalProgress = intervalProgress;
        WindupRemaining = windupRemaining;
        IsCharging = isCharging;
        EmpowerBonus = empowerBonus;
        StunRemaining = stunRemaining;
        BossPhase = bossPhase;
        BossPhaseTransitionPending = bossPhaseTransitionPending;
        if (MonsterId == "annihilation-core" && BossPhase == 2)
        {
            SetBossPhaseTwoValues();
        }
        _statusRemaining.Clear();
        foreach (var (key, value) in statusRemaining)
        {
            _statusRemaining[key] = value;
        }
    }

    public MonsterIntentState? Advance(TimeSpan delta)
    {
        if (IsDead || delta <= TimeSpan.Zero)
        {
            return null;
        }

        foreach (var (key, remaining) in _statusRemaining.ToArray())
        {
            var next = Reduce(remaining, delta);
            if (next == TimeSpan.Zero)
            {
                _statusRemaining.Remove(key);
            }
            else
            {
                _statusRemaining[key] = next;
            }
        }

        if (StunRemaining > TimeSpan.Zero)
        {
            StunRemaining = Reduce(StunRemaining, delta);
            return null;
        }

        if (WindupRemaining > TimeSpan.Zero)
        {
            WindupRemaining = Reduce(WindupRemaining, delta);
            if (WindupRemaining > TimeSpan.Zero)
            {
                return null;
            }

            var resolved = _intents[IntentIndex];
            IntentIndex = (IntentIndex + 1) % _intents.Count;
            return resolved;
        }

        IntervalProgress += delta;
        if (IntervalProgress < AttackInterval)
        {
            return null;
        }

        IntervalProgress -= AttackInterval;
        var intent = _intents[IntentIndex];
        WindupRemaining = intent.Kind is MonsterIntentKind.Charge or MonsterIntentKind.Empower
            ? TimeSpan.FromSeconds(1.2)
            : TimeSpan.FromSeconds(0.6);
        return null;
    }

    public int ResolveIntentValue(MonsterIntentState intent)
    {
        var value = intent.Value + EmpowerBonus;
        if (IsCharging)
        {
            value = (int)Math.Floor(value * 1.5);
        }
        IsCharging = false;
        EmpowerBonus = 0;
        return value;
    }

    public int ResolveIntentDamage(MonsterIntentState intent, double targetResistance = 0)
    {
        var value = ResolveIntentValue(intent);
        var damage = intent.Element == CardElement.None
            ? value
            : (int)Math.Floor(value * (1 + ElementalAmplification) * (1 - targetResistance));
        CompleteBossStep();
        return damage;
    }

    public double ElementalResistance(CardElement incoming)
    {
        if (incoming == CardElement.None)
        {
            return 0;
        }
        if (MonsterId == "annihilation-core")
        {
            var main = BossPhase == 1 ? CardElement.Fire : CardElement.Metal;
            var neighbor = BossPhase == 1 ? CardElement.Wood : CardElement.Earth;
            if (incoming == main) return .35;
            if (incoming == neighbor) return .20;
            if (Counters(incoming, main)) return -.30;
            if (Counters(main, incoming)) return .30;
            return 0;
        }

        var mainElement = _intents.FirstOrDefault(intent => intent.Element != CardElement.None)?.Element
            ?? CardElement.None;
        if (mainElement == CardElement.None)
        {
            return 0;
        }
        var elite = MonsterId is "metal-guard" or "fire-herald" or "marsh-mother" or "stone-guard" or "thorn-guard";
        if (incoming == mainElement) return elite ? .25 : .15;
        if (elite && incoming == Generates(mainElement)) return .15;
        if (Counters(incoming, mainElement)) return -.30;
        if (Counters(mainElement, incoming)) return .25;
        return 0;
    }

    public void ResolveUtilityIntent(MonsterIntentState intent)
    {
        if (intent.Kind == MonsterIntentKind.Charge)
        {
            IsCharging = true;
        }
        else if (intent.Kind == MonsterIntentKind.Empower)
        {
            EmpowerBonus += intent.Value;
        }
        else if (intent.Kind == MonsterIntentKind.Shield)
        {
            GainShield(intent.Value);
        }
        CompleteBossStep();
    }

    public MonsterCombatSnapshot Capture() =>
        new(
            MonsterId,
            MaximumHp,
            Hp,
            Shield,
            AttackInterval,
            ElementalAmplification,
            _intents.ToArray(),
            IntentIndex,
            IntervalProgress,
            WindupRemaining,
            IsCharging,
            EmpowerBonus,
            StunRemaining,
            _statusRemaining
                .OrderBy(value => value.Key, StringComparer.Ordinal)
                .Select(value => new TimedCombatStatusSnapshot(value.Key, value.Value))
                .ToArray(),
            BossPhase,
            BossPhaseTransitionPending);

    public static MonsterCombatState Restore(MonsterCombatSnapshot snapshot)
    {
        var monster = new MonsterCombatState(
            snapshot.MonsterId,
            snapshot.MaximumHp,
            snapshot.Hp,
            snapshot.Shield,
            snapshot.AttackInterval,
            snapshot.Intents,
            snapshot.ElementalAmplification);
        monster.SetRuntimeState(
            snapshot.IntentIndex,
            snapshot.IntervalProgress,
            snapshot.WindupRemaining,
            snapshot.IsCharging,
            snapshot.EmpowerBonus,
            snapshot.StunRemaining,
            snapshot.StatusRemaining.ToDictionary(value => value.Key, value => value.Remaining, StringComparer.Ordinal),
            snapshot.BossPhase,
            snapshot.BossPhaseTransitionPending);
        return monster;
    }

    private static TimeSpan Reduce(TimeSpan value, TimeSpan delta) =>
        value <= delta ? TimeSpan.Zero : value - delta;

    private static bool Counters(CardElement attacker, CardElement target) => (attacker, target) is
        (CardElement.Water, CardElement.Fire) or
        (CardElement.Fire, CardElement.Metal) or
        (CardElement.Metal, CardElement.Wood) or
        (CardElement.Wood, CardElement.Earth) or
        (CardElement.Earth, CardElement.Water);

    private static CardElement Generates(CardElement element) => element switch
    {
        CardElement.Wood => CardElement.Fire,
        CardElement.Fire => CardElement.Earth,
        CardElement.Earth => CardElement.Metal,
        CardElement.Metal => CardElement.Water,
        CardElement.Water => CardElement.Wood,
        _ => CardElement.None
    };

    private void CompleteBossStep()
    {
        if (MonsterId != "annihilation-core" || !BossPhaseTransitionPending || IsDead)
        {
            return;
        }
        BossPhase = 2;
        BossPhaseTransitionPending = false;
        SetBossPhaseTwoValues();
        IntentIndex = 0;
        IntervalProgress = TimeSpan.Zero;
        WindupRemaining = TimeSpan.Zero;
        IsCharging = false;
        EmpowerBonus = 0;
    }

    private void SetBossPhaseTwoValues()
    {
        AttackInterval = TimeSpan.FromSeconds(3.8);
        _intents.Clear();
        _intents.AddRange([
            new(MonsterIntentKind.Attack, 5, CardElement.Metal),
            new(MonsterIntentKind.Attack, 5, CardElement.Earth),
            new(MonsterIntentKind.Shield, 8, CardElement.None),
            new(MonsterIntentKind.Attack, 5, CardElement.Metal),
            new(MonsterIntentKind.Attack, 5, CardElement.Earth),
            new(MonsterIntentKind.Direct, 8, CardElement.None)
        ]);
    }
}
