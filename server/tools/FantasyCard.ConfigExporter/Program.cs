using System.Globalization;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Xml.Linq;

namespace FantasyCard.ConfigExporter;

public enum ConfigValueType { Text = 1, WholeNumber = 2, FloatingPoint = 3, Logical = 4 }
public enum PublishScope { Both = 1, Server = 2, Client = 3 }
public sealed record ConfigColumn(string Name, ConfigValueType Type, bool Required, PublishScope Scope, string Description);
public sealed record ConfigValue(ConfigValueType Type, object? Value);
public sealed record ConfigTable(string Name, IReadOnlyList<ConfigColumn> Columns, IReadOnlyList<IReadOnlyList<ConfigValue>> Rows);

public static class ConfigCompiler
{
    public static byte[] Compile(string version, IReadOnlyList<ConfigTable> tables, out string sha256)
    {
        if (string.IsNullOrWhiteSpace(version)) throw new InvalidDataException("configVersion is required.");
        Validate(tables);
        var canonical = EncodeBundle(version, [], tables);
        var hash = SHA256.HashData(canonical);
        sha256 = Convert.ToHexString(hash).ToLowerInvariant();
        return EncodeBundle(version, hash, tables);
    }

    public static void Validate(IReadOnlyList<ConfigTable> tables)
    {
        if (tables.Count == 0) throw new InvalidDataException("Workbook contains no publishable sheets.");
        var tableNames = new HashSet<string>(StringComparer.Ordinal);
        foreach (var table in tables)
        {
            if (!tableNames.Add(table.Name)) throw new InvalidDataException($"Duplicate table '{table.Name}'.");
            if (table.Columns.Count == 0) throw new InvalidDataException($"Table '{table.Name}' has no columns.");
            var columnNames = new HashSet<string>(StringComparer.Ordinal);
            foreach (var column in table.Columns)
            {
                if (!IsIdentifier(column.Name)) throw new InvalidDataException($"{table.Name}: invalid field name '{column.Name}'.");
                if (!columnNames.Add(column.Name)) throw new InvalidDataException($"{table.Name}: duplicate field '{column.Name}'.");
            }
            var keys = new HashSet<string>(StringComparer.Ordinal);
            for (var rowIndex = 0; rowIndex < table.Rows.Count; rowIndex++)
            {
                var row = table.Rows[rowIndex];
                if (row.Count != table.Columns.Count) throw new InvalidDataException($"{table.Name}: row {rowIndex + 6} has the wrong column count.");
                for (var columnIndex = 0; columnIndex < row.Count; columnIndex++)
                    if (table.Columns[columnIndex].Required && row[columnIndex].Value is null)
                        throw new InvalidDataException($"{table.Name}: row {rowIndex + 6}, field '{table.Columns[columnIndex].Name}' is required.");
                var key = Convert.ToString(row[0].Value, CultureInfo.InvariantCulture);
                if (string.IsNullOrWhiteSpace(key)) throw new InvalidDataException($"{table.Name}: row {rowIndex + 6} has an empty primary key.");
                if (!keys.Add(key)) throw new InvalidDataException($"{table.Name}: duplicate primary key '{key}'.");
            }
        }
    }

    private static bool IsIdentifier(string value)
    {
        if (string.IsNullOrEmpty(value) || !(char.IsLetter(value[0]) || value[0] == '_')) return false;
        return value.All(character => char.IsLetterOrDigit(character) || character == '_');
    }

    private static byte[] EncodeBundle(string version, byte[] hash, IReadOnlyList<ConfigTable> tables)
    {
        var writer = new ProtoWriter(); writer.String(1, version); writer.Bytes(2, hash);
        foreach (var table in tables) writer.Message(3, tableWriter =>
        {
            tableWriter.String(1, table.Name);
            foreach (var column in table.Columns) tableWriter.Message(2, columnWriter =>
            {
                columnWriter.String(1, column.Name); columnWriter.Int64(2, (long)column.Type);
                columnWriter.Bool(3, column.Required); columnWriter.Int64(4, (long)column.Scope); columnWriter.String(5, column.Description);
            });
            foreach (var row in table.Rows) tableWriter.Message(3, rowWriter =>
            {
                foreach (var value in row) rowWriter.Message(1, valueWriter =>
                {
                    if (value.Value is null) { valueWriter.Bool(5, true); return; }
                    switch (value.Type)
                    {
                        case ConfigValueType.Text: valueWriter.String(1, (string)value.Value); break;
                        case ConfigValueType.WholeNumber: valueWriter.Int64(2, (long)value.Value); break;
                        case ConfigValueType.FloatingPoint: valueWriter.Double(3, (double)value.Value); break;
                        case ConfigValueType.Logical: valueWriter.Bool(4, (bool)value.Value); break;
                    }
                });
            });
        });
        return writer.ToArray();
    }
}

