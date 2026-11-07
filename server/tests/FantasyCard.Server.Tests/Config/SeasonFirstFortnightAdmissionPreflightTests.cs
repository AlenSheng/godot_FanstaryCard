using System.Text.Json;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Budget/journal preflight only. Poison backend dependencies ensure no map path can run.</summary>
public sealed class SeasonFirstFortnightAdmissionPreflightTests
{
    private static readonly JsonSerializerOptions EvidenceJson = new() { WriteIndented = true };
    public static bool Enabled => Environment.GetEnvironmentVariable("FANTASYCARD_RUN_F01_ADMISSION_PREFLIGHT") == "1";

    [Fact(Skip = "Explicit F01 unapproved launch guard, no backend or gameplay.", SkipUnless = nameof(Enabled))]
    public async Task PendingAndSyntheticPermitsStopBeforeBackendOrJournalCreation()
    {
        var output = Output("permit-guards");
        var actor = SeasonFirstFortnightInputsTests.DeclareActors().First();
        var caseId = actor.Id + "-D01-A1";
        var now = new DateTimeOffset(2026, 11, 1, 1, 0, 0, TimeSpan.Zero);
        var path = Path.Combine(output, "must-not-be-created.jsonl");
        var journal = new SeasonFirstFortnightAttemptJournal(path, 300, new HashSet<string>(StringComparer.Ordinal) { caseId });
        foreach (var permit in new[]
                 {
                     new SeasonFirstFortnightExecutionPermit(false, false, 300, null),
                     new SeasonFirstFortnightExecutionPermit(true, true, 300, "synthetic-unit-fixture")
                 })
        {
            // Any backend dereference would produce the wrong exception and fail this assertion.
            var controller = new SeasonFirstFortnightAdmissionController(null!, null!, null!, null!, null!,
                new SeasonFirstFortnightTimeProvider(now), permit, journal);
            await Assert.ThrowsAsync<InvalidOperationException>(() => controller.AdmitAsync(caseId, actor,
                Guid.NewGuid(), Guid.NewGuid(), now, TestContext.Current.CancellationToken));
            Assert.False(File.Exists(path));
        }
        Write("permit-guards.original.json", new { actual_backend_calls = 0, journal_created = false,
            pending_permit_rejected = true, synthetic_permit_rejected = true, actual_gameplay_starts = 0 });
    }

    [Fact(Skip = "Explicit synthetic ledger test, not actual gameplay authority.", SkipUnless = nameof(Enabled))]
    public void DurableStartSurvivesReopenAndCannotBeRetriedOrResetPastItsMaximum()
    {
        var path = Path.Combine(Output("durable-ledger"), "synthetic-only.jsonl");
        var cases = new HashSet<string>(StringComparer.Ordinal) { "case-a", "case-b", "case-c" };
        var journal = new SeasonFirstFortnightAttemptJournal(path, 2, cases);
        var now = new DateTimeOffset(2026, 11, 1, 1, 0, 0, TimeSpan.Zero);
        Assert.Equal(1, journal.Reserve("case-a", "synthetic-actor", Guid.NewGuid(), now, syntheticLedgerOnly: true));
        journal.Phase("case-a", "interrupted", new { stage = "synthetic-only", no_backend_called = true });
        var reopened = new SeasonFirstFortnightAttemptJournal(path, 2, cases);
        Assert.Throws<InvalidOperationException>(() => reopened.Reserve("case-a", "synthetic-actor", Guid.NewGuid(), now, syntheticLedgerOnly: true));
        Assert.Equal(2, reopened.Reserve("case-b", "synthetic-actor", Guid.NewGuid(), now, syntheticLedgerOnly: true));
        var bytes = File.ReadAllBytes(path);
        Assert.Throws<InvalidOperationException>(() => reopened.Reserve("case-c", "synthetic-actor", Guid.NewGuid(), now, syntheticLedgerOnly: true));
        Assert.Throws<InvalidOperationException>(() => reopened.Phase("case-a", "started", new { invalid = true }));
        Assert.Equal(bytes, File.ReadAllBytes(path));
        var rows = File.ReadAllLines(path).Select(line => JsonDocument.Parse(line)).ToArray();
        try
        {
            Assert.Equal(3, rows.Length);
            Assert.Equal(2, rows.Count(row => row.RootElement.GetProperty("payload").GetProperty("kind").GetString() == "started"));
            Assert.All(rows.Where(row => row.RootElement.GetProperty("payload").GetProperty("kind").GetString() == "started"),
                row => Assert.True(row.RootElement.GetProperty("payload").GetProperty("detail").GetProperty("syntheticLedgerOnly").GetBoolean()));
        }
        finally { foreach (var row in rows) row.Dispose(); }
        Write("durable-ledger.original.json", new { synthetic_started_records = 2, interrupted_record_retained = true,
            reopen_does_not_reset = true, duplicate_or_exhausted_starts_rejected = true, actual_gameplay_starts = 0 });
    }

