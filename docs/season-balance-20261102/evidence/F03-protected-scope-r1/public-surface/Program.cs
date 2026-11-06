using System.Globalization;
using System.Reflection;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

static string Hash(string text) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
static string TypeName(Type type)
{
    if (type.IsGenericParameter) return (type.DeclaringMethod is null ? "!" : "!!") + type.GenericParameterPosition;
    if (type.IsByRef) return TypeName(type.GetElementType()!) + "&";
    if (type.IsPointer) return TypeName(type.GetElementType()!) + "*";
    if (type.IsArray) return TypeName(type.GetElementType()!) + "[" + new string(',', type.GetArrayRank() - 1) + "]";
    if (type.IsGenericType && !type.IsGenericTypeDefinition)
        return TypeName(type.GetGenericTypeDefinition()) + "<" + string.Join(",", type.GetGenericArguments().Select(TypeName)) + ">";
    return type.IsVisible ? type.FullName ?? type.Name : "#internal";
}
static string Value(object? value) => value is null ? "null" : value is Type type ? TypeName(type) : value.GetType().FullName + ":" + Convert.ToString(value, CultureInfo.InvariantCulture);
static string Attributes(MemberInfo member) => string.Join(";", member.GetCustomAttributesData()
    .Where(a => a.AttributeType.Namespace == "System.Text.Json.Serialization")
    .Select(a => a.AttributeType.FullName + "(" + string.Join(",", a.ConstructorArguments.Select(v => Value(v.Value))) + ")[" +
        string.Join(",", a.NamedArguments.Select(v => v.MemberName + "=" + Value(v.TypedValue.Value))) + "]").Order(StringComparer.Ordinal));
static string Parameters(MethodBase method) => string.Join(",", method.GetParameters().Select(p =>
    p.Name + ":" + TypeName(p.ParameterType) + ":" + p.IsIn + ":" + p.IsOut + ":" + p.IsOptional + ":" +
    (p.HasDefaultValue ? Hash(Value(p.DefaultValue)) : "required")));

if (args.Length != 2) return 2;
var directory = Path.GetFullPath(args[0]);
var context = new LocalContext(directory);
var signatures = new SortedSet<string>(StringComparer.Ordinal);
var counts = new Dictionary<string, object>();
foreach (var name in new[] { "FantasyCard.Contracts", "FantasyCard.Domain", "FantasyCard.Server" })
{
    var assembly = context.LoadFromAssemblyPath(Path.Combine(directory, name + ".dll"));
    var types = assembly.GetTypes();
    var visible = types.Where(t => t.IsVisible).OrderBy(t => t.FullName, StringComparer.Ordinal).ToArray();
    var before = signatures.Count;
    foreach (var type in visible)
    {
        var key = name + ":" + TypeName(type);
        signatures.Add(key + "|type|" + type.Attributes + "|" + (type.BaseType is null ? "" : TypeName(type.BaseType)) + "|" + Attributes(type));
        foreach (var field in type.GetFields(BindingFlags.DeclaredOnly | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
            .Where(f => f.IsPublic || f.IsFamily || f.IsFamilyOrAssembly))
            signatures.Add(key + "|field|" + field.Name + "|" + TypeName(field.FieldType) + "|" + field.Attributes + "|" +
                (field.IsLiteral ? Hash(Value(field.GetRawConstantValue())) : "not-literal") + "|" + Attributes(field));
        foreach (var property in type.GetProperties(BindingFlags.DeclaredOnly | BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static))
            signatures.Add(key + "|property|" + property.Name + "|" + TypeName(property.PropertyType) + "|" + Attributes(property));
        foreach (var method in type.GetMethods(BindingFlags.DeclaredOnly | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
            .Where(m => m.IsPublic || m.IsFamily || m.IsFamilyOrAssembly))
            signatures.Add(key + "|method|" + method.Name + "|" + method.Attributes + "|" + TypeName(method.ReturnType) + "|" + Parameters(method));
        foreach (var constructor in type.GetConstructors(BindingFlags.DeclaredOnly | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
            .Where(m => m.IsPublic || m.IsFamily || m.IsFamilyOrAssembly))
            signatures.Add(key + "|ctor|" + constructor.Attributes + "|" + Parameters(constructor));
    }
    // These names and parameter names are reflected by Minimal API; ignore generated lambdas.
    foreach (var type in types.Where(t => t.FullName == "Program" || t.FullName?.Contains("Endpoints", StringComparison.Ordinal) == true))
    {
        if (type.Name.StartsWith('<')) continue;
        foreach (var method in type.GetMethods(BindingFlags.DeclaredOnly | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static)
            .Where(m => !m.Name.StartsWith('<')))
            signatures.Add(name + ":reflection:" + type.FullName + "|" + method.Name + "|" + Parameters(method));
    }
    counts.Add(name, new { exportedTypes = visible.Length, signaturesAdded = signatures.Count - before });
}
var rows = signatures.ToArray();
File.WriteAllText(args[1], JsonSerializer.Serialize(new { counts, signatures = rows, hash = Hash(string.Join("\n", rows)), scope = "Public/protected API, literal/default hashes, JSON attributes and Minimal API named parameters only; no method bodies executed." }, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine(JsonSerializer.Serialize(new { signatures = rows.Length, hash = Hash(string.Join("\n", rows)), counts }));
return 0;

sealed class LocalContext(string directory) : AssemblyLoadContext(isCollectible: true)
{
    protected override Assembly? Load(AssemblyName name)
    {
        var path = Path.Combine(directory, name.Name + ".dll");
        return File.Exists(path) ? LoadFromAssemblyPath(path) : null;
    }
}