public static class XlsxConfigReader
{
    private static readonly XNamespace Main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
    private static readonly XNamespace Rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private static readonly XNamespace PackageRel = "http://schemas.openxmlformats.org/package/2006/relationships";

    public static IReadOnlyList<ConfigTable> Read(string path)
    {
        using var archive = ZipFile.OpenRead(path);
        var shared = ReadSharedStrings(archive);
        var workbook = LoadXml(archive, "xl/workbook.xml");
        var relationships = LoadXml(archive, "xl/_rels/workbook.xml.rels").Root!.Elements(PackageRel + "Relationship")
            .ToDictionary(item => (string)item.Attribute("Id")!, item => (string)item.Attribute("Target")!, StringComparer.Ordinal);
        var tables = new List<ConfigTable>();
        foreach (var sheet in workbook.Root!.Element(Main + "sheets")!.Elements(Main + "sheet"))
        {
            var name = (string)sheet.Attribute("name")!;
            if (name.StartsWith('_' )) continue;
            var target = relationships[(string)sheet.Attribute(Rel + "id")!].Replace('\\', '/');
            if (target.StartsWith('/' )) target = target.TrimStart('/');
            else if (!target.StartsWith("xl/", StringComparison.Ordinal)) target = "xl/" + target;
            var grid = ReadGrid(archive, target, shared);
            tables.Add(ParseTable(name, grid));
        }
        return tables;
    }

    private static ConfigTable ParseTable(string name, Dictionary<(int Row, int Column), string> grid)
    {
        var maxColumn = grid.Keys.Where(key => key.Row <= 5).Select(key => key.Column).DefaultIfEmpty(-1).Max();
        if (maxColumn < 0) throw new InvalidDataException($"{name}: rows 1-5 must define field metadata.");
        var columns = new List<ConfigColumn>();
        for (var column = 0; column <= maxColumn; column++)
        {
            var fieldName = Cell(grid, 1, column).Trim();
            if (fieldName.Length == 0) throw new InvalidDataException($"{name}: row 1 contains an empty field name.");
            columns.Add(new ConfigColumn(fieldName, ParseType(Cell(grid, 2, column), name, fieldName), ParseBool(Cell(grid, 3, column), name, fieldName), ParseScope(Cell(grid, 4, column), name, fieldName), Cell(grid, 5, column)));
        }
        var maxRow = grid.Keys.Select(key => key.Row).DefaultIfEmpty(5).Max();
        var rows = new List<IReadOnlyList<ConfigValue>>();
        for (var row = 6; row <= maxRow; row++)
        {
            if (Enumerable.Range(0, columns.Count).All(column => Cell(grid, row, column).Length == 0)) continue;
            var values = new List<ConfigValue>();
            for (var column = 0; column < columns.Count; column++) values.Add(ParseValue(Cell(grid, row, column), columns[column], name, row));
            rows.Add(values);
        }
        return new ConfigTable(name, columns, rows);
    }

    private static ConfigValue ParseValue(string raw, ConfigColumn column, string table, int row)
    {
        if (raw.Length == 0) return new ConfigValue(column.Type, null);
        try
        {
            return column.Type switch
            {
                ConfigValueType.Text => new ConfigValue(column.Type, raw),
                ConfigValueType.WholeNumber => new ConfigValue(column.Type, long.Parse(raw, NumberStyles.Integer, CultureInfo.InvariantCulture)),
                ConfigValueType.FloatingPoint => new ConfigValue(column.Type, double.Parse(raw, NumberStyles.Float, CultureInfo.InvariantCulture)),
                ConfigValueType.Logical => new ConfigValue(column.Type, bool.Parse(raw)),
                _ => throw new InvalidDataException()
            };
        }
        catch (Exception exception) when (exception is FormatException or OverflowException)
        { throw new InvalidDataException($"{table}: row {row}, field '{column.Name}' cannot parse '{raw}' as {column.Type}.", exception); }
    }

