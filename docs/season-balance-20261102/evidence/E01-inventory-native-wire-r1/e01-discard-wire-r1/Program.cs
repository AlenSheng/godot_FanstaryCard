using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Progression;
using Google.Protobuf;
using Wire = FantasyCard.Contracts.Http.V1;

if(args.Length!=1||Directory.Exists(args[0]))throw new InvalidOperationException("New output required.");
Directory.CreateDirectory(args[0]);var contract=HttpProtocolRegistry.Find("POST","/api/v1/inventory/discard")!;var cases=new List<object>();
foreach(var name in new[]{"active","legacy"})
{
    var season=name=="active"?"original":null;var id=Guid.Parse("10000000-0000-0000-0000-000000000001");const long version=9_007_199_254_740_993L;
    var request=new DiscardEquipmentRequest([new(id,version)],season);
    var item=new EquipmentResponse(id,"Head","Orange",3,true,"Recycled",version+1,"Water","Vitality","DrawInterval",
        season,season,season is null?null:"ActiveSeason",season is null?null:"season-equipment-v1",season is null?null:"NaturalDrop",season is null?null:true);
    var bytes=HttpDtoMapper.FromDto(Wire.DiscardEquipmentRequest.Descriptor,request).ToByteArray();
    var response=HttpDtoMapper.EncodeResponse(contract,new DiscardEquipmentResponse([item],season));
    File.WriteAllBytes(Path.Combine(args[0],name+".request"),bytes);File.WriteAllBytes(Path.Combine(args[0],name+".response"),response);
    cases.Add(new{name,season,id,version,request_sha256=Convert.ToHexStringLower(SHA256.HashData(bytes)),response_sha256=Convert.ToHexStringLower(SHA256.HashData(response))});
}
File.WriteAllText(Path.Combine(args[0],"cases.json"),JsonSerializer.Serialize(cases,new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine("Produced two actual C# typed discard request/receipt fixtures.");
