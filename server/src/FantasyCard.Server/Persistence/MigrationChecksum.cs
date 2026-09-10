using System.Security.Cryptography;
using System.Text;

namespace FantasyCard.Server.Persistence;

internal static class MigrationChecksum
{
    public static string Calculate(string sql) => Hash(NormalizeLineEndings(sql));

    public static bool Matches(string sql, string appliedChecksum)
    {
        var normalized = NormalizeLineEndings(sql);
        // Older builds hashed checkout bytes, so retain LF/CRLF compatibility without rewriting history.
        return string.Equals(appliedChecksum, Hash(normalized), StringComparison.Ordinal)
            || string.Equals(appliedChecksum, Hash(sql), StringComparison.Ordinal)
            || string.Equals(appliedChecksum, Hash(normalized.Replace("\n", "\r\n", StringComparison.Ordinal)), StringComparison.Ordinal);
    }

    private static string NormalizeLineEndings(string sql) => sql.Replace("\r\n", "\n", StringComparison.Ordinal);

    private static string Hash(string sql) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(sql))).ToLowerInvariant();
}
