namespace FantasyCard.Server.Telemetry;

public sealed record PhysicalMovementClass(string Kind,bool Known,int DestroyedUnits,int TransferredUnits,int EscrowEntries,int EscrowReleases,int EscrowTransitions);

public static class PhysicalEquipmentFlow
{
    public static bool IsCreationPlacement(string reason,string? from)=>
        (reason,from) is ("equipment.craft","NotMinted") or ("mail.claim","Mail") or ("admin.grant_all_equipment","Admin") or
            ("settlement.extract","MatchReward") or ("settlement.death","MatchReward") or ("reward.recycle","MatchReward");

    public static PhysicalMovementClass Classify(string reason,string? from,string? to)
    {
        var placement=IsCreationPlacement(reason,from)&&(reason switch
        {
            "equipment.craft" or "mail.claim" or "admin.grant_all_equipment"=>to=="Inventory",
            "settlement.extract"=>to is "Inventory" or "Equipped",
            "settlement.death"=>to=="RelicPile",
            "reward.recycle"=>to=="Recycled",
            _=>false
        });
        if(placement)return new(to=="Recycled"?"InitialPlacementAndDestroy":"InitialPlacement",true,to=="Recycled"?1:0,0,0,0,0);
        return(reason,from,to) switch
        {
            ("equipment.discard","Inventory","Recycled") or ("equipment.enhance" or "admin_revoke","Inventory","EnhanceMaterialConsumed") or
                ("reward.recycle","InMatchBackpack" or "InMatchEquipped" or "RelicPile","Recycled")=>new("Destroy",true,1,0,0,0,0),
            ("market.listed","Inventory","MarketListed")=>new("EscrowEnter",true,0,0,1,0,0),
            ("market.purchased","MarketListed","Inventory")=>new("PlayerTransferAndEscrowRelease",true,0,1,0,1,0),
            ("market.cancelled" or "market.expired","MarketListed","Inventory") or ("market.return","MarketReturnPending","Inventory")=>new("EscrowRelease",true,0,0,0,1,0),
            ("market.cancelled" or "market.expired","MarketListed","MarketReturnPending") or ("market.relisted","MarketListed","MarketListed")=>new("EscrowTransition",true,0,0,0,0,1),
            ("equipment.reforge","Inventory" or "Equipped","Inventory")=>new("Mutation",true,0,0,0,0,0),
            ("season.archive","Inventory" or "Equipped","SeasonArchive")=>new("ArchiveDomainMove",true,0,0,0,0,0),
            ("season.archive","Recycled" or "EnhanceMaterialConsumed" or "MarketReturnPending",_) when from==to=>new("ArchiveDomainMove",true,0,0,0,0,0),
            ("settlement.death","InMatchBackpack" or "InMatchEquipped" or "RelicPile","RelicPile")=>new("RelicCustody",true,0,0,0,0,0),
            ("settlement.extract","InMatchBackpack" or "InMatchEquipped" or "RelicPile","Inventory" or "Equipped")=>new("ExtractionCustody",true,0,0,0,0,0),
            ("loadout.save" or "equipment.equip" or "equipment.unequip","Inventory","Equipped") or
                ("loadout.save" or "equipment.equip" or "equipment.unequip","Equipped","Inventory")=>new("WearMove",true,0,0,0,0,0),
            ("preparation.lock","Equipped","PreparationLocked")=>new("PreparationEscrowEnter",true,0,0,1,0,0),
            ("preparation.release","PreparationLocked","Equipped")=>new("PreparationEscrowRelease",true,0,0,0,1,0),
            ("match.start","PreparationLocked","InMatchEquipped")=>new("MatchCustody",true,0,0,0,0,1),
            _=>new("Unclassified",false,0,0,0,0,0)
        };
    }
}
