using System.Globalization;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Mail;
using Google.Protobuf;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class MailTemplateEncodingTests
{
    [Fact]
    public void Mail_metadata_uses_appended_typed_fields_and_preserves_raw_arguments()
    {
        const string reason = "  Fire  Gold: 装备 {amount}\n管理员原文  ";
        var dto = new MailItemResponse(Guid.NewGuid(), "原标题", "原正文", "Game Admin", DateTimeOffset.UnixEpoch,
            null, false, false, [], "Original title", "Original body", "item_reclamation",
            [new("kind", "Gold"), new("amount", "7"), new("reason", reason)], "admin");
        var message = HttpDtoMapper.FromDto(Wire.MailItemResponse.Descriptor, dto);
        HttpDtoMapper.Validate(message);
        var wire = Wire.MailItemResponse.Parser.ParseFrom(message.ToByteArray());
        Assert.Equal(dto.Title, wire.Title);
        Assert.Equal(dto.Body, wire.Body);
        Assert.Equal(dto.TitleEn, wire.TitleEn);
        Assert.Equal(dto.BodyEn, wire.BodyEn);
        Assert.Equal("item_reclamation", wire.TemplateId);
        Assert.Equal("admin", wire.SenderRole);
        Assert.Equal(reason, Assert.Single(wire.TemplateArgs, argument => argument.Key == "reason").Value);
        var decoded = Assert.IsType<MailItemResponse>(HttpDtoMapper.ToDto(wire, typeof(MailItemResponse)));
        Assert.Equal(reason, Assert.Single(decoded.TemplateArgs!, argument => argument.Key == "reason").Value);
        Assert.Equal(dto.TemplateArgs!.Select(argument => argument.Key), decoded.TemplateArgs!.Select(argument => argument.Key));
        Assert.Equal("template_id", Wire.MailItemResponse.Descriptor.FindFieldByNumber(12).Name);
        Assert.Equal("template_args", Wire.MailItemResponse.Descriptor.FindFieldByNumber(13).Name);
        Assert.Equal("sender_role", Wire.MailItemResponse.Descriptor.FindFieldByNumber(14).Name);
        Assert.Equal("body_en", Wire.MailItemResponse.Descriptor.FindFieldByNumber(11).Name);
    }

    [Fact]
    public void Legacy_payload_has_no_template_or_role_and_keeps_original_copy()
    {
        var wire = new Wire.MailItemResponse
        {
            Id = Guid.NewGuid().ToString("D"), Title = "Legacy title", Body = "Fire Gold 装备",
            Sender = "Custom sender", SentAt = DateTimeOffset.UnixEpoch.ToString("O", CultureInfo.InvariantCulture),
            TitleEn = "Legacy English title", BodyEn = "Legacy English body"
        };
        Assert.False(wire.HasTemplateId);
        Assert.False(wire.HasSenderRole);
        var dto = Assert.IsType<MailItemResponse>(HttpDtoMapper.ToDto(wire, typeof(MailItemResponse)));
        Assert.Null(dto.TemplateId);
        Assert.Null(dto.SenderRole);
        Assert.Empty(dto.TemplateArgs!);
        Assert.Equal(wire.Body, dto.Body);
        Assert.Equal(wire.BodyEn, dto.BodyEn);
        var encoded = Assert.IsType<Wire.MailItemResponse>(HttpDtoMapper.FromDto(Wire.MailItemResponse.Descriptor, dto));
        Assert.False(encoded.HasTemplateId);
        Assert.False(encoded.HasSenderRole);
        Assert.Empty(encoded.TemplateArgs);
    }

    [Fact]
    public void Duplicate_argument_keys_are_rejected_without_case_folding_raw_values()
    {
        var wire = new Wire.MailItemResponse
        {
            Id = Guid.NewGuid().ToString("D"), SentAt = DateTimeOffset.UnixEpoch.ToString("O", CultureInfo.InvariantCulture)
        };
        wire.TemplateArgs.Add(new Wire.MailTemplateArgument { Key = "reason", Value = "first" });
        wire.TemplateArgs.Add(new Wire.MailTemplateArgument { Key = "reason", Value = "second" });
        Assert.Throws<ArgumentException>(() => HttpDtoMapper.ToDto(wire, typeof(MailItemResponse)));
    }

    [Fact]
    public void Legacy_reader_can_skip_new_fields_and_still_read_old_title_and_body()
    {
        var dto = new MailItemResponse(Guid.NewGuid(), "Original", "Keep original", "System", DateTimeOffset.UnixEpoch,
            null, false, false, [], "English", "English body", "seed_gold", [], "system");
        var bytes = HttpDtoMapper.FromDto(Wire.MailItemResponse.Descriptor, dto).ToByteArray();
        using var input = new CodedInputStream(bytes);
        var oldFields = new Dictionary<int, string>();
        uint tag;
        while ((tag = input.ReadTag()) != 0)
        {
            var number = WireFormat.GetTagFieldNumber(tag);
            if (number is 1 or 2 or 3 or 4 or 5 or 10 or 11) oldFields[number] = input.ReadString();
            else input.SkipLastField();
        }
        Assert.Equal(dto.Title, oldFields[2]);
        Assert.Equal(dto.Body, oldFields[3]);
        Assert.Equal(dto.TitleEn, oldFields[10]);
        Assert.Equal(dto.BodyEn, oldFields[11]);
    }
}
