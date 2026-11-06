using System.Globalization;
using System.Numerics;

namespace FantasyCard.Server.Telemetry;

public enum EconomyFlowKind { SystemMint, SystemBurn, Transfer, EscrowReserve, EscrowRelease, EscrowConsumed, AccountingOnly, Unclassified }
public sealed record EconomyFlowRow(string Currency,string WalletScope,string? WalletSeasonId,EconomyFlowKind Kind,string Channel,
    string Quantity,string LedgerDelta,long Records,bool Known=true);
public sealed record EconomyFlowTotal(string Currency,string WalletScope,string? WalletSeasonId,string SystemMint,string SystemBurn,
    string Transfer,string EscrowReserved,string EscrowReturned,string EscrowConsumed,string UnclassifiedMagnitude,string LedgerDelta,
    string RecognizedNetSupply,string ExpectedLedgerDelta,string ReconciliationDifference,long SourceRecords,bool CoverageComplete);
public sealed record EconomyFlowBreakdown(string Currency,string WalletScope,string? WalletSeasonId,EconomyFlowKind Kind,string Channel,
    string Quantity,string LedgerDelta,long SourceRecords,bool Known);
public sealed record EconomyFlowReport(DateTimeOffset FromUtc,DateTimeOffset ToUtc,DateTimeOffset ReadAtUtc,IReadOnlyList<EconomyFlowTotal> Totals,
    IReadOnlyList<EconomyFlowBreakdown> Sources,
    bool SourceGroupsTruncated,long AppliedRefreshesWithoutOriginalTime,long UnmatchedMarketTransactions,long InvalidAppliedRefreshes,
    bool RecognizedCurrencyCoverageComplete,
    bool PerAttemptPlaytimeRatesAvailable=false,string Scope="Persistent account-currency flows; provisional field loot, physical items and per-attempt playtime are separate collectors.");

/// <summary>Currency supply and account movements are distinct. IDs and arbitrary reasons never become meter labels.</summary>
public static class EconomyFlow
{
    public static bool IsPermanent(string currency)=>currency is "Diamond" or "WarriorSoul" or "PriestSoul" or "MageSoul" or "GuardianSoul" or "ClassSoul";
    public static bool KnownCurrency(string currency)=>currency is "Gold" or "Diamond" or "EquipmentFragments" or "WarriorSoul" or "PriestSoul" or "MageSoul" or "GuardianSoul" or "ChallengeMarks" or "BlueprintMarks" or "OrangeBlueprintMarks";
    public static (string Scope,string? Season) Wallet(string currency,string? season)=>IsPermanent(currency)?("Permanent",null):season is null?("LegacyUnspecified",null):("Season",season);

    public static (EconomyFlowKind Kind,string Channel,bool Known) Classify(string reason,string? source,bool positive)
    {
        if(reason is "market.purchase" or "market.sale")return(EconomyFlowKind.AccountingOnly,"Market",true);
        if(reason=="reward.choice.refresh.reserve"&&!positive)return(EconomyFlowKind.EscrowReserve,"Refresh",true);
        if(reason=="reward.choice.refresh.refund"&&positive)return(EconomyFlowKind.EscrowRelease,"Refresh",true);
        if(reason is "settlement.commit" or "activity.claim" or "journey.claim" or "mail.claim")
            return positive?(EconomyFlowKind.SystemMint,reason.Split('.')[0],true):(EconomyFlowKind.Unclassified,"Unknown",false);
        if(reason=="shop.purchase")return(positive?EconomyFlowKind.SystemMint:EconomyFlowKind.SystemBurn,"Shop",true);
        if(reason is "equipment.enhance" or "class_weapon.enhance" or "equipment.craft" or "equipment.reforge" or "card.craft" or "card.upgrade")
            return !positive?(EconomyFlowKind.SystemBurn,reason.StartsWith("card.",StringComparison.Ordinal)?"Card":"Equipment",true):(EconomyFlowKind.Unclassified,"Unknown",false);
        if(reason=="card.dismantle"&&positive)return(EconomyFlowKind.SystemMint,"Card",true);
        if(reason=="admin_revoke"&&!positive&&source=="AdminRevoke")return(EconomyFlowKind.SystemBurn,"Admin",true);
        return(EconomyFlowKind.Unclassified,"Unknown",false);
    }

