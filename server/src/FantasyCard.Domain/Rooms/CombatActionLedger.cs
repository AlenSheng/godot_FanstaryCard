using System.Globalization;
using System.Buffers;
using System.Security.Cryptography;
using System.Text;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Rooms;

public sealed record CombatActionReceipt(long Sequence, string ActionId, string RequestHash, TimeSpan AppliedAt, CombatResolution Resolution);
public sealed record CombatActionStatus(long NextSequence, long RemainingMs);
public sealed class CombatActionAlreadyAppliedException : Exception
{
    public CombatActionAlreadyAppliedException() : base("The old combat action was already sequenced; use the authoritative snapshot.") { }
}

/// <summary>The action ID embeds its sequence, so evicting a result never makes an old ID executable again.</summary>
internal sealed class CombatActionLedger
{
    public const int RetainedResults = 64;
    public static readonly TimeSpan MinimumInterval = TimeSpan.FromMilliseconds(500);
    private static readonly SearchValues<char> HexDigits = SearchValues.Create("0123456789abcdef");
    private readonly List<CombatActionReceipt> _receipts = [];
    public long LastSequence { get; private set; }
    public TimeSpan? LastSuccessfulAt { get; private set; }
    public IReadOnlyList<CombatActionReceipt> Capture() => _receipts.ToArray();
    public CombatActionStatus Status(TimeSpan elapsed) => new(LastSequence == long.MaxValue ? 0 : LastSequence + 1,
        LastSuccessfulAt is { } last ? Math.Clamp((long)Math.Ceiling((last + MinimumInterval - elapsed).TotalMilliseconds), 0, 500) : 0);
    public string NewId() => LastSequence == long.MaxValue
        ? throw new DomainValidationException("The combat action sequence is exhausted.")
        : (LastSequence + 1).ToString(CultureInfo.InvariantCulture) + ":" + Guid.NewGuid().ToString("N");

    public static bool TrySequence(string? id, out long sequence)
    {
        sequence = 0;
        if (id is null || id.Length is < 34 or > 53) return false;
        var split = id.IndexOf(':');
        if (split is < 1 or > 19 || id.Length - split - 1 != 32 ||
            !long.TryParse(id.AsSpan(0, split), NumberStyles.None, CultureInfo.InvariantCulture, out sequence) || sequence <= 0 ||
            !id.AsSpan(0, split).SequenceEqual(sequence.ToString(CultureInfo.InvariantCulture))) return false;
        return id.AsSpan(split + 1).IndexOfAnyExcept(HexDigits) < 0;
    }

    public bool IsHistorical(string? id) => TrySequence(id, out var sequence) && sequence <= LastSequence;

    public CombatResolution? Replay(string? id, string hash)
    {
        if (!TrySequence(id, out var sequence)) throw new DomainValidationException("combatActionId must be nextSequence:32-lowercase-hex.");
        if (sequence > LastSequence) return null;
        var receipt = _receipts.FirstOrDefault(value => value.Sequence == sequence);
        if (receipt is null) throw new CombatActionAlreadyAppliedException();
        if (receipt.ActionId != id || receipt.RequestHash != hash)
            throw new DomainValidationException("The combat action sequence was already used with another ID or payload.");
        return receipt.Resolution with { ActionReplayed = true };
    }

    public void ValidateNew(string? id, TimeSpan elapsed)
    {
        if (!TrySequence(id, out var sequence) || LastSequence == long.MaxValue || sequence != LastSequence + 1)
            throw new DomainValidationException("The next combat action sequence is required.");
        if (Status(elapsed).RemainingMs > 0)
            throw new DomainValidationException("Successful combat actions must be at least 500ms apart.");
    }

    public void Commit(string id, string hash, TimeSpan elapsed, CombatResolution resolution)
    {
        ValidateNew(id, elapsed);
        TrySequence(id, out var sequence);
        LastSequence = sequence; LastSuccessfulAt = elapsed;
        _receipts.Add(new(sequence, id, hash, elapsed, resolution));
        if (_receipts.Count > RetainedResults) _receipts.RemoveAt(0);
    }

    public void Restore(long sequence, TimeSpan? last, IReadOnlyList<CombatActionReceipt>? receipts, TimeSpan elapsed, Guid playerId, long revision)
    {
        var values = receipts?.ToArray() ?? [];
        if (sequence < 0 || values.Length > RetainedResults || sequence == 0 && (last is not null || values.Length != 0) ||
            sequence > 0 && (last is null || last.Value < TimeSpan.Zero || last.Value > elapsed ||
                last.Value > TimeSpan.MaxValue - MinimumInterval || values.Length == 0 || values[^1].Sequence != sequence || values[^1].AppliedAt != last.Value))
            throw new DomainValidationException("The combat action checkpoint is invalid.");
        long prior = sequence - values.Length;
        TimeSpan? priorTime = null;
        foreach (var value in values)
        {
            if (value.Sequence != ++prior || !TrySequence(value.ActionId, out var parsed) || parsed != value.Sequence ||
                value.RequestHash.Length != 64 || value.RequestHash.Any(c => !char.IsAsciiHexDigitLower(c)) ||
                value.AppliedAt < TimeSpan.Zero || value.AppliedAt > elapsed || priorTime is { } previous && value.AppliedAt - previous < MinimumInterval ||
                value.Resolution.AttackerId != playerId || value.Resolution.RoomRevision > revision ||
                value.Resolution.CombatActionId != value.ActionId || value.Resolution.ActionReplayed)
                throw new DomainValidationException("A retained combat action receipt is invalid.");
            priorTime = value.AppliedAt;
        }
        LastSequence = sequence; LastSuccessfulAt = last;
        _receipts.Clear(); _receipts.AddRange(values);
    }

    public static string Hash(Guid battleId, string targetId, IReadOnlyList<Guid> ids) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(
            battleId.ToString("D") + "\n" + targetId + "\n" + string.Join('\n', ids.Select(id => id.ToString("D"))))));
}
