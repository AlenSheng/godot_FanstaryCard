using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Configuration;

/// <summary>Versioned season attributes; legacy quality rows remain a separate published policy.</summary>
public sealed record SeasonEquipmentConfig(string StatsVersion,IReadOnlyList<EquipmentQualityConfig> Qualities,
    double ResistanceCap,double DrawFloorSeconds,double DrawCeilingSeconds,double InfernoBonus,
    double RapidDrawReduction,double RapidDrawFloorSeconds,int ChainDrawBasisPoints,int OpeningDrawCount,double GoldenCicadaBonus)
{
    public EquipmentQualityConfig Quality(string quality)=>Qualities.SingleOrDefault(value=>value.Quality==quality)
        ??throw new DomainValidationException("The selected seasonal equipment quality is not published.");
    public void Validate()
    {
        if(!new[]{ResistanceCap,DrawFloorSeconds,DrawCeilingSeconds,InfernoBonus,RapidDrawReduction,RapidDrawFloorSeconds,GoldenCicadaBonus}.All(double.IsFinite) ||
            string.IsNullOrWhiteSpace(StatsVersion) || Qualities.Count!=6 || Qualities.Select(value=>value.Quality).Distinct(StringComparer.Ordinal).Count()!=6 ||
            ResistanceCap is <=0 or >.6 || DrawFloorSeconds is <1.8 or >6 || DrawCeilingSeconds<DrawFloorSeconds || DrawCeilingSeconds>6 ||
            RapidDrawFloorSeconds<DrawFloorSeconds || RapidDrawFloorSeconds>DrawCeilingSeconds ||
            InfernoBonus is <0 or >1 || RapidDrawReduction is <0 or >=1 || ChainDrawBasisPoints is <0 or >10000 || OpeningDrawCount is <0 or >1 || GoldenCicadaBonus is <0 or >.7)
            throw new InvalidDataException("Invalid published seasonal equipment policy.");
    }
}
