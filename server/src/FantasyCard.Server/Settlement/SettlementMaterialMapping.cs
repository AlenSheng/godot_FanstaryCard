using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Settlement;

public static class SettlementMaterialMapping
{
    // SQL identifiers must come only from this closed mapping, never from asset text.
    public static string? GetColumn(SettlementAsset asset) => asset.AssetKind switch
    {
        "WarriorSoul" => "warrior_soul",
        "EquipmentFragments" => "equipment_fragments",
        "ClassSoul" => asset.AssetId switch
        {
            "PriestSoul" or "class_soul:Priest" => "priest_soul",
            "MageSoul" or "class_soul:Mage" => "mage_soul",
            "GuardianSoul" or "class_soul:Guardian" => "guardian_soul",
            _ => null
        },
        _ => null
    };
}
