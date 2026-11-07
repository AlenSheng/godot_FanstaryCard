using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Test-run evidence only: one durable started record per frozen case, never an automatic retry.</summary>
internal sealed class SeasonFirstFortnightAttemptJournal(string path, int maximum, IReadOnlySet<string> allowedCases)
{
    private static readonly JsonSerializerOptions Json = new();
    private readonly HashSet<string> _allowedCases = new(allowedCases, StringComparer.Ordinal);
    internal int Maximum => maximum;

    internal int Reserve(string caseId, string actorId, Guid preparationId, DateTimeOffset scheduledAtUtc, bool syntheticLedgerOnly)
    {
        if (maximum is < 1 or > 300 || !_allowedCases.Contains(caseId))
            throw new InvalidOperationException("F01 case or maximum differs from the frozen plan.");
        return Append(caseId, "started", new { actorId, preparationId, scheduledAtUtc, syntheticLedgerOnly }, reserve: true);
    }

    internal void Phase(string caseId, string phase, object detail)
    {
        if (string.IsNullOrWhiteSpace(phase) || phase == "started")
            throw new InvalidOperationException("A F01 phase cannot create or replace its original start.");
        Append(caseId, phase, detail, reserve: false);
    }

    private int Append(string caseId, string kind, object detail, bool reserve)
    {
        if (maximum is < 1 or > 300) throw new InvalidOperationException("F01 maximum differs from the bounded budget.");
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        using var file = new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.Read);
        if (file.Length > 0)
        {
            file.Seek(-1, SeekOrigin.End);
            if (file.ReadByte() != '\n') throw new InvalidDataException("F01 journal has an incomplete tail; preserve it and stop.");
        }
        file.Position = 0;
        var previous = new string('0', 64);
        var sequence = 0;
        var started = new HashSet<string>(StringComparer.Ordinal);
        using (var reader = new StreamReader(file, Encoding.UTF8, detectEncodingFromByteOrderMarks: false, leaveOpen: true))
        {
            while (reader.ReadLine() is { } line)
            {
                using var document = JsonDocument.Parse(line);
                var record = document.RootElement;
                var payload = record.GetProperty("payload");
                if (record.GetProperty("sequence").GetInt32() != ++sequence
                    || record.GetProperty("previous").GetString() != previous
                    || record.GetProperty("hash").GetString() != Digest(previous, payload))
                    throw new InvalidDataException("F01 journal chain differs; no repair or reset is permitted.");
                var priorCase = payload.GetProperty("caseId").GetString()!;
                if (payload.GetProperty("kind").GetString() == "started")
                {
                    if (!_allowedCases.Contains(priorCase) || !started.Add(priorCase))
                        throw new InvalidDataException("F01 journal contains an unknown or duplicate start.");
                }
                else if (!started.Contains(priorCase)) throw new InvalidDataException("F01 phase has no original start.");
                previous = record.GetProperty("hash").GetString()!;
            }
        }
        if (started.Count > maximum) throw new InvalidDataException("F01 prior starts exceed the declared maximum.");
        if (reserve && (started.Contains(caseId) || started.Count >= maximum))
            throw new InvalidOperationException("The F01 case already started or its budget is exhausted.");
        if (!reserve && !started.Contains(caseId)) throw new InvalidOperationException("The F01 phase has no started case.");
        var next = JsonSerializer.SerializeToElement(new { kind, caseId, detail }, Json);
        var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { sequence = sequence + 1, previous, payload = next, hash = Digest(previous, next) }, Json) + "\n");
        file.Position = file.Length;
        file.Write(bytes);
        file.Flush(flushToDisk: true);
        return started.Count + (reserve ? 1 : 0);
    }

    private static string Digest(string previous, JsonElement payload) => Convert.ToHexStringLower(
        SHA256.HashData(Encoding.UTF8.GetBytes(previous + "\n" + JsonSerializer.Serialize(payload, Json))));
}

/// <summary>A synthetic ledger fixture is never permission for real Ready/map launch.</summary>
internal sealed record SeasonFirstFortnightExecutionPermit(bool Approved, bool Synthetic, int Maximum, string? DecisionReference)
{
    internal void RequireRealLaunch()
    {
        if (!Approved || Synthetic || Maximum is < 1 or > 300 || string.IsNullOrWhiteSpace(DecisionReference))
            throw new InvalidOperationException("F01 timed-start budget is not confirmed; do not enqueue or launch a map.");
    }
}
