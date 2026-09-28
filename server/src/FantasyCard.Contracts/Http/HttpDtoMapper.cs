using System.Collections;
using System.Collections.Concurrent;
using System.Linq.Expressions;
using System.Globalization;
using System.Reflection;
using System.Text;
using System.Text.Json;
using Google.Protobuf;
using Google.Protobuf.Reflection;

namespace FantasyCard.Contracts.Http;

/// <summary>Typed wire/domain boundary. Integer values never pass through JSON or double.</summary>
public static class HttpDtoMapper
{
    // Keys are application DTO types and immutable generated descriptors; no request data is cached.
    private static readonly ConcurrentDictionary<MessageDescriptor, MessageMetadata> Messages = new();
    private static readonly ConcurrentDictionary<Type, Dictionary<string, PropertyInfo>> Properties = new();
    private static readonly ConcurrentDictionary<(MessageDescriptor Descriptor, Type Type), ReadBinding[]> Readers = new();
    private static readonly ConcurrentDictionary<(MessageDescriptor Descriptor, Type Type), ConstructorMetadata> Constructors = new();

    private sealed record MessageMetadata(Func<IMessage> Create, FieldDescriptor[] Fields);
    private sealed record ReadBinding(FieldDescriptor Field, PropertyInfo? Property);
    private sealed record ParameterBinding(FieldDescriptor? Field, Type Type, Type? ItemType, object? DefaultValue);
    private sealed record ConstructorMetadata(ConstructorInfo Constructor, ParameterBinding[] Parameters);

    private static MessageMetadata Metadata(MessageDescriptor descriptor) => Messages.GetOrAdd(descriptor, static d =>
        new(Expression.Lambda<Func<IMessage>>(Expression.Convert(Expression.New(d.ClrType), typeof(IMessage))).Compile(),
            d.Fields.InFieldNumberOrder().ToArray()));

    private static Dictionary<string, PropertyInfo> PropertyMap(Type type) => Properties.GetOrAdd(type, static t =>
    {
        var result = new Dictionary<string, PropertyInfo>(StringComparer.OrdinalIgnoreCase);
        foreach (var property in t.GetProperties(BindingFlags.Public | BindingFlags.Instance))
        {
            result.TryAdd(Normalize(property.Name), property);
            if (property.Name == "IsRead") result.TryAdd("read", property);
            if (property.Name == "IsClaimed") result.TryAdd("claimed", property);
        }
        return result;
    });

    private static string Normalize(string name) => name.Replace("_", "", StringComparison.Ordinal);

    public static object DecodeRequest(HttpEndpointContract contract, byte[] bytes, Type dtoType)
    {
        ArgumentNullException.ThrowIfNull(contract);
        ArgumentNullException.ThrowIfNull(bytes);
        ArgumentNullException.ThrowIfNull(dtoType);
        if (bytes.Length > HttpProtocolRegistry.MaximumBodyBytes) throw new InvalidDataException("HTTP protobuf body is too large.");
        using var input = CodedInputStream.CreateWithLimits(new MemoryStream(bytes, false), HttpProtocolRegistry.MaximumBodyBytes, HttpProtocolRegistry.MaximumDepth);
        var message = contract.RequestDescriptor.Parser.ParseFrom(input);
        Validate(message, 0);
        return ToDto(message, dtoType);
    }

    public static byte[] EncodeResponse(HttpEndpointContract contract, object? value)
    {
        ArgumentNullException.ThrowIfNull(contract);
        var message = FromDto(contract.ResponseDescriptor, value, contract.UnwrapItems);
        Validate(message, 0);
        if (message.CalculateSize() > HttpProtocolRegistry.MaximumBodyBytes) throw new InvalidDataException("HTTP protobuf response is too large.");
        return message.ToByteArray();
    }

    public static IMessage FromDto(MessageDescriptor descriptor, object? value, bool wrapItems = false)
    {
        ArgumentNullException.ThrowIfNull(descriptor);
        var metadata = Metadata(descriptor);
        var message = metadata.Create();
        if (value is null) return message;
        // Existing persistence DTOs contain JSON, but the wire always contains named typed fields.
        if (descriptor.Name == "ShopProductPayload" && value is string text)
        {
            using var document = JsonDocument.Parse(text);
            return FromDto(descriptor, document.RootElement);
        }
        var bindings = Readers.GetOrAdd((descriptor, value.GetType()), static key =>
        {
            var properties = PropertyMap(key.Type);
            return Metadata(key.Descriptor).Fields.Select(field =>
                new ReadBinding(field, properties.GetValueOrDefault(Normalize(field.Name)))).ToArray();
        });
        foreach (var binding in bindings)
        {
            var field = binding.Field;
            object? source = wrapItems && field.Name == "items" ? value
                : value is JsonElement element ? ReadJson(element, field.Name) : binding.Property?.GetValue(value);
            if (source is null) continue;
            if (field.IsRepeated)
            {
                var destination = (IList)field.Accessor.GetValue(message);
                foreach (var item in Enumerate(source)) destination.Add(ToWire(field, item));
            }
            else field.Accessor.SetValue(message, ToWire(field, source));
        }
        return message;
    }

