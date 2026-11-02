using System.Text.Json;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Seasons;

public sealed class SeasonAssetDomainTests
{
    private static readonly SeasonContext OldSeason = new("season-old", 2, "season-v1", "config-old", "stats-1");
    private static readonly SeasonContext NewSeason = new("season-new", 2, "season-v1", "config-new", "stats-1");

    [Theory]
    [InlineData(SeasonAssetKind.CardUnlock)]
    [InlineData(SeasonAssetKind.CardCopy)]
    [InlineData(SeasonAssetKind.CardLevel)]
    [InlineData(SeasonAssetKind.SignatureWeapon)]
    [InlineData(SeasonAssetKind.DeckPreset)]
    [InlineData(SeasonAssetKind.Cosmetic)]
    [InlineData(SeasonAssetKind.Title)]
    [InlineData(SeasonAssetKind.Achievement)]
    [InlineData(SeasonAssetKind.SeasonHistory)]
    [InlineData(SeasonAssetKind.WarriorSoul)]
    [InlineData(SeasonAssetKind.ClassSoul)]
    [InlineData(SeasonAssetKind.Diamond)]
    public void PermanentAssetsSurviveArchivalAndRemainAvailableInNewSeason(SeasonAssetKind kind)
    {
        var asset = SeasonAssetDomain.ForAsset(kind, OldSeason.SeasonId);

        Assert.Equal(SeasonAssetScope.Permanent, asset.Scope);
        Assert.Equal(OldSeason.SeasonId, asset.OriginSeasonId);
        Assert.Null(asset.DomainSeasonId);
        Assert.Same(asset, asset.Archive());
        Assert.True(asset.CanUseInSeason(kind, NewSeason));
        asset.RequireUseInSeason(kind, NewSeason);
    }

    [Theory]
    [InlineData(SeasonAssetKind.Armor)]
    [InlineData(SeasonAssetKind.Gold)]
    [InlineData(SeasonAssetKind.EquipmentFragment)]
    [InlineData(SeasonAssetKind.Recipe)]
    [InlineData(SeasonAssetKind.ChallengeMark)]
    [InlineData(SeasonAssetKind.PityCounter)]
    [InlineData(SeasonAssetKind.ChallengeRecord)]
    [InlineData(SeasonAssetKind.SeasonProgress)]
    [InlineData(SeasonAssetKind.ActivityBadge)]
    public void SeasonalAssetsCannotMoveIntoNewEconomyAndArchivePreservesTheirOrigin(SeasonAssetKind kind)
    {
        var asset = SeasonAssetDomain.ForAsset(kind, OldSeason.SeasonId);
        var archived = asset.Archive();

        Assert.True(asset.CanUseInSeason(kind, OldSeason));
        Assert.False(asset.CanUseInSeason(kind, NewSeason));
        Assert.Equal(SeasonAssetScope.ActiveSeason, asset.Scope);
        Assert.Equal(SeasonAssetScope.ArchivedSeason, archived.Scope);
        Assert.Equal(asset.OriginSeasonId, archived.OriginSeasonId);
        Assert.Equal(asset.DomainSeasonId, archived.DomainSeasonId);
        Assert.False(archived.CanUseInSeason(kind, OldSeason));
        Assert.False(archived.CanUseInSeason(kind, NewSeason));
        Assert.Same(archived, archived.Archive());
        Assert.Throws<DomainValidationException>(() => archived.RequireUseInSeason(kind, NewSeason));
    }

    [Fact]
    public void OldAndHistoricalFragmentsMayFundPermanentWeaponsButNotNewArmor()
    {
        var current = SeasonAssetDomain.ForAsset(SeasonAssetKind.EquipmentFragment, NewSeason.SeasonId);
        var old = SeasonAssetDomain.ForAsset(SeasonAssetKind.EquipmentFragment, OldSeason.SeasonId).Archive();
        var historical = SeasonAssetDomain.HistoricalWeaponFragments;

        Assert.True(current.CanFundSignatureWeapon(SeasonAssetKind.EquipmentFragment));
        Assert.True(old.CanFundSignatureWeapon(SeasonAssetKind.EquipmentFragment));
        Assert.True(historical.CanFundSignatureWeapon(SeasonAssetKind.EquipmentFragment));
        Assert.True(current.CanUseInSeason(SeasonAssetKind.EquipmentFragment, NewSeason));
        Assert.False(old.CanUseInSeason(SeasonAssetKind.EquipmentFragment, NewSeason));
        Assert.False(historical.CanUseInSeason(SeasonAssetKind.EquipmentFragment, NewSeason));
        Assert.False(historical.CanFundSignatureWeapon(SeasonAssetKind.Diamond));
        Assert.False(historical.CanFundSignatureWeapon(SeasonAssetKind.Gold));
    }

    [Fact]
    public void OriginCannotBeRewrittenByAssigningAnotherSeasonDomain()
    {
        Assert.Throws<DomainValidationException>(() => new SeasonAssetDomain("season-old", "season-new", SeasonAssetScope.ActiveSeason));
        Assert.Throws<DomainValidationException>(() => new SeasonAssetDomain("season-old", "season-new", SeasonAssetScope.ArchivedSeason));
        Assert.Throws<DomainValidationException>(() => new SeasonAssetDomain(null, null, SeasonAssetScope.ActiveSeason));
        Assert.Throws<DomainValidationException>(() => new SeasonAssetDomain("season-old", "season-old", SeasonAssetScope.Permanent));
    }

    [Fact]
    public void UnknownKindAndScopeNeverBecomePermanentByDefault()
    {
        Assert.Throws<DomainValidationException>(() => SeasonAssetDomain.ForAsset((SeasonAssetKind)0, "season-old"));
        Assert.Throws<DomainValidationException>(() => SeasonAssetDomain.ForAsset((SeasonAssetKind)999, "season-old"));
        Assert.Throws<DomainValidationException>(() => new SeasonAssetDomain(null, null, (SeasonAssetScope)0));
        Assert.Throws<DomainValidationException>(() => new SeasonAssetDomain(null, null, (SeasonAssetScope)999));
    }

    [Fact]
    public void MarkingSeasonalEquipmentPermanentDoesNotMakeItUsableInNewSeason()
    {
        var asset = new SeasonAssetDomain("season-old", null, SeasonAssetScope.Permanent);

        Assert.False(asset.CanUseInSeason(SeasonAssetKind.Armor, NewSeason));
        Assert.False(asset.CanUseInSeason(SeasonAssetKind.Gold, NewSeason));
    }

    [Fact]
    public void ArchivedDomainSerializationKeepsBothOriginAndScope()
    {
        var archived = SeasonAssetDomain.ForAsset(SeasonAssetKind.Armor, "season-old").Archive();
        var restored = JsonSerializer.Deserialize<SeasonAssetDomain>(JsonSerializer.Serialize(archived));

        Assert.Equal(archived, restored);
        Assert.Equal("season-old", Assert.IsType<SeasonAssetDomain>(restored).OriginSeasonId);
        Assert.Equal(SeasonAssetScope.ArchivedSeason, restored.Scope);
    }
}
