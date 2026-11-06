namespace FantasyCard.Domain.Configuration;

public sealed record SeasonDifficultyConfig(string Id, string NameKey, int HpBasisPoints, int ShieldBasisPoints,
    int DamageBasisPoints, int IntervalBasisPoints, int GoldBasisPoints, int SoulBasisPoints, int FragmentBasisPoints,
    int QualityCap, int EntryQualityCap, double PurpleAffixChance, bool RedBossEnabled, int? MageReturnRateBasisPoints = null)
{
    public const int Basis = 10000;
    public static int ToBasisPoints(double value)
    {
        if (!double.IsFinite(value) || value <= 0 || value > int.MaxValue / (double)Basis)
            throw new InvalidDataException("Season multiplier is outside fixed-point bounds.");
        var scaled = (decimal)value * Basis;
        if (scaled < 1 || scaled != decimal.Truncate(scaled))
            throw new InvalidDataException("Season multipliers support at most four decimal places.");
        return checked((int)scaled);
    }
    public static int Scale(int value, int basisPoints) => checked((int)((long)value * basisPoints / Basis));
    public static TimeSpan ScaleInterval(TimeSpan value, int basisPoints) =>
        TimeSpan.FromMilliseconds(checked((long)value.TotalMilliseconds * basisPoints / Basis));
}

/// <summary>Frozen numeric policy; intent values remain unscaled until charge/empower has resolved.</summary>
public sealed record SeasonMonsterProfile(int DamageBasisPoints, int ShieldBasisPoints, int IntervalBasisPoints, int WindupMilliseconds)
{
    public static SeasonMonsterProfile For(SeasonDifficultyConfig difficulty, string monsterId) => new(
        difficulty.DamageBasisPoints,difficulty.ShieldBasisPoints,difficulty.IntervalBasisPoints,
        monsterId is "metal-guard" or "fire-herald" or "marsh-mother" or "stone-guard" or "thorn-guard" or "annihilation-core" ? 800 : 600);
    public void Validate()
    {
        if (DamageBasisPoints <= 0 || ShieldBasisPoints <= 0 || IntervalBasisPoints <= 0 || WindupMilliseconds is not (600 or 800))
            throw new InvalidDataException("Invalid frozen seasonal monster policy.");
    }
}