    [Fact(Skip = "Explicit corruption copies, no gameplay or changes to previous evidence.", SkipUnless = nameof(Enabled))]
    public void ModifiedOrPartialJournalCopiesAreRejectedWithoutRepair()
    {
        var output = Output("corrupt-copies");
        var original = Path.Combine(output, "original-synthetic.jsonl");
        var cases = new HashSet<string>(StringComparer.Ordinal) { "case-a", "case-b" };
        var journal = new SeasonFirstFortnightAttemptJournal(original, 2, cases);
        var now = new DateTimeOffset(2026, 11, 1, 1, 0, 0, TimeSpan.Zero);
        journal.Reserve("case-a", "synthetic-actor", Guid.NewGuid(), now, syntheticLedgerOnly: true);
        var originalBytes = File.ReadAllBytes(original);
        var changed = Path.Combine(output, "modified-copy.jsonl");
        File.WriteAllText(changed, File.ReadAllText(original).Replace("synthetic-actor", "changed-actor", StringComparison.Ordinal));
        var changedBytes = File.ReadAllBytes(changed);
        Assert.Throws<InvalidDataException>(() => new SeasonFirstFortnightAttemptJournal(changed, 2, cases)
            .Reserve("case-b", "synthetic-actor", Guid.NewGuid(), now, syntheticLedgerOnly: true));
        Assert.Equal(changedBytes, File.ReadAllBytes(changed));
        var partial = Path.Combine(output, "partial-copy.jsonl");
        File.WriteAllText(partial, File.ReadAllText(original) + "{");
        var partialBytes = File.ReadAllBytes(partial);
        Assert.Throws<InvalidDataException>(() => new SeasonFirstFortnightAttemptJournal(partial, 2, cases)
            .Reserve("case-b", "synthetic-actor", Guid.NewGuid(), now, syntheticLedgerOnly: true));
        Assert.Equal(partialBytes, File.ReadAllBytes(partial));
        Assert.Equal(originalBytes, File.ReadAllBytes(original));
        Write("corrupt-copies.original.json", new { original_unchanged = true, changed_payload_rejected = true,
            incomplete_tail_rejected = true, copies_not_repaired = true, actual_gameplay_starts = 0 });
    }

    private static string Output(string suffix)
    {
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_F01_ADMISSION_OUTPUT")
            ?? throw new InvalidOperationException("New owned F01 admission preflight output required.");
        var path = Path.Combine(output, suffix);
        Assert.False(Directory.Exists(path));
        Directory.CreateDirectory(path);
        return path;
    }

    private static void Write(string name, object value)
    {
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_F01_ADMISSION_OUTPUT")!;
        var path = Path.Combine(output, name);
        Assert.False(File.Exists(path));
        File.WriteAllText(path, JsonSerializer.Serialize(value, EvidenceJson));
    }
}
