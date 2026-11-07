using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json;

var rows=new List<object>();
foreach(var path in args.Skip(1))
{
    using var stream=File.OpenRead(path);
    using var pe=new PEReader(stream);
    var metadata=pe.GetMetadataReader();
    var types=new Names();
    foreach(var handle in metadata.TypeDefinitions)
    {
        var definition=metadata.GetTypeDefinition(handle);
        var fullName=types.GetTypeFromDefinition(metadata,handle,0);
        foreach(var methodHandle in definition.GetMethods())
        {
            var method=metadata.GetMethodDefinition(methodHandle);
            foreach(var attributeHandle in method.GetCustomAttributes())
            {
                var attribute=metadata.GetCustomAttribute(attributeHandle);
                var parent=attribute.Constructor.Kind==HandleKind.MemberReference
                    ? metadata.GetMemberReference((MemberReferenceHandle)attribute.Constructor).Parent
                    : metadata.GetMethodDefinition((MethodDefinitionHandle)attribute.Constructor).GetDeclaringType();
                var name=parent.Kind==HandleKind.TypeReference
                    ? types.GetTypeFromReference(metadata,(TypeReferenceHandle)parent,0)
                    : parent.Kind==HandleKind.TypeDefinition ? types.GetTypeFromDefinition(metadata,(TypeDefinitionHandle)parent,0) : parent.Kind.ToString();
                if(!name.EndsWith("FactAttribute",StringComparison.Ordinal) && !name.EndsWith("TheoryAttribute",StringComparison.Ordinal)) continue;
                var named=new Dictionary<string,object?>();string? error=null;
                try
                {
                    foreach(var item in attribute.DecodeValue(types).NamedArguments) named[item.Name!]=item.Value;
                }
                catch(Exception exception){error=exception.GetType().Name+": "+exception.Message;}
                rows.Add(new{assembly=Path.GetFileName(path),assembly_sha256=Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path))),
                    type=fullName,method=metadata.GetString(method.Name),attribute=name,named,error,
                    attribute_blob_sha256=Convert.ToHexStringLower(SHA256.HashData(metadata.GetBlobBytes(attribute.Value)))});
            }
        }
    }
}
File.WriteAllText(args[0],JsonSerializer.Serialize(new{method_definitions=rows.Count,rows,metadata_only=true,test_methods_invoked=0,attribute_instances_created=0,source_assemblies_loaded_for_execution=false},new JsonSerializerOptions{WriteIndented=true}));
return 0;

sealed class Names : ICustomAttributeTypeProvider<string>
{
    public string GetPrimitiveType(PrimitiveTypeCode code)=>code.ToString();
    public string GetSystemType()=>"System.Type";
    public bool IsSystemType(string type)=>type=="System.Type";
    public string GetSZArrayType(string elementType)=>elementType+"[]";
    public string GetTypeFromDefinition(MetadataReader reader,TypeDefinitionHandle handle,byte rawTypeKind)
    {var type=reader.GetTypeDefinition(handle);return reader.GetString(type.Namespace)+"."+reader.GetString(type.Name);}
    public string GetTypeFromReference(MetadataReader reader,TypeReferenceHandle handle,byte rawTypeKind)
    {var type=reader.GetTypeReference(handle);return reader.GetString(type.Namespace)+"."+reader.GetString(type.Name);}
    public string GetTypeFromSerializedName(string name)=>name;
    public PrimitiveTypeCode GetUnderlyingEnumType(string type)=>PrimitiveTypeCode.Int32;
}
