using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Combat;

public static class PveBattleFactory
{
    public static PveBattleState Create(ChaosMapCell cell)
    {
        ArgumentNullException.ThrowIfNull(cell);
        MonsterCombatState[] monsters = cell.MonsterGroupId switch
        {
            "BOX" when cell.Layer == ChaosMapLayer.Outer && cell.TreasureElement is { } element && Enum.IsDefined(element) =>
                [Monster("box-spirit", 84, 0, 4, element == CardElement.None ? MonsterIntentKind.Direct : MonsterIntentKind.Attack, 3, element)],
            "O1" => [Monster("fire-bat", 78, 0, 3.6, MonsterIntentKind.Attack, 3, CardElement.Fire)],
            "O2" => [Monster("thorn-mite", 84, 0, 4.0, MonsterIntentKind.Attack, 3, CardElement.Wood)],
            "O3" => [Monster("murk-snail", 86, 0, 4.2, MonsterIntentKind.Attack, 3, CardElement.Water)],
            "O4" => [Monster("sand-lizard", 92, 8, 4.6, MonsterIntentKind.Attack, 3, CardElement.Earth)],
            "O5" => [Monster("rust-rat", 80, 0, 3.6, MonsterIntentKind.Attack, 3, CardElement.Metal)],
            "O6" => [Monster("fire-bat-a", 42, 0, 3.6, MonsterIntentKind.Attack, 2, CardElement.Fire), Monster("fire-bat-b", 42, 0, 3.6, MonsterIntentKind.Attack, 2, CardElement.Fire)],
            "O7" => [Monster("rust-rat", 44, 0, 3.8, MonsterIntentKind.Attack, 2, CardElement.Metal), Monster("thorn-mite", 46, 0, 4.0, MonsterIntentKind.Attack, 2, CardElement.Wood)],
            "O8" => [Monster("murk-snail", 46, 0, 4.2, MonsterIntentKind.Attack, 2, CardElement.Water), Monster("sand-lizard", 50, 6, 4.6, MonsterIntentKind.Attack, 2, CardElement.Earth)],
            "M1" => [Monster("fire-bat-a", 56, 0, 3.8, MonsterIntentKind.Attack, 2, CardElement.Fire), Monster("fire-bat-b", 56, 0, 3.8, MonsterIntentKind.Attack, 2, CardElement.Fire)],
            "M2" => [Monster("murk-snail", 60, 0, 4.2, MonsterIntentKind.Attack, 2, CardElement.Water), Monster("sand-lizard", 66, 8, 4.6, MonsterIntentKind.Attack, 2, CardElement.Earth)],
            "M3" => [Monster("rust-rat", 58, 0, 3.6, MonsterIntentKind.Attack, 2, CardElement.Metal), Monster("thorn-mite", 62, 0, 4.0, MonsterIntentKind.Attack, 2, CardElement.Wood)],
            "M4" => [Monster("murk-snail-a", 64, 0, 4.0, MonsterIntentKind.Attack, 2, CardElement.Water), Monster("murk-snail-b", 64, 0, 4.0, MonsterIntentKind.Attack, 2, CardElement.Water)],
            "M5" => [Monster("fire-bat", 54, 0, 3.6, MonsterIntentKind.Attack, 2, CardElement.Fire), Monster("sand-lizard", 64, 8, 4.6, MonsterIntentKind.Attack, 2, CardElement.Earth)],
            "E1" => [Monster("metal-guard", 200, 12, 4.4, [new(MonsterIntentKind.Attack, 4, CardElement.Metal), new(MonsterIntentKind.Attack, 4, CardElement.Metal), new(MonsterIntentKind.Shield, 12, CardElement.None), new(MonsterIntentKind.Attack, 6, CardElement.Metal)])],
            "E2" => [Monster("fire-herald", 188, 0, 4.2, [new(MonsterIntentKind.Attack, 4, CardElement.Fire), new(MonsterIntentKind.Charge, 0, CardElement.None), new(MonsterIntentKind.Attack, 6, CardElement.Fire), new(MonsterIntentKind.Attack, 4, CardElement.Fire)])],
            "E3" => [Monster("marsh-mother", 210, 8, 4.6, [new(MonsterIntentKind.Attack, 4, CardElement.Water), new(MonsterIntentKind.Attack, 4, CardElement.Water), new(MonsterIntentKind.Shield, 10, CardElement.None), new(MonsterIntentKind.Attack, 6, CardElement.Water)])],
            "E4" => [Monster("stone-guard", 184, 24, 4.8, [new(MonsterIntentKind.Attack, 4, CardElement.Earth), new(MonsterIntentKind.Shield, 14, CardElement.None), new(MonsterIntentKind.Attack, 4, CardElement.Earth), new(MonsterIntentKind.Direct, 7, CardElement.None)])],
            "E5" => [Monster("thorn-guard", 196, 0, 4.2, [new(MonsterIntentKind.Attack, 4, CardElement.Wood), new(MonsterIntentKind.Empower, 2, CardElement.None), new(MonsterIntentKind.Attack, 4, CardElement.Wood), new(MonsterIntentKind.Attack, 5, CardElement.Wood)])],
            "E6" => [Monster("metal-guard", 160, 10, 4.4, [new(MonsterIntentKind.Attack, 4, CardElement.Metal), new(MonsterIntentKind.Attack, 4, CardElement.Metal), new(MonsterIntentKind.Shield, 12, CardElement.None), new(MonsterIntentKind.Attack, 6, CardElement.Metal)]), Monster("fire-bat", 40, 0, 3.6, MonsterIntentKind.Attack, 2, CardElement.Fire)],
            "BOSS" => [Monster("annihilation-core", 280, 20, 4.4, [new(MonsterIntentKind.Attack, 4, CardElement.Fire), new(MonsterIntentKind.Attack, 4, CardElement.Wood), new(MonsterIntentKind.Shield, 10, CardElement.None), new(MonsterIntentKind.Attack, 5, CardElement.Fire), new(MonsterIntentKind.Charge, 0, CardElement.None), new(MonsterIntentKind.Direct, 6, CardElement.None)])],
            _ => throw new DomainValidationException($"Unknown monster group '{cell.MonsterGroupId}'.")
        };
        return new PveBattleState(Guid.CreateVersion7(), monsters[0].MonsterId, monsters);
    }

    private static MonsterCombatState Monster(string id, int hp, int shield, double interval, MonsterIntentKind kind, int value, CardElement element) => Monster(id, hp, shield, interval, [new(kind, value, element)]);
    private static MonsterCombatState Monster(string id, int hp, int shield, double interval, IReadOnlyList<MonsterIntentState> intents)
    {
        var amplification = intents.Any(intent => intent.Element != CardElement.None)
            ? id is "metal-guard" or "fire-herald" or "marsh-mother" or "stone-guard" or "thorn-guard" ? 0.15 : 0.10
            : 0;
        if (id == "annihilation-core") amplification = 0.20;
        return new MonsterCombatState(id, hp, hp, shield, TimeSpan.FromSeconds(interval), intents, amplification);
    }
}
