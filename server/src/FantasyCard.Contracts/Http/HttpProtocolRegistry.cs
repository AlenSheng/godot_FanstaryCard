using System.Text.Json;
using Google.Protobuf.Reflection;

namespace FantasyCard.Contracts.Http;

public sealed record HttpEndpointContract(string Method, string Path, string Request, string Response, bool UnwrapItems)
{
    public MessageDescriptor RequestDescriptor => HttpProtocolRegistry.Message(Request);
    public MessageDescriptor ResponseDescriptor => HttpProtocolRegistry.Message(Response);
}

public static class HttpProtocolRegistry
{
    public const string MediaType = "application/protobuf";
    public const int MaximumBodyBytes = 2 * 1024 * 1024;
    public const int MaximumDepth = 24;
    public const int MaximumCollectionItems = 4096;
    public const int MaximumStringBytes = 128 * 1024;
    public static IReadOnlyList<HttpEndpointContract> Endpoints { get; } = Load();

    public static MessageDescriptor Message(string name) =>
        V1.GameReflection.Descriptor.MessageTypes.FirstOrDefault(m => m.Name == name)
        ?? throw new InvalidDataException($"Unknown HTTP protobuf message '{name}'.");

    public static HttpEndpointContract? Find(string method, string path)
    {
        var segments = path.Split('?', 2)[0].Trim('/').Split('/');
        return Endpoints.FirstOrDefault(endpoint =>
        {
            if (!string.Equals(method, endpoint.Method, StringComparison.OrdinalIgnoreCase)) return false;
            var template = endpoint.Path.Trim('/').Split('/');
            if (template.Length != segments.Length) return false;
            for (var i = 0; i < template.Length; i++)
            {
                if (template[i].StartsWith('{') && template[i].EndsWith('}'))
                {
                    if (segments[i].Length == 0) return false;
                    if (template[i].EndsWith(":guid}", StringComparison.Ordinal) && !Guid.TryParse(segments[i], out _)) return false;
                }
                else if (!string.Equals(template[i], segments[i], StringComparison.OrdinalIgnoreCase)) return false;
            }
            return true;
        });
    }

    private static HttpEndpointContract[] Load()
    {
        using var stream = typeof(HttpProtocolRegistry).Assembly.GetManifestResourceStream("FantasyCard.HttpEndpoints.json")
            ?? throw new InvalidDataException("Missing HTTP endpoint registry.");
        using var document = JsonDocument.Parse(stream);
        return document.RootElement.GetProperty("endpoints").EnumerateArray().Select(e => new HttpEndpointContract(
            e.GetProperty("method").GetString()!, e.GetProperty("path").GetString()!,
            e.GetProperty("request").GetString()!, e.GetProperty("response").GetString()!,
            e.GetProperty("unwrap_items").GetBoolean())).ToArray();
    }
}
