using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using Npgsql;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    // Native tools are permitted only after both filesystem/process ownership
    // and the actual loopback server identity have been checked. This is test
    // infrastructure; no production connection or inherited PG environment is used.
    private sealed class NativeRollbackPostgres(string bin, NpgsqlConnectionStringBuilder settings, int postmasterPid)
    {
        public int PostmasterPid { get; } = postmasterPid;
        private static StringComparison Comparison => OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        private static string Full(string path) => Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));
        private static void Require(bool condition, string reason)
        {
            if (!condition) throw new InvalidOperationException("Native rollback ownership rejected: " + reason);
        }
        private static void Regular(string path, bool directory)
        {
            var attributes = File.GetAttributes(path);
            Require(!attributes.HasFlag(FileAttributes.ReparsePoint), "link or junction");
            Require(attributes.HasFlag(FileAttributes.Directory) == directory, "unexpected file type");
        }

        public static async Task<NativeRollbackPostgres> VerifyAsync(string connectionString, string manifestPath, CancellationToken ct)
        {
            var requested = new NpgsqlConnectionStringBuilder(connectionString);
            Require(requested.Database?.StartsWith("ready_stop_", StringComparison.Ordinal) == true, "database must have ready_stop_ prefix");
            Require(requested.Host is "127.0.0.1" or "::1", "host must be literal loopback");
            var root = Full(Path.GetTempPath());
            Require(Path.GetFileName(root).StartsWith("fc-rollback-", StringComparison.Ordinal), "private temporary run root required");
            var manifest = Full(manifestPath);
            Require(string.Equals(Path.GetDirectoryName(manifest), root, Comparison), "manifest outside private run root");
            Regular(root, directory: true); Regular(manifest, directory: false);
            Require(new FileInfo(manifest).Length is > 0 and <= 65536, "manifest size");
            using var document = JsonDocument.Parse(await File.ReadAllBytesAsync(manifest, ct));
            var item = document.RootElement;
            Require(item.GetProperty("schema_version").GetInt32() == 1 && item.GetProperty("scope").GetString() == "disposable-local" &&
                item.GetProperty("task").GetString() == "pr13-stages-20261008", "manifest scope");
            Require(string.Equals(Full(item.GetProperty("run_root").GetString()!), root, Comparison), "manifest run root");
            var data = Full(item.GetProperty("data_directory").GetString()!);
            Require(string.Equals(data, Path.Combine(root, "pg-data"), Comparison), "data directory outside owned pg-data");
            Regular(data, directory: true);
            var pidFile = Path.Combine(data, "postmaster.pid"); Regular(pidFile, directory: false);
            var pidLines = await File.ReadAllLinesAsync(pidFile, ct);
            Require(pidLines.Length >= 4, "postmaster identity incomplete");
            var pid = item.GetProperty("postmaster_pid").GetInt32();
            Require(pid > 0 && int.Parse(pidLines[0], CultureInfo.InvariantCulture) == pid, "postmaster PID differs from owned data directory");
            Require(string.Equals(Full(pidLines[1]), data, Comparison), "postmaster data directory");
            Require(requested.Host == item.GetProperty("host").GetString() && requested.Port == item.GetProperty("port").GetInt32() &&
                requested.Port == int.Parse(pidLines[3], CultureInfo.InvariantCulture) && requested.Database == item.GetProperty("database").GetString() &&
                requested.Username == item.GetProperty("username").GetString(), "connection differs from owned manifest");
            var toolDirectory = Full(item.GetProperty("tool_directory").GetString()!); Regular(toolDirectory, directory: true);
            var suffix = OperatingSystem.IsWindows() ? ".exe" : "";
            var tools = item.GetProperty("tools");
            foreach (var name in new[] { "postgres", "pg_dump", "pg_restore", "createdb", "dropdb" })
            {
                var filename = name + suffix;
                var expected = tools.EnumerateArray().Single(entry => entry.GetProperty("name").GetString() == filename);
                var path = Path.Combine(toolDirectory, filename); Regular(path, directory: false);
                Require(new FileInfo(path).Length == expected.GetProperty("bytes").GetInt64(), "tool size differs");
                Require(Convert.ToHexStringLower(SHA256.HashData(await File.ReadAllBytesAsync(path, ct))) == expected.GetProperty("sha256").GetString(), "tool content differs");
            }
            using (var process = Process.GetProcessById(pid))
                Require(!process.HasExited && string.Equals(Full(process.MainModule!.FileName), Path.Combine(toolDirectory, "postgres" + suffix), Comparison), "owned PostgreSQL executable differs");
            await using var connection = new NpgsqlConnection(connectionString);
            await connection.OpenAsync(ct);
            await using var transaction = await connection.BeginTransactionAsync(ct);
            await using (var readOnly = new NpgsqlCommand("SET TRANSACTION READ ONLY", connection, transaction))
                await readOnly.ExecuteNonQueryAsync(ct);
            await using (var directory = new NpgsqlCommand("SHOW data_directory", connection, transaction) { CommandTimeout = 5 })
                Require(string.Equals(Full((string)(await directory.ExecuteScalarAsync(ct))!), data, Comparison), "actual server data directory differs");
            await using (var identity = new NpgsqlCommand("SELECT inet_server_port(),current_database(),current_user", connection, transaction) { CommandTimeout = 5 })
            await using (var reader = await identity.ExecuteReaderAsync(ct))
            {
                Require(await reader.ReadAsync(ct), "actual server identity missing");
                Require(reader.GetInt32(0) == requested.Port && reader.GetString(1) == requested.Database && reader.GetString(2) == requested.Username, "actual server identity differs");
            }
            await transaction.RollbackAsync(ct);
            Record("native-rollback-owned-PG-verified", new { pid, port = requested.Port, ownedDataDirectory = data,
                manifestSha256 = Convert.ToHexStringLower(SHA256.HashData(await File.ReadAllBytesAsync(manifest, ct))),
                toolContentsVerified = 5, transaction = "READ ONLY; rollback", noProductionOrInheritedConnection = true });
            return new(toolDirectory, requested, pid);
        }

        private ProcessStartInfo Start(string tool, string[] arguments)
        {
            var start = new ProcessStartInfo(Path.Combine(bin, tool + (OperatingSystem.IsWindows() ? ".exe" : "")))
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true };
            start.Environment.Clear();
            if (OperatingSystem.IsWindows()) start.Environment["SystemRoot"] = Environment.GetEnvironmentVariable("SystemRoot");
            start.Environment["PGPASSWORD"] = settings.Password;
            foreach (var argument in new[] { "--host", settings.Host!, "--port", settings.Port.ToString(CultureInfo.InvariantCulture), "--username", settings.Username!, "--no-password" })
                start.ArgumentList.Add(argument);
            foreach (var argument in arguments) start.ArgumentList.Add(argument);
            return start;
        }
        private static async Task FinishAsync(Process process, CancellationToken ct)
        {
            try { await process.WaitForExitAsync(ct); }
            finally { if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); } }
            Record("native-rollback-tool-stop", new { process.Id, process.ExitCode, executable = process.StartInfo.FileName });
            Assert.Equal(0, process.ExitCode);
        }
        private Process Launch(string tool, string[] arguments)
        {
            var process = Process.Start(Start(tool, arguments))!;
            Record("native-rollback-tool-start", new { tool, process.Id, executable = process.StartInfo.FileName, noWindow = true });
            return process;
        }
        private static async Task SaveToolLogsAsync(Process process, Task<string>? stdout, Task<string> stderr)
        {
            var directory = Path.Combine(EvidenceDirectory, "native-tool-" + process.Id + "-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            if (stdout is not null) await File.WriteAllTextAsync(Path.Combine(directory, "stdout.original.log"), await stdout);
            await File.WriteAllTextAsync(Path.Combine(directory, "stderr.original.log"), await stderr);
            Record("native-rollback-tool-logs", new { process.Id, directory, stdoutIsBinaryDump = stdout is null });
        }
        public async Task TextAsync(string tool, string[] arguments, CancellationToken ct)
        {
            using var bounded = CancellationTokenSource.CreateLinkedTokenSource(ct); bounded.CancelAfter(TimeSpan.FromSeconds(30));
            using var process = Launch(tool, arguments);
            var stdout = process.StandardOutput.ReadToEndAsync(CancellationToken.None); var stderr = process.StandardError.ReadToEndAsync(CancellationToken.None);
            try { await FinishAsync(process, bounded.Token); }
            finally { await SaveToolLogsAsync(process, stdout, stderr); }
        }
        public async Task DumpAsync(string database, string schema, string path, CancellationToken ct)
        {
            using var process = Launch("pg_dump", ["--dbname", database, "--schema", schema, "--format=custom", "--no-owner", "--no-acl", "--lock-wait-timeout=10s"]);
            var stderr = process.StandardError.ReadToEndAsync(CancellationToken.None);
            try
            {
                await using var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write);
                await process.StandardOutput.BaseStream.CopyToAsync(file, ct); await FinishAsync(process, ct);
            }
            finally
            {
                if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); }
                await SaveToolLogsAsync(process, null, stderr);
            }
        }
        public async Task RestoreAsync(string database, string path, CancellationToken ct)
        {
            using var process = Launch("pg_restore", ["--dbname", database, "--exit-on-error", "--no-owner", "--no-acl"]);
            var stdout = process.StandardOutput.ReadToEndAsync(CancellationToken.None); var stderr = process.StandardError.ReadToEndAsync(CancellationToken.None);
            try
            {
                await using var file = File.OpenRead(path); await file.CopyToAsync(process.StandardInput.BaseStream, ct);
                process.StandardInput.Close(); await FinishAsync(process, ct);
            }
            finally
            {
                if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); }
                await SaveToolLogsAsync(process, stdout, stderr);
            }
        }
    }
}
