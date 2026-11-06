using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Common;

public sealed class PhysicalEquipmentFlowTests
{
    [Theory]
    [InlineData("equipment.craft","NotMinted","Inventory","InitialPlacement",0)]
    [InlineData("mail.claim","Mail","Inventory","InitialPlacement",0)]
    [InlineData("admin.grant_all_equipment","Admin","Inventory","InitialPlacement",0)]
    [InlineData("reward.recycle","MatchReward","Recycled","InitialPlacementAndDestroy",1)]
    [InlineData("equipment.reforge","Inventory","Inventory","Mutation",0)]
    [InlineData("season.archive","Recycled","Recycled","ArchiveDomainMove",0)]
    [InlineData("season.archive","Inventory","SeasonArchive","ArchiveDomainMove",0)]
    [InlineData("equipment.discard","Inventory","Recycled","Destroy",1)]
    [InlineData("equipment.enhance","Inventory","EnhanceMaterialConsumed","Destroy",1)]
    [InlineData("admin_revoke","Inventory","EnhanceMaterialConsumed","Destroy",1)]
    [InlineData("preparation.lock","Equipped","PreparationLocked","PreparationEscrowEnter",0)]
    [InlineData("match.start","PreparationLocked","InMatchEquipped","MatchCustody",0)]
    [InlineData("settlement.death","InMatchEquipped","RelicPile","RelicCustody",0)]
    public void QuantityChangesFollowDocumentedTransitionsRatherThanDestinationOrCurrentItemSource(string reason,string from,string to,string expected,int destroyed)
    {
        var result=PhysicalEquipmentFlow.Classify(reason,from,to);Assert.True(result.Known);Assert.Equal(expected,result.Kind);Assert.Equal(destroyed,result.DestroyedUnits);
    }

    [Fact]
    public void MarketTransferAndTwoKindsOfEscrowReleaseDoNotMintOrDestroy()
    {
        var listed=PhysicalEquipmentFlow.Classify("market.listed","Inventory","MarketListed");Assert.Equal(1,listed.EscrowEntries);Assert.Equal(0,listed.DestroyedUnits);
        var returned=PhysicalEquipmentFlow.Classify("market.expired","MarketListed","MarketReturnPending");Assert.Equal(1,returned.EscrowTransitions);Assert.Equal(0,returned.EscrowReleases);
        var claimed=PhysicalEquipmentFlow.Classify("market.return","MarketReturnPending","Inventory");Assert.Equal(1,claimed.EscrowReleases);
        var sold=PhysicalEquipmentFlow.Classify("market.purchased","MarketListed","Inventory");Assert.Equal(1,sold.TransferredUnits);Assert.Equal(1,sold.EscrowReleases);Assert.Equal(0,sold.DestroyedUnits);
    }

    [Theory]
    [InlineData("season.archive","Inventory","Recycled")]
    [InlineData("mail.claim","Mail","Recycled")]
    [InlineData("historical.unknown","Inventory","Recycled")]
    [InlineData("equipment.reforge","Recycled","Inventory")]
    public void UnprovenOrImpossibleShapesRemainUnclassified(string reason,string from,string to)
        =>Assert.False(PhysicalEquipmentFlow.Classify(reason,from,to).Known);
}
