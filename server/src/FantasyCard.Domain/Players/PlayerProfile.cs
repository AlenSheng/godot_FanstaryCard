using System.Text;

namespace FantasyCard.Domain.Players;

public sealed class PlayerProfile
{
    public const int MinDisplayNameLength = 2;
    public const int MaxDisplayNameLength = 20;

    private PlayerProfile(
        Guid userId,
        string displayName,
        HeroClass? selectedClass,
        long version,
        DateTimeOffset createdAt,
        DateTimeOffset updatedAt)
    {
        UserId = userId;
        DisplayName = displayName;
        SelectedClass = selectedClass;
        Version = version;
        CreatedAt = createdAt;
        UpdatedAt = updatedAt;
    }

    public Guid UserId { get; }

    public string DisplayName { get; private set; }

    public HeroClass? SelectedClass { get; private set; }

    public long Version { get; private set; }

    public DateTimeOffset CreatedAt { get; }

    public DateTimeOffset UpdatedAt { get; private set; }

    public static PlayerProfile Create(Guid userId, string? displayName, DateTimeOffset now)
    {
        if (userId == Guid.Empty)
        {
            throw new DomainValidationException("User id cannot be empty.");
        }

        return new PlayerProfile(userId, NormalizeDisplayName(displayName), null, 1, now, now);
    }

    public static PlayerProfile Rehydrate(
        Guid userId,
        string displayName,
        HeroClass? selectedClass,
        long version,
        DateTimeOffset createdAt,
        DateTimeOffset updatedAt) =>
        new(userId, displayName, selectedClass, version, createdAt, updatedAt);

    public void Update(string? displayName, HeroClass? selectedClass, DateTimeOffset now)
    {
        if (displayName is not null)
        {
            DisplayName = NormalizeDisplayName(displayName);
        }

        if (selectedClass is not null)
        {
            if (!Enum.IsDefined(selectedClass.Value))
            {
                throw new DomainValidationException("Unknown hero class.");
            }

            SelectedClass = selectedClass;
        }

        Version++;
        UpdatedAt = now;
    }

    public static string NormalizeDisplayName(string? displayName)
    {
        if (string.IsNullOrWhiteSpace(displayName))
        {
            throw new DomainValidationException(
                $"Display name must contain {MinDisplayNameLength}-{MaxDisplayNameLength} characters.");
        }

        var normalized = displayName.Trim().Normalize(NormalizationForm.FormKC);
        var runeCount = normalized.EnumerateRunes().Count();

        if (runeCount is < MinDisplayNameLength or > MaxDisplayNameLength)
        {
            throw new DomainValidationException(
                $"Display name must contain {MinDisplayNameLength}-{MaxDisplayNameLength} characters.");
        }

        if (normalized.EnumerateRunes().Any(Rune.IsControl))
        {
            throw new DomainValidationException("Display name cannot contain control characters.");
        }

        return normalized;
    }
}
