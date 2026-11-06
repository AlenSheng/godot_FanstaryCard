using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Configuration;

/// <summary>Published zero-based quality ranks and exact ten-thousandth probabilities.</summary>
public sealed record SeasonLootConfig(string RuleId, int Difficulty, string LayerId,
    IReadOnlyList<int> Weights, int QualityCap, int PromotionCap)
{
    private static readonly string[] Qualities = ["White", "Green", "Blue", "Purple", "Orange", "Red"];
    public const int ProbabilityBasis = 10000;

    public static int Rank(string quality) => Array.IndexOf(Qualities,quality) is var rank && rank >= 0 ? rank
        : throw new DomainValidationException("Unknown seasonal equipment quality.");
    public static string Quality(int rank) => rank is >=0 and <=5 ? Qualities[rank]
        : throw new DomainValidationException("Unknown seasonal equipment rank.");
    public static string Layer(ChaosMapLayer layer,bool isBoss) => isBoss ? "boss" : layer switch
    {
        ChaosMapLayer.Outer => "outer", ChaosMapLayer.Middle => "middle", ChaosMapLayer.Core => "elite",
        _ => throw new DomainValidationException("Unknown seasonal loot layer.")
    };
    public void Validate()
    {
        if (string.IsNullOrWhiteSpace(RuleId) || Difficulty is <0 or >5 || LayerId is not ("outer" or "middle" or "elite" or "boss") ||
            Weights.Count != 5 || Weights.Any(value=>value is <0 or >ProbabilityBasis) || Weights.Sum()!=ProbabilityBasis ||
            QualityCap is <0 or >4 || PromotionCap is <0 or >3 || PromotionCap>QualityCap ||
            QualityCap>(Difficulty switch {0=>2,1=>3,_=>4}) || LayerId=="outer" && QualityCap>3 ||
            Weights.Select((value,rank)=>(value,rank)).Any(value=>value.rank>QualityCap && value.value!=0))
            throw new InvalidDataException("Invalid seasonal loot probabilities or caps.");
    }
    public string Roll(int roll)
    {
        if (roll is <0 or >=ProbabilityBasis) throw new ArgumentOutOfRangeException(nameof(roll));
        var threshold=0;
        for (var rank=0;rank<Weights.Count;rank++)
        {
            threshold+=Weights[rank];
            if (roll<threshold) return Quality(rank);
        }
        throw new InvalidDataException("Seasonal loot weights do not cover the roll.");
    }
    public string ApplyCaps(string baseQuality,bool promote,int difficultyCap)
    {
        var rank=Rank(baseQuality);
        if (rank==5) throw new DomainValidationException("Ordinary seasonal reward choices cannot mint red equipment.");
        if (promote && rank<PromotionCap) rank++;
        return Quality(Math.Min(rank,Math.Min(QualityCap,difficultyCap)));
    }
}