    private static ConfigValueType ParseType(string value, string table, string field) => value.Trim().ToLowerInvariant() switch
    { "string" => ConfigValueType.Text, "int" or "int64" => ConfigValueType.WholeNumber, "double" or "float" => ConfigValueType.FloatingPoint, "bool" or "boolean" => ConfigValueType.Logical, _ => throw new InvalidDataException($"{table}.{field}: unsupported type '{value}'.") };
    private static PublishScope ParseScope(string value, string table, string field) => value.Trim().ToLowerInvariant() switch
    { "both" => PublishScope.Both, "server" => PublishScope.Server, "client" => PublishScope.Client, _ => throw new InvalidDataException($"{table}.{field}: scope must be both/server/client.") };
    private static bool ParseBool(string value, string table, string field) => bool.TryParse(value, out var result) ? result : throw new InvalidDataException($"{table}.{field}: required must be true/false.");
    private static string Cell(Dictionary<(int Row, int Column), string> grid, int row, int column) => grid.GetValueOrDefault((row, column), string.Empty);

    private static Dictionary<(int Row, int Column), string> ReadGrid(ZipArchive archive, string path, string[] shared)
    {
        var document = LoadXml(archive, path); var result = new Dictionary<(int, int), string>();
        foreach (var cell in document.Descendants(Main + "c"))
        {
            var reference = (string)cell.Attribute("r")!; var row = int.Parse(new string(reference.SkipWhile(char.IsLetter).ToArray()), CultureInfo.InvariantCulture);
            var column = ColumnIndex(new string(reference.TakeWhile(char.IsLetter).ToArray())); var type = (string?)cell.Attribute("t");
            string value;
            if (type == "inlineStr") value = string.Concat(cell.Descendants(Main + "t").Select(item => item.Value));
            else { var raw = cell.Element(Main + "v")?.Value ?? string.Empty; value = type == "s" && raw.Length > 0 ? shared[int.Parse(raw, CultureInfo.InvariantCulture)] : type == "b" ? (raw == "1" ? "true" : "false") : raw; }
            result[(row, column)] = value;
        }
        return result;
    }

    private static string[] ReadSharedStrings(ZipArchive archive)
    {
        var entry = archive.GetEntry("xl/sharedStrings.xml"); if (entry is null) return [];
        using var stream = entry.Open(); var document = XDocument.Load(stream);
        return document.Root!.Elements(Main + "si").Select(item => string.Concat(item.Descendants(Main + "t").Select(text => text.Value))).ToArray();
    }
    private static XDocument LoadXml(ZipArchive archive, string path) { var entry = archive.GetEntry(path) ?? throw new InvalidDataException($"XLSX entry '{path}' is missing."); using var stream = entry.Open(); return XDocument.Load(stream); }
    private static int ColumnIndex(string letters) { var result = 0; foreach (var letter in letters) result = result * 26 + char.ToUpperInvariant(letter) - 'A' + 1; return result - 1; }
}

internal sealed class ProtoWriter
{
    private readonly List<byte> _stream = [];
    public void String(int field, string? value) { if (!string.IsNullOrEmpty(value)) Bytes(field, Encoding.UTF8.GetBytes(value)); }
    public void Int64(int field, long value) { Tag(field, 0); Varint(unchecked((ulong)value)); }
    public void Bool(int field, bool value) { if (value) Int64(field, 1); }
    public void Double(int field, double value) { Tag(field, 1); var bytes = BitConverter.GetBytes(value); if (!BitConverter.IsLittleEndian) Array.Reverse(bytes); _stream.AddRange(bytes); }
    public void Bytes(int field, byte[] value) { if (value.Length == 0) return; Tag(field, 2); Varint((ulong)value.Length); _stream.AddRange(value); }
    public void Message(int field, Action<ProtoWriter> action)
    {
        var nested = new ProtoWriter();
        action(nested);
        var payload = nested.ToArray();
        Tag(field, 2);
        Varint((ulong)payload.Length);
        _stream.AddRange(payload);
    }
    public byte[] ToArray() => [.. _stream];
    private void Tag(int field, int wire) => Varint((ulong)((field << 3) | wire));
    private void Varint(ulong value) { while (value >= 128) { _stream.Add((byte)(value | 128)); value >>= 7; } _stream.Add((byte)value); }
}

