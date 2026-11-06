using System.Text.Json;
using FantasyCard.ConfigExporter;
using FantasyCard.Domain.Configuration;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Explicit in-memory card-data probe. Never writes the formal workbook or activates a published configuration.</summary>
internal static class SeasonMageCardCandidate
{
    private static readonly Lazy<GameConfigCatalog> Candidate = new(Build);
    internal static GameConfigCatalog Current => Candidate.Value;

    private static GameConfigCatalog Build()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        string? workbook = null;
        string? originalBundle = null;
        while (directory is not null)
        {
            var root = Path.Combine(directory.FullName, "server/config/archive/season-v1-config-16");
            var path = Path.Combine(root,"FantasyCard_Config.xlsx");
            if (File.Exists(path)) { workbook = path; originalBundle=Path.Combine(root,"fantasycard.config.bytes"); break; }
            directory = directory.Parent;
        }
        var tables = XlsxConfigReader.Read(workbook ?? throw new FileNotFoundException("Pinned formal workbook required."));
        var table = tables.Single(t => t.Name == "Cards");
        var column = table.Columns.Select((c, i) => (c, i)).Single(x => x.c.Name == "immediate_draw");
        var rowIndex = table.Rows.Select((r, i) => (r, i)).Single(x => Equals(x.r[0].Value, "MAG-10")).i;
        var rows = table.Rows.ToArray(); var row = rows[rowIndex].ToArray();
        Assert.Equal(1L, Convert.ToInt64(row[column.i].Value, System.Globalization.CultureInfo.InvariantCulture));
        row[column.i] = new(column.c.Type, 0L); rows[rowIndex] = row;
        var changed = tables.Select(t => t == table ? t with { Rows = rows } : t).ToArray();
        var bytes = ConfigCompiler.Compile("season-v1-config-16-mage10-probe-r1", changed, out var hash);
        var result = GameConfigCatalog.Load(bytes); var original = GameConfigCatalog.Load(File.ReadAllBytes(originalBundle!));
        Assert.Equal(original.Cards.Count, result.Cards.Count);
        foreach (var card in original.Cards)
        {
            var actual = result.Cards.Single(x => x.CardId == card.CardId);
            Assert.Equal(card.CardId == "MAG-10" ? card with { Effect = card.Effect with { ImmediateDraw = 0 } } : card, actual);
        }
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_D03_CARD_VARIANT_OUTPUT");
        if (output is not null)
        {
            Assert.False(Directory.Exists(output)); Directory.CreateDirectory(output);
            File.WriteAllBytes(Path.Combine(output, "candidate.config.original.bytes"), bytes);
            File.WriteAllText(Path.Combine(output, "candidate.original.json"), JsonSerializer.Serialize(new { result.Version, result.ContentHash,
                compiled_hash = hash, before = original.Cards.Single(x => x.CardId == "MAG-10"), after = result.Cards.Single(x => x.CardId == "MAG-10"),
                formal_workbook_modified = false, other_card_rows_identical = true, published = false }));
        }
        return result;
    }
}
