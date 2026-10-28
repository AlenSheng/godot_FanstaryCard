using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

// Independent GDD calculation, with no call to CombatResolver or ResolveHeal.
internal sealed record TuningRecoveryOracle(CardElement? Core, int R, int P, int B, double K, double D,
    double SharedMultiplier, double E0, int RawConflictHeal, int OrdinaryHeal, int ConflictHeal, int Damage,
    int IncorrectPriestConflictHeal, bool FirstEligibleIsTuning, bool SameCoreTuningWithCounter, bool OrdinaryAndConflict)
{
    private static readonly double[] WeaponBonuses = [.06, .08, .10, .11, .13, .14];
    private static readonly (CardElement, CardElement)[] Conflicts =
    [(CardElement.Wood,CardElement.Earth),(CardElement.Earth,CardElement.Water),(CardElement.Water,CardElement.Fire),
     (CardElement.Fire,CardElement.Metal),(CardElement.Metal,CardElement.Wood)];
    private static bool Conflict(CardElement a, CardElement b) => Conflicts.Any(p => p == (a,b) || p == (b,a));

    public bool Matches(CardResolutionDraft draft) =>
        (Core,R,P,K,D,Damage,OrdinaryHeal+ConflictHeal) ==
        (draft.CoreElement,draft.CoreCount,draft.ConflictPairCount,draft.ResonanceMultiplier,draft.ConflictCancellation,draft.Damage,draft.Heal);

    public static TuningRecoveryOracle Calculate(IReadOnlyList<CombatCardDefinition> cards, PlayerCombatState attacker, Func<CardElement,double> resistance)
    {
        var eligible = cards.Where(c => c.Effect.ElementalDamage > 0 && c.Effect.Element != CardElement.None && c.Effect.SecondaryElementalDamage == 0).ToArray();
        CardElement? core = eligible.Length == 0 ? null : eligible[0].Effect.Element;
        var counts = eligible.GroupBy(c => c.Effect.Element).ToDictionary(g => g.Key,g => g.Count());
        var reveal = cards.Any(c => c.Effect.IsClassReveal);
        var revealElement = attacker.HeroClass switch { HeroClass.Mage => CardElement.Fire, HeroClass.Priest => CardElement.Water, _ => CardElement.Earth };
        var bases = cards.Select(c =>
        {
            var value = c.Effect.ElementalDamage + c.Effect.SameElementBonus*Math.Max(0,counts.GetValueOrDefault(c.Effect.Element)-3);
            return reveal && c.Effect.Element==revealElement ? (int)Math.Floor(value*1.3) : value;
        }).ToArray();
        var r = core is null ? 0 : counts.GetValueOrDefault(core.Value);
        var p = core is null ? 0 : eligible.Count(c => c.Effect.Element!=core && !c.Effect.IsElementTuning && Conflict(core.Value,c.Effect.Element));
        var b = cards.Any(c => c.Effect.ResonanceBonus>0) ? 1 : 0;
        var k = core is null ? 1 : 1+.20*Math.Max(0,r-1+b-p);
        var d = p==0 ? 0 : Math.Min(.80,.20*p+cards.Max(c => c.Effect.ConflictCancelBonus));
        var shared = core is null ? 1 : (1+attacker.Equipment.DamageBonus(core.Value))*(1-resistance(core.Value));
        var e0 = core is null ? 0 : cards.Select((c,i)=>(c,i)).Where(v => v.c.Effect.Element==core && v.c.Effect.SecondaryElementalDamage==0 && !v.c.Effect.IsElementTuning).Sum(v => bases[v.i])*shared*k;
        var rawConflict = p==0 ? 0 : (int)Math.Floor(e0*d*Math.Max(.50,cards.Max(c => c.Effect.ConflictHealCoefficient)))+2*p;
        var conflict = (int)Math.Floor(rawConflict*(1+attacker.Equipment.VitalityHealBonus));
        var ordinary = cards.Sum(c => c.Effect.Heal)*(1+.25*p);
        var missing = Math.Clamp(1-(double)attacker.Hp/attacker.MaximumHp,0,1);
        var weapon = WeaponBonuses[attacker.WeaponLevel];
        if (attacker.HeroClass==HeroClass.Priest) { ordinary=Math.Floor(ordinary*(1+.80*missing));ordinary=Math.Floor(ordinary*(1+weapon)); }
        ordinary=Math.Floor(ordinary*(1+attacker.Equipment.VitalityHealBonus));
        var wrong = attacker.HeroClass==HeroClass.Priest ? (int)Math.Floor(Math.Floor(Math.Floor(rawConflict*(1+.80*missing))*(1+weapon))*(1+attacker.Equipment.VitalityHealBonus)) : conflict;
        var damage = 0;
        for (var i=0;i<cards.Count;i++)
        {
            var effect=cards[i].Effect;
            var secondary=reveal && effect.SecondaryElement==revealElement ? (int)Math.Floor(effect.SecondaryElementalDamage*1.3) : effect.SecondaryElementalDamage;
            if (effect.SecondaryElementalDamage>0)
            {
                damage+=(int)Math.Floor(bases[i]*(core is not null ? shared : (1+attacker.Equipment.DamageBonus(effect.Element))*(1-resistance(effect.Element))));
                damage+=(int)Math.Floor(secondary*(core is not null ? shared : (1+attacker.Equipment.DamageBonus(effect.SecondaryElement))*(1-resistance(effect.SecondaryElement))));
            }
            else if (effect.ElementalDamage>0 && effect.Element!=CardElement.None)
            {
                var branch=effect.Element==core ? k : core is not null && !effect.IsElementTuning && Conflict(core.Value,effect.Element) ? 1-d : 1;
                damage+=Math.Max(0,(int)Math.Floor(bases[i]*shared*branch));
            }
            damage+=effect.DirectDamage+(int)Math.Floor((bases[i]+secondary+effect.DirectDamage)*attacker.Equipment.PiercingBonus);
        }
        return new(core,r,p,b,k,d,shared,e0,rawConflict,(int)ordinary,conflict,damage,wrong,
            eligible.Length>0 && eligible[0].Effect.IsElementTuning,
            p>0 && eligible.Any(c => c.Effect.IsElementTuning && c.Effect.Element==core),
            rawConflict>0 && cards.Any(c => c.Effect.Heal>0));
    }
}

internal sealed record TuningRecoveryCast(int Seed, int SeedBlock, string Hero, string Deck, string Group, string Profile,
    int Cast, double AtSeconds, IReadOnlyList<CombatCardInstance> Selected, int HpBefore, int MaximumHp, int ShieldBefore,
    int WeaponLevel, CombatEquipmentProfile Equipment, string TargetId, TuningRecoveryOracle Oracle,
    CardResolutionDraft Draft, CombatResolution Actual, bool Passed);
