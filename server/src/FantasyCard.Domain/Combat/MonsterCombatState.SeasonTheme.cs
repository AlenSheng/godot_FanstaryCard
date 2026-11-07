using FantasyCard.Domain.Configuration;

namespace FantasyCard.Domain.Combat;

public sealed partial class MonsterCombatState
{
    public SeasonThemeDefinition? ThemeProfile {get;private set;}
    public int ThemeRecoveredHp {get;private set;}
    public long ThemeShieldGenerated {get;private set;}

    internal void SetThemeProfile(SeasonThemeDefinition? profile)
    {
        profile?.Validate();
        if(ThemeProfile==profile)return;
        if(ThemeProfile is not null||profile is not null&&(MonsterId!="annihilation-core"||DifficultyProfile is null))
            throw new InvalidDataException("A live boss cannot change its original seasonal theme.");
        ThemeProfile=profile;
        if(profile is not null)
        {
            _intents.Clear();_intents.AddRange(profile.Intents(BossPhase));
        }
    }

    private void RestoreThemeCounters(int recovered,long shields)
    {
        if(recovered<0||shields<0||ThemeProfile is null&&(recovered!=0||shields!=0)||
            recovered>(long)MaximumHp*(ThemeProfile?.RegenerationBudgetBasisPoints??0)/10000)
            throw new InvalidDataException("Saved theme recovery or shield accounting is invalid.");
        ThemeRecoveredHp=recovered;ThemeShieldGenerated=shields;
    }

    private static int RegenerationAmount(int maximum,int hp,int alreadyRecovered,SeasonThemeDefinition? profile)
    {
        if(profile is null||hp<=0)return 0;
        var budget=(int)((long)maximum*profile.RegenerationBudgetBasisPoints/10000);
        var step=(int)((long)maximum*profile.RegenerationStepBasisPoints/10000);
        return Math.Max(0,Math.Min(maximum-hp,Math.Min(step,budget-alreadyRecovered)));
    }
}
