using FantasyCard.ConfigExporter;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Distinct, legal configuration controls; these numbers are not seasonal balance candidates.</summary>
internal static class PublishedConfigTestInputs
{
    public static (GameConfigCatalog Catalog, byte[] Bytes, string Hash) Create(string version, bool alternate = false)
    {
        var tables = XlsxConfigReader.Read(Path.Combine(FindRoot(), "config/FantasyCard_Config.xlsx"));
        tables = Set(tables, "Cards", "C01", "elemental_damage", alternate ? 400L : 200L);
        tables = Set(tables, "CardLevels", "C01:1", "value_bonus", alternate ? 7L : 3L);
        tables = Set(tables, "EquipmentQuality", "White", "damage_percent", alternate ? .27 : .13);
        tables = Set(tables, "Backpacks", "Free", "capacity", alternate ? 22L : 21L);
        tables = Set(tables, "Economy", "health-potion-heal-rate", "double_value", alternate ? .6 : .4);
        tables = Set(tables, "LootRules", "heal-outer", "gold", alternate ? 91L : 71L);
        tables = Set(tables, "LootRules", "heal-outer", "fragment_min", alternate ? 11L : 9L);
        tables = Set(tables, "LootRules", "heal-outer", "fragment_max", alternate ? 11L : 9L);
        tables = Set(tables, "LootRules", "heal-outer", "white_rate", alternate ? 0d : 1d);
        tables = Set(tables, "LootRules", "heal-outer", "green_rate", alternate ? 1d : 0d);
        tables = Set(tables, "LootRules", "heal-outer", "blue_rate", 0d);
        tables = Set(tables, "LootRules", "heal-outer", "purple_rate", 0d);
        tables = Set(tables, "LootRules", "heal-outer", "orange_rate", 0d);
        for (var index = 1; index <= 3; index++)
            tables = Set(tables, "LootRules", $"refresh-{index}", "refresh_gold", alternate ? 11L : 7L);
        var bytes = ConfigCompiler.Compile(version, tables, out var hash);
        return (GameConfigCatalog.Load(bytes), bytes, hash);
    }

    public static BattleRoom Room(GameConfigCatalog configuration, Guid playerId, bool withMap = false)
    {
        var cards = Enumerable.Range(1, 13).Select(i => $"C{i:D2}")
            .Concat(Enumerable.Range(1, 7).Select(i => $"MAG-{i:D2}")).ToArray();
        DeckRules.Validate(HeroClass.Mage, cards, configuration.Cards.Where(c => c.IsCodex).ToDictionary(c => c.CardId,
            c => new OwnedCard(c.CardId, c.HeroClass, (CardRarity)c.Rarity, 1, false)));
        var context = new SeasonContext("archive-season", 5, "season-v1", configuration.Version, "archive-control-stats");
        var room = new BattleRoom(Guid.NewGuid(), configuration.Version, CombatCardCatalog.Create(configuration), 73, season: context);
        room.AddPlayer(new(playerId, HeroClass.Mage, cards, null, InventoryCapacity: configuration.Backpack("Free").Capacity,
            CardLevels: Enumerable.Repeat(1,20).ToArray()));
        if (withMap) room.InitializeMap(ChaosMapGenerator.Generate(73, 1));
        return room;
    }

    public static void PutC01InHand(RoomPlayerState player)
    {
        var deck = player.Combat.Deck.Capture();
        var all = deck.Hand.Concat(deck.Library).Concat(deck.Discard).ToArray();
        var card = Assert.Single(all,c => c.CardId == "C01");
        player.Combat.Deck.Restore(new([card], all.Where(c => c.InstanceId != card.InstanceId).ToArray(), [], 0));
    }

    public static PveBattleSnapshot Target(int hp = 1000) => new PveBattleState(Guid.NewGuid(), "fire-bat",
        [new MonsterCombatState("fire-bat",hp,hp,0,TimeSpan.FromDays(1),[new(MonsterIntentKind.Attack,2,CardElement.Fire)])]).Capture();

    public static BattleRoom WithTarget(BattleRoom room, GameConfigCatalog configuration, int hp = 1000)
    {
        var snapshot = room.Capture();
        snapshot = snapshot with { Players = snapshot.Players.Select(p => p with { Phase = RoomPlayerPhase.Pve, Pve = Target(hp) }).ToArray() };
        return BattleRoom.Restore(snapshot, CombatCardCatalog.Create(configuration), 73);
    }

    public static void Store(string root, string version, byte[] bytes, string hash)
    {
        var folder = Path.Combine(root,version); Directory.CreateDirectory(folder);
        File.WriteAllBytes(Path.Combine(folder,"fantasycard.config.bytes"),bytes);
        File.WriteAllText(Path.Combine(folder,"fantasycard.config.version.txt"),version);
        File.WriteAllText(Path.Combine(folder,"fantasycard.config.sha256"),hash);
    }

    private static FantasyCard.ConfigExporter.ConfigTable[] Set(IReadOnlyList<FantasyCard.ConfigExporter.ConfigTable> tables,
        string name, string id, string field, object value)
    {
        var table = tables.Single(t => t.Name == name);
        var fieldIndex = table.Columns.Select((c,i) => (c,i)).Single(x => x.c.Name == field).i;
        Assert.Single(table.Rows,r => Equals(r[0].Value,id));
        var rows = table.Rows.Select(row =>
        {
            if (!Equals(row[0].Value,id)) return row;
            var changed = row.ToArray();changed[fieldIndex] = new(row[fieldIndex].Type,value);return changed;
        }).ToArray();
        return tables.Select(t => t == table ? t with { Rows = rows } : t).ToArray();
    }

    private static string FindRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName,"config/FantasyCard_Config.xlsx"))) return directory.FullName;
            directory = directory.Parent;
        }
        throw new DirectoryNotFoundException("The pinned source workbook is required.");
    }
}

internal sealed class ConfigArchiveDirectory : IDisposable
{
    public string Root { get; } = Path.Combine(Path.GetTempPath(),"fc-config-archive-"+Guid.NewGuid().ToString("N"));
    public ConfigArchiveDirectory() => Directory.CreateDirectory(Root);
    public void Dispose()
    {
        if (!Path.GetFullPath(Root).StartsWith(Path.GetFullPath(Path.GetTempPath()),StringComparison.Ordinal))
            throw new InvalidOperationException("The test archive must remain inside its owned temporary directory.");
        if (Directory.Exists(Root)) Directory.Delete(Root,recursive:true);
    }
}
