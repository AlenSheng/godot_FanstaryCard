using System.Collections;
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
        var message = (IMessage)Activator.CreateInstance(descriptor.ClrType)!;
        if (value is null) return message;
        // Existing persistence DTOs contain JSON, but the wire always contains named typed fields.
        if (descriptor.Name == "ShopProductPayload" && value is string text)
        {
            using var document = JsonDocument.Parse(text);
            return FromDto(descriptor, document.RootElement);
        }
        foreach (var field in descriptor.Fields.InFieldNumberOrder())
        {
            object? source = wrapItems && field.Name == "items" ? value : Read(value, field.Name);
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
        var constructor = dtoType.GetConstructors().OrderByDescending(c => c.GetParameters().Length).First();
        var arguments = constructor.GetParameters().Select(parameter =>
        {
            var field = message.Descriptor.Fields.InFieldNumberOrder().FirstOrDefault(f => SameName(f.Name, parameter.Name!));
            if (field is null || (field.HasPresence && !field.Accessor.HasValue(message)))
                return parameter.HasDefaultValue ? parameter.DefaultValue : Default(parameter.ParameterType);
            var source = field.Accessor.GetValue(message);
            if (field.IsRepeated)
            {
                var itemType = parameter.ParameterType.GetGenericArguments()[0];
                var items = ((IEnumerable)source).Cast<object>().Select(item => FromWire(item, itemType)).ToArray();
                var array = Array.CreateInstance(itemType, items.Length);
                for (var i = 0; i < items.Length; i++) array.SetValue(items[i], i);
                return array;
            }
            return FromWire(source, parameter.ParameterType);
        }).ToArray();
        return constructor.Invoke(arguments);
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

    private static object? Read(object source, string name)
    {
        if (source is JsonElement element)
        {
            if (element.ValueKind != JsonValueKind.Object) return null;
            foreach (var property in element.EnumerateObject())
                if (SameName(property.Name, name)) return property.Value.ValueKind == JsonValueKind.Null ? null : property.Value;
            return null;
        }
        var propertyInfo = source.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .FirstOrDefault(p => SameName(p.Name, name) || (name == "read" && p.Name == "IsRead") || (name == "claimed" && p.Name == "IsClaimed"));
        return propertyInfo?.GetValue(source);
    }

    private static bool SameName(string a, string b) => string.Equals(a.Replace("_", "", StringComparison.Ordinal), b.Replace("_", "", StringComparison.Ordinal), StringComparison.OrdinalIgnoreCase);

    public static void Validate(IMessage message, int depth = 0)
    {
        ArgumentNullException.ThrowIfNull(message);
        if (depth > HttpProtocolRegistry.MaximumDepth) throw new InvalidDataException("HTTP protobuf nesting limit.");
        foreach (var field in message.Descriptor.Fields.InFieldNumberOrder())
        {
            var value = field.Accessor.GetValue(message);
            if (field.IsRepeated && ((ICollection)value).Count > HttpProtocolRegistry.MaximumCollectionItems)
                throw new InvalidDataException("HTTP protobuf collection limit.");
            IEnumerable<object?> values = field.IsRepeated ? ((IEnumerable)value).Cast<object?>() : [value];
            foreach (var item in values)
            {
                if (item is string text && Encoding.UTF8.GetByteCount(text) > HttpProtocolRegistry.MaximumStringBytes)
                    throw new InvalidDataException("HTTP protobuf string limit.");
                if (item is IMessage nested) Validate(nested, depth + 1);
            }
        }
    }
}
