using FantasyCard.Contracts.Http;
using Google.Protobuf;

namespace FantasyCard.Server.ProtobufHttp;

/// <summary>Preflight a write response inside its transaction, before committing any rewards.</summary>
public static class GameResponseBudget
{
    public static void EnsureFits(string messageName, object response)
    {
        try
        {
            var message = HttpDtoMapper.FromDto(HttpProtocolRegistry.Message(messageName), response);
            HttpDtoMapper.Validate(message);
            if (message.CalculateSize() > HttpProtocolRegistry.MaximumBodyBytes)
                throw new InvalidDataException("Response body limit exceeded.");
        }
        catch (InvalidDataException exception)
        {
            throw new BadHttpRequestException("The operation response would exceed the supported HTTP budget. Claim fewer mails individually.", 413, exception);
        }
    }
}