    public static object ToDto(IMessage message, Type dtoType)
    {
        ArgumentNullException.ThrowIfNull(message);
        ArgumentNullException.ThrowIfNull(dtoType);
        if (dtoType.IsInstanceOfType(message)) return message;
        var metadata = Constructors.GetOrAdd((message.Descriptor, dtoType), static key =>
        {
            var constructor = key.Type.GetConstructors().OrderByDescending(c => c.GetParameters().Length).First();
            var fields = Metadata(key.Descriptor).Fields.ToDictionary(f => Normalize(f.Name), StringComparer.OrdinalIgnoreCase);
            var parameters = constructor.GetParameters().Select(parameter =>
            {
                var field = fields.GetValueOrDefault(Normalize(parameter.Name!));
                return new ParameterBinding(field, parameter.ParameterType,
                    field?.IsRepeated == true ? parameter.ParameterType.GetGenericArguments()[0] : null,
                    parameter.HasDefaultValue ? parameter.DefaultValue : Default(parameter.ParameterType));
            }).ToArray();
            return new ConstructorMetadata(constructor, parameters);
        });
        var arguments = new object?[metadata.Parameters.Length];
        for (var i = 0; i < arguments.Length; i++)
        {
            var parameter = metadata.Parameters[i];
            var field = parameter.Field;
            if (field is null || (field.HasPresence && !field.Accessor.HasValue(message)))
            {
                arguments[i] = parameter.DefaultValue;
                continue;
            }
            var source = field.Accessor.GetValue(message);
            if (field.IsRepeated)
            {
                var items = (IList)source;
                var array = Array.CreateInstance(parameter.ItemType!, items.Count);
                for (var j = 0; j < items.Count; j++) array.SetValue(FromWire(items[j]!, parameter.ItemType!), j);
                arguments[i] = array;
            }
            else arguments[i] = FromWire(source, parameter.Type);
        }
        return metadata.Constructor.Invoke(arguments);
    }

    private static object? Default(Type type) => type.IsValueType ? Activator.CreateInstance(type) : null;
    private static object? FromWire(object value, Type type)
    {
        var nullable = Nullable.GetUnderlyingType(type);
        if (nullable is not null)
        {
            if (value is string empty && empty.Length == 0) return null;
            type = nullable;
        }
        if (value is IMessage nested) return ToDto(nested, type);
        if (type == typeof(Guid)) return Guid.Parse((string)value);
        if (type == typeof(DateTimeOffset)) return DateTimeOffset.Parse((string)value, CultureInfo.InvariantCulture);
        if (type.IsEnum) return Enum.Parse(type, (string)value, false);
        return Convert.ChangeType(value, type, CultureInfo.InvariantCulture);
    }

    private static object ToWire(FieldDescriptor field, object? value)
    {
        if (field.FieldType == FieldType.Message) return FromDto(field.MessageType, value);
        if (value is JsonElement element)
            value = element.ValueKind switch
            {
                JsonValueKind.String => element.GetString(),
                JsonValueKind.True => true,
                JsonValueKind.False => false,
                JsonValueKind.Number when field.FieldType == FieldType.Int64 => element.GetInt64(),
                JsonValueKind.Number when field.FieldType == FieldType.Int32 => element.GetInt32(),
                JsonValueKind.Number when field.FieldType == FieldType.String => element.GetRawText(),
                _ => throw new InvalidDataException($"Invalid persisted value for {field.FullName}.")
            };
        return field.FieldType switch
        {
            FieldType.String => value switch
            {
                null => "",
                DateTimeOffset date => date.ToString("O", CultureInfo.InvariantCulture),
                Guid guid => guid.ToString("D"),
                IFormattable number => number.ToString(null, CultureInfo.InvariantCulture),
                _ => value.ToString()!
            },
            FieldType.Int64 => Convert.ToInt64(value, CultureInfo.InvariantCulture),
            FieldType.Int32 => Convert.ToInt32(value, CultureInfo.InvariantCulture),
            FieldType.Bool => Convert.ToBoolean(value, CultureInfo.InvariantCulture),
            _ => throw new InvalidDataException($"Unsupported HTTP field {field.FullName}.")
        };
    }

    private static IEnumerable<object?> Enumerate(object value) => value is JsonElement element
        ? element.EnumerateArray().Select(e => (object?)e)
        : ((IEnumerable)value).Cast<object?>();

    private static JsonElement? ReadJson(JsonElement element, string name)
    {
        if (element.ValueKind != JsonValueKind.Object) return null;
        foreach (var property in element.EnumerateObject())
            if (SameName(property.Name, name)) return property.Value.ValueKind == JsonValueKind.Null ? null : property.Value;
        return null;
    }

    private static bool SameName(string a, string b)
    {
        // Compare snake/camel/Pascal case without allocating normalized strings per persisted field.
        var i = 0;
        var j = 0;
        while (true)
        {
            while (i < a.Length && a[i] == '_') i++;
            while (j < b.Length && b[j] == '_') j++;
            if (i == a.Length || j == b.Length) return i == a.Length && j == b.Length;
            if (char.ToUpperInvariant(a[i++]) != char.ToUpperInvariant(b[j++])) return false;
        }
    }

    public static void Validate(IMessage message, int depth = 0)
    {
        ArgumentNullException.ThrowIfNull(message);
        if (depth > HttpProtocolRegistry.MaximumDepth) throw new InvalidDataException("HTTP protobuf nesting limit.");
        foreach (var field in Metadata(message.Descriptor).Fields)
        {
            var value = field.Accessor.GetValue(message);
            if (field.IsRepeated)
            {
                var items = (IList)value;
                if (items.Count > HttpProtocolRegistry.MaximumCollectionItems)
                    throw new InvalidDataException("HTTP protobuf collection limit.");
                foreach (var item in items) ValidateValue(item, depth);
            }
            else ValidateValue(value, depth);
        }
    }

    private static void ValidateValue(object? item, int depth)
    {
        if (item is string text && Encoding.UTF8.GetByteCount(text) > HttpProtocolRegistry.MaximumStringBytes)
            throw new InvalidDataException("HTTP protobuf string limit.");
        if (item is IMessage nested) Validate(nested, depth + 1);
    }
}