public static class ConfigBundlePublisher
{
    private static readonly string[] FileNames =
    [
        "fantasycard.config.bytes",
        "fantasycard.config.version.txt",
        "fantasycard.config.sha256"
    ];

    public static void Publish(
        string serverDirectory,
        string clientDirectory,
        byte[] bytes,
        string version,
        string hash)
    {
        ArgumentNullException.ThrowIfNull(bytes);
        ArgumentException.ThrowIfNullOrWhiteSpace(version);
        ArgumentException.ThrowIfNullOrWhiteSpace(hash);
        var payloads = new Dictionary<string, byte[]>(StringComparer.Ordinal)
        {
            [FileNames[0]] = bytes,
            [FileNames[1]] = Encoding.UTF8.GetBytes(version + Environment.NewLine),
            [FileNames[2]] = Encoding.UTF8.GetBytes(hash + Environment.NewLine)
        };
        var targets = new[] { serverDirectory, clientDirectory }
            .SelectMany(directory => payloads.Select(payload => new PublishTarget(
                Path.GetFullPath(Path.Combine(directory, payload.Key)), payload.Value)))
            .ToArray();
        var transactionId = Guid.NewGuid().ToString("N");

        try
        {
            foreach (var target in targets)
            {
                var directory = Path.GetDirectoryName(target.Path)
                    ?? throw new InvalidOperationException("Config output directory is invalid.");
                Directory.CreateDirectory(directory);
                target.StagePath = target.Path + ".stage-" + transactionId;
                target.BackupPath = target.Path + ".backup-" + transactionId;
                File.WriteAllBytes(target.StagePath, target.Payload);
            }

            foreach (var target in targets)
            {
                if (File.Exists(target.Path))
                {
                    File.Move(target.Path, target.BackupPath!);
                    target.HadOriginal = true;
                }
                File.Move(target.StagePath!, target.Path);
                target.Committed = true;
            }
        }
        catch
        {
            foreach (var target in targets.Reverse())
            {
                if (target.Committed && File.Exists(target.Path)) File.Delete(target.Path);
                if (target.HadOriginal && File.Exists(target.BackupPath))
                    File.Move(target.BackupPath!, target.Path, true);
            }
            throw;
        }
        finally
        {
            foreach (var target in targets)
            {
                if (target.StagePath is not null && File.Exists(target.StagePath)) File.Delete(target.StagePath);
                if (target.BackupPath is not null && File.Exists(target.BackupPath)) File.Delete(target.BackupPath);
            }
        }
    }

    private sealed class PublishTarget(string path, byte[] payload)
    {
        public string Path { get; } = path;
        public byte[] Payload { get; } = payload;
        public string? StagePath { get; set; }
        public string? BackupPath { get; set; }
        public bool HadOriginal { get; set; }
        public bool Committed { get; set; }
    }
}

internal static class Program
{
    public static int Main(string[] args)
    {
        try
        {
            var options = Args(args); var input = Required(options, "input"); var version = Required(options, "version");
            var serverOutput = Required(options, "server-output"); var clientOutput = Required(options, "client-output");
            var tables = XlsxConfigReader.Read(input); var bytes = ConfigCompiler.Compile(version, tables, out var hash);
            ConfigBundlePublisher.Publish(serverOutput, clientOutput, bytes, version, hash);
            Console.WriteLine($"Exported {tables.Count} tables, {tables.Sum(table => table.Rows.Count)} rows, version={version}, sha256={hash}"); return 0;
        }
        catch (Exception exception) { Console.Error.WriteLine("CONFIG_EXPORT_FAILED: " + exception.Message); return 1; }
    }
    private static Dictionary<string, string> Args(string[] args) { var result = new Dictionary<string, string>(StringComparer.Ordinal); for (var i = 0; i < args.Length; i += 2) { if (!args[i].StartsWith("--", StringComparison.Ordinal) || i + 1 >= args.Length) throw new ArgumentException("Arguments use --name value pairs."); result[args[i][2..]] = args[i + 1]; } return result; }
    private static string Required(Dictionary<string, string> options, string key) => options.TryGetValue(key, out var value) && value.Length > 0 ? value : throw new ArgumentException($"--{key} is required.");
}
