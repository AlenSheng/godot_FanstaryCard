using FantasyCard.ConfigExporter;

namespace FantasyCard.Server.Tests.Config;

public sealed class ConfigCompilerTests
{
    [Fact]
    public void Compile_IsDeterministicAndEmbedsHash()
    {
        var tables = new[] { new ConfigTable("Cards", new[] { new ConfigColumn("id", ConfigValueType.Text, true, PublishScope.Both, "stable id") }, new[] { (IReadOnlyList<ConfigValue>)new[] { new ConfigValue(ConfigValueType.Text, "card-001") } }) };
        var first = ConfigCompiler.Compile("gdd-0.64-config-1", tables, out var firstHash);
        var second = ConfigCompiler.Compile("gdd-0.64-config-1", tables, out var secondHash);
        Assert.Equal(firstHash, secondHash);
        Assert.Equal(first, second);
        Assert.Contains(Convert.FromHexString(firstHash), first);
    }

    [Fact]
    public void Validate_RejectsDuplicatePrimaryKey()
    {
        var column = new ConfigColumn("id", ConfigValueType.Text, true, PublishScope.Both, "stable id");
        var row = (IReadOnlyList<ConfigValue>)new[] { new ConfigValue(ConfigValueType.Text, "same") };
        var table = new ConfigTable("Cards", new[] { column }, new[] { row, row });
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Validate(new[] { table }));
    }

    [Fact]
    public void Compile_PreservesFalseLogicalValueAsPresentEmptyMessage()
    {
        var columns = new[]
        {
            new ConfigColumn("id", ConfigValueType.Text, true, PublishScope.Both, "stable id"),
            new ConfigColumn("enabled", ConfigValueType.Logical, true, PublishScope.Both, "logical value")
        };
        var rows = new[]
        {
            (IReadOnlyList<ConfigValue>)
            [
                new ConfigValue(ConfigValueType.Text, "card-001"),
                new ConfigValue(ConfigValueType.Logical, false)
            ]
        };

        var bytes = ConfigCompiler.Compile("false-value-test", [new ConfigTable("Cards", columns, rows)], out _);

        Assert.True(bytes.AsSpan().IndexOf(new byte[] { 0x0A, 0x00 }) >= 0);
    }
}
