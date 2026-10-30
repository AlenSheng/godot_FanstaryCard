using System.Text.Json.Serialization;

namespace FantasyCard.Contracts.Mail;

public sealed record MailAttachmentResponse(
    string Kind,
    long Amount,
    string? ItemId = null,
    string? HeroClass = null,
    string? EffectAffix = null,
    string? SecondaryTrait = null);

public sealed record MailTemplateArgumentResponse(string Key, string Value);

public sealed record MailItemResponse(
    Guid Id,
    string Title,
    string Body,
    string Sender,
    DateTimeOffset SentAt,
    DateTimeOffset? ExpiresAt,
    [property: JsonPropertyName("read")]
    bool IsRead,
    [property: JsonPropertyName("claimed")]
    bool IsClaimed,
    IReadOnlyList<MailAttachmentResponse> Attachments,
    string TitleEn = "",
    string BodyEn = "",
    string? TemplateId = null,
    IReadOnlyList<MailTemplateArgumentResponse>? TemplateArgs = null,
    string? SenderRole = null)
{
    public IReadOnlyList<MailTemplateArgumentResponse>? TemplateArgs { get; init; } = ValidateArguments(TemplateArgs);

    private static IReadOnlyList<MailTemplateArgumentResponse>? ValidateArguments(IReadOnlyList<MailTemplateArgumentResponse>? arguments)
    {
        if (arguments is null) return null;
        var keys = new HashSet<string>(StringComparer.Ordinal);
        foreach (var argument in arguments)
            if (argument is null || string.IsNullOrEmpty(argument.Key) || argument.Value is null || !keys.Add(argument.Key))
                throw new ArgumentException("Mail template arguments require unique, nonempty keys and nonnull values.", nameof(arguments));
        return arguments;
    }
}

public sealed record MailListResponse(
    IReadOnlyList<MailItemResponse> Items,
    int UnreadCount);

public sealed record MailClaimResponse(
    Guid MailId,
    bool AlreadyClaimed,
    IReadOnlyList<MailAttachmentResponse> Granted);

public sealed record MailClaimAllResponse(
    int MailCount,
    int AttachmentCount,
    IReadOnlyList<MailClaimResponse>? Claims = null);

public sealed record MailDeleteResponse(
    int DeletedCount);
