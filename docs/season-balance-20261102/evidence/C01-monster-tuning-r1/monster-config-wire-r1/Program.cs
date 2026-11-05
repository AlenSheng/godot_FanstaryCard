using System.Text.Json;
using System.Security.Cryptography;
using FantasyCard.Contracts.Configuration;
using FantasyCard.Contracts.Http;
using FantasyCard.Domain.Configuration;
if(args.Length!=2||Directory.Exists(args[0]))throw new InvalidOperationException("New owned output and original archive required.");
Directory.CreateDirectory(args[0]);var cases=new List<object>();
foreach(var (name,catalog) in new[]{("old14",GameConfigCatalog.Load(File.ReadAllBytes(args[1]))),("current15",GameConfigCatalog.Current)})
{
    var bundle=catalog.ExportPublishedBytes();var contract=HttpProtocolRegistry.Find("GET","/api/v1/config/"+catalog.Version)!;
    var envelope=HttpDtoMapper.EncodeResponse(contract,new PublishedConfigurationResponse(catalog.Version,catalog.ContentHash,bundle));
    File.WriteAllBytes(Path.Combine(args[0],name+".bundle"),bundle);File.WriteAllBytes(Path.Combine(args[0],name+".envelope"),envelope);
    cases.Add(new{name,version=catalog.Version,hash=catalog.ContentHash,bundle_sha256=Convert.ToHexStringLower(SHA256.HashData(bundle)),envelope_sha256=Convert.ToHexStringLower(SHA256.HashData(envelope))});
}
File.WriteAllText(Path.Combine(args[0],"cases.json"),JsonSerializer.Serialize(cases,new JsonSerializerOptions{WriteIndented=true}));Console.WriteLine("Encoded original14 and current15 typed configuration responses.");
