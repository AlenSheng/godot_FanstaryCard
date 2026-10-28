using System.Security.Cryptography;
using System.Text;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Bots;

/// <summary>Explicit searchable loot, not a copy of the bot's combat loadout.</summary>
public static class BotLootRules
{
    private static readonly string[] Slots = ["Head", "Hands", "Chest"];
    private static readonly string[] Elements = ["Fire", "Wood", "Earth", "Metal", "Water"];

    public static IReadOnlyList<ExplorationItem> Generate(Guid roomId, Guid playerId, int count)
    {
        if (count is < 0 or > 3) throw new DomainValidationException("Bot loot budget is invalid.");
        var items = new List<ExplorationItem>(count);
        for (var index = 0; index < count; index++)
        {
            var digest = SHA256.HashData(Encoding.UTF8.GetBytes($"bot-loot-v1:{roomId:D}:{playerId:D}:{index}"));
            var id = new Guid(digest.AsSpan(0, 16));
            var gear = new EquipmentRewardData(Slots[index], digest[16] % 2 == 0 ? "White" : "Green",
                Elements[digest[17] % Elements.Length], null, "DrawInterval");
            items.Add(new(id.ToString("D"), ExplorationItemKind.Equipment, Equipment: gear, IsGenerated: true));
        }
        return items;
    }

    public static void Validate(IReadOnlyList<ExplorationItem> items, int budget)
    {
        if (items.Count > budget || items.Select(item => item.ItemId).Distinct(StringComparer.Ordinal).Count() != items.Count ||
            items.Any(item => item.Kind != ExplorationItemKind.Equipment || item.Quantity != 1 || item.IsGenerated != true ||
                item.Equipment is not { Quality: "White" or "Green", Level: 0, EffectAffix: null } ||
                !EquipmentRewardRules.IsValid(item.Equipment)))
            throw new DomainValidationException("Bot loot contains an item outside its budget.");
    }
}