    public static EconomyFlowRow Ledger(string currency,string? season,string reason,string? source,string delta,long records)
    {
        var value=Parse(delta);var wallet=Wallet(currency,season);var classification=Classify(reason,source,value.Sign>0);
        var knownCurrency=KnownCurrency(currency);
        return new(currency,wallet.Scope,wallet.Season,knownCurrency?classification.Kind:EconomyFlowKind.Unclassified,knownCurrency?classification.Channel:"Unknown",BigInteger.Abs(value).ToString(CultureInfo.InvariantCulture),
            value.ToString(CultureInfo.InvariantCulture),records,classification.Known&&knownCurrency&&(!value.IsZero||reason=="market.sale"));
    }

    public static bool MarketLegsKnown(string currency,BigInteger price,BigInteger net,long buyerRows,string? buyerSeason,BigInteger? buyerDelta,
        long sellerRows,string? sellerSeason,BigInteger? sellerDelta)=>buyerRows==1&&buyerDelta==-price&&
        (net.IsZero&&sellerRows==0||sellerRows==1&&sellerDelta==net&&(IsPermanent(currency)||buyerSeason==sellerSeason));

    public static IReadOnlyList<EconomyFlowTotal> Summarize(IEnumerable<EconomyFlowRow> source)
    {
        return source.GroupBy(r=>(r.Currency,r.WalletScope,r.WalletSeasonId)).OrderBy(g=>g.Key.Currency,StringComparer.Ordinal)
            .ThenBy(g=>g.Key.WalletScope,StringComparer.Ordinal).ThenBy(g=>g.Key.WalletSeasonId,StringComparer.Ordinal).Select(g=>
            {
                BigInteger Sum(EconomyFlowKind kind)=>g.Where(r=>r.Kind==kind).Aggregate(BigInteger.Zero,(a,r)=>a+Parse(r.Quantity));
                string Text(BigInteger value)=>value.ToString(CultureInfo.InvariantCulture);
                var mint=Sum(EconomyFlowKind.SystemMint);var burn=Sum(EconomyFlowKind.SystemBurn);var reserved=Sum(EconomyFlowKind.EscrowReserve);
                var returned=Sum(EconomyFlowKind.EscrowRelease);var consumed=Sum(EconomyFlowKind.EscrowConsumed);
                var delta=g.Aggregate(BigInteger.Zero,(a,r)=>a+Parse(r.LedgerDelta));var expected=mint-burn-reserved+returned+consumed;
                return new EconomyFlowTotal(g.Key.Currency,g.Key.WalletScope,g.Key.WalletSeasonId,Text(mint),Text(burn),Text(Sum(EconomyFlowKind.Transfer)),
                    Text(reserved),Text(returned),Text(consumed),Text(Sum(EconomyFlowKind.Unclassified)),Text(delta),Text(mint-burn),Text(expected),Text(delta-expected),g.Sum(r=>r.Records),g.All(r=>r.Known)&&delta==expected);
            }).ToArray();
    }

    public static IReadOnlyList<EconomyFlowBreakdown> Breakdown(IEnumerable<EconomyFlowRow> source)=>source
        .GroupBy(r=>(r.Currency,r.WalletScope,r.WalletSeasonId,r.Kind,r.Channel))
        .OrderBy(g=>g.Key.Currency,StringComparer.Ordinal).ThenBy(g=>g.Key.WalletScope,StringComparer.Ordinal).ThenBy(g=>g.Key.WalletSeasonId,StringComparer.Ordinal)
        .ThenBy(g=>g.Key.Kind).ThenBy(g=>g.Key.Channel,StringComparer.Ordinal)
        .Select(g=>new EconomyFlowBreakdown(g.Key.Currency,g.Key.WalletScope,g.Key.WalletSeasonId,g.Key.Kind,g.Key.Channel,
            g.Aggregate(BigInteger.Zero,(a,r)=>a+Parse(r.Quantity)).ToString(CultureInfo.InvariantCulture),
            g.Aggregate(BigInteger.Zero,(a,r)=>a+Parse(r.LedgerDelta)).ToString(CultureInfo.InvariantCulture),g.Sum(r=>r.Records),g.All(r=>r.Known))).ToArray();

    public static BigInteger Parse(string value)=>BigInteger.TryParse(value,NumberStyles.AllowLeadingSign,CultureInfo.InvariantCulture,out var result)
        ?result:throw new InvalidDataException("A telemetry amount must be an exact integer.");
}
