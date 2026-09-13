using System.Text.Json.Serialization;

namespace FantasyCard.Contracts.Mail;

public sealed record MailAttachmentResponse(
    string Kind,
    long Amount,
    string? ItemId = null,
    string? HeroClass = null,
    string? EffectAffix = null,
    string? SecondaryTrait = null);

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
    IReadOnlyList<MailAttachmentResponse> Attachments);

public sealed record MailListResponse(
    IReadOnlyList<MailItemResponse> Items,
    int UnreadCount);

public sealed record MailClaimResponse(
    Guid MailId,
    bool AlreadyClaimed,
    IReadOnlyList<MailAttachmentResponse> Granted);

public sealed record MailClaimAllResponse(
    int MailCount,
    int AttachmentCount);

public sealed record MailDeleteResponse(
    int DeletedCount);
