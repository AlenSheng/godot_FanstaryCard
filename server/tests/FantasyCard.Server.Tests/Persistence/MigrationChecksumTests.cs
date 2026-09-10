using FantasyCard.Server.Persistence;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class MigrationChecksumTests
{
    private const string LfSql = "CREATE TABLE example (\n    id integer PRIMARY KEY\n);\n";
    private const string CrlfSql = "CREATE TABLE example (\r\n    id integer PRIMARY KEY\r\n);\r\n";
    private const string MixedSql = "CREATE TABLE example (\r\n    id integer PRIMARY KEY\n);\r\n";
    private const string LfChecksum = "ecc5d96c1087f107748f2722e7b4e8a4e7f807a0eb720321607377c7b11fa8b2";
    private const string CrlfChecksum = "2c1337ba7df966d058414f2885f658c897388e498e4ba2eb9722ab41ce6224a1";
    private const string MixedChecksum = "98bd25c14eb0a9e8576f036f87e1fb1c872d9b53c4b4890f7c5c48a67898751c";

    [Theory]
    [InlineData(LfSql)]
    [InlineData(CrlfSql)]
    [InlineData(MixedSql)]
    public void New_migrations_use_the_same_checksum_across_checkout_line_endings(string sql)
    {
        Assert.Equal(LfChecksum, MigrationChecksum.Calculate(sql));
    }

    [Theory]
    [InlineData(LfSql, LfChecksum)]
    [InlineData(LfSql, CrlfChecksum)]
    [InlineData(CrlfSql, LfChecksum)]
    [InlineData(CrlfSql, CrlfChecksum)]
    [InlineData(MixedSql, LfChecksum)]
    [InlineData(MixedSql, CrlfChecksum)]
    [InlineData(MixedSql, MixedChecksum)]
    public void Previously_applied_migrations_accept_legacy_line_ending_checksums(string sql, string checksum)
    {
        Assert.True(MigrationChecksum.Matches(sql, checksum));
    }

    [Theory]
    [InlineData("CREATE TABLE example (\n    id bigint PRIMARY KEY\n);\n")]
    [InlineData("CREATE TABLE different (\n    id integer PRIMARY KEY\n);\n")]
    [InlineData("CREATE TABLE example (\n    id integer PRIMARY KEY\n);\nDROP TABLE example;\n")]
    [InlineData("CREATE TABLE example (\n    id integer PRIMARY KEY\n);")]
    [InlineData("CREATE TABLE example (\n    id integer PRIMARY KEY \n);\n")]
    [InlineData("CREATE TABLE example (\r    id integer PRIMARY KEY\r);\r")]
    public void Changes_other_than_lf_crlf_conversion_still_reject_applied_checksums(string changedSql)
    {
        Assert.False(MigrationChecksum.Matches(changedSql, LfChecksum));
        Assert.False(MigrationChecksum.Matches(changedSql, CrlfChecksum));
    }
}
