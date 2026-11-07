using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Seasons;

public enum SeasonAssetScope
{
    Permanent = 1,
    ActiveSeason = 2,
    ArchivedSeason = 3
}

public enum SeasonAssetKind
{
    CardUnlock = 1, CardCopy, CardLevel, SignatureWeapon, DeckPreset, Cosmetic, Title,
    Achievement, SeasonHistory, WarriorSoul, ClassSoul, Diamond,
    Armor, Gold, EquipmentFragment, Recipe, ChallengeMark, PityCounter,
    ChallengeRecord, SeasonProgress, ActivityBadge
}

/// <summary>Origin and current asset domain remain distinct even after archival.</summary>
public sealed record SeasonAssetDomain
{
    public SeasonAssetDomain(string? originSeasonId, string? domainSeasonId, SeasonAssetScope scope)
    {
        if (!Enum.IsDefined(scope))
            throw new DomainValidationException("Unknown season asset scope.");
        if (originSeasonId is not null)
            SeasonDefinition.RequireIdentifier(originSeasonId, nameof(originSeasonId));
        if (domainSeasonId is not null)
            SeasonDefinition.RequireIdentifier(domainSeasonId, nameof(domainSeasonId));
        if (scope == SeasonAssetScope.Permanent && domainSeasonId is not null)
            throw new DomainValidationException("A permanent asset cannot belong to a season wallet.");
        if (scope != SeasonAssetScope.Permanent &&
            (originSeasonId is null || domainSeasonId is null || originSeasonId != domainSeasonId))
            throw new DomainValidationException("A seasonal asset must remain in its origin season domain.");

        OriginSeasonId = originSeasonId;
        DomainSeasonId = domainSeasonId;
        Scope = scope;
    }

    public string? OriginSeasonId { get; }
    public string? DomainSeasonId { get; }
    public SeasonAssetScope Scope { get; }

    public static bool IsPermanentKind(SeasonAssetKind kind) => kind switch
    {
        SeasonAssetKind.CardUnlock or SeasonAssetKind.CardCopy or SeasonAssetKind.CardLevel or
        SeasonAssetKind.SignatureWeapon or SeasonAssetKind.DeckPreset or SeasonAssetKind.Cosmetic or
        SeasonAssetKind.Title or SeasonAssetKind.Achievement or SeasonAssetKind.SeasonHistory or
        SeasonAssetKind.WarriorSoul or SeasonAssetKind.ClassSoul or SeasonAssetKind.Diamond => true,
        SeasonAssetKind.Armor or SeasonAssetKind.Gold or SeasonAssetKind.EquipmentFragment or
        SeasonAssetKind.Recipe or SeasonAssetKind.ChallengeMark or SeasonAssetKind.PityCounter or
        SeasonAssetKind.ChallengeRecord or SeasonAssetKind.SeasonProgress or SeasonAssetKind.ActivityBadge => false,
        _ => throw new DomainValidationException("Unknown season asset kind.")
    };

    public static SeasonAssetDomain ForAsset(SeasonAssetKind kind, string? originSeasonId) =>
        IsPermanentKind(kind)
            ? new(originSeasonId, null, SeasonAssetScope.Permanent)
            : new(originSeasonId, originSeasonId, SeasonAssetScope.ActiveSeason);

    /// <summary>Legacy fragment balances may fund permanent weapons, never new-season armor.</summary>
    public static SeasonAssetDomain HistoricalWeaponFragments { get; } = new(null, null, SeasonAssetScope.Permanent);

    public bool CanUseInSeason(SeasonAssetKind kind, SeasonContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        return IsPermanentKind(kind)
            ? Scope == SeasonAssetScope.Permanent
            : Scope == SeasonAssetScope.ActiveSeason && DomainSeasonId == context.SeasonId;
    }

    public void RequireUseInSeason(SeasonAssetKind kind, SeasonContext context)
    {
        if (!CanUseInSeason(kind, context))
            throw new DomainValidationException("The asset is not usable in the selected season.");
    }

    public bool CanFundSignatureWeapon(SeasonAssetKind kind)
    {
        _ = IsPermanentKind(kind);
        return kind == SeasonAssetKind.EquipmentFragment &&
            Scope is SeasonAssetScope.Permanent or SeasonAssetScope.ActiveSeason or SeasonAssetScope.ArchivedSeason;
    }

    /// <summary>Archival preserves origin and has no deletion or conversion side effects.</summary>
    public SeasonAssetDomain Archive() => Scope == SeasonAssetScope.ActiveSeason
        ? new(OriginSeasonId, DomainSeasonId, SeasonAssetScope.ArchivedSeason)
        : this;
}
