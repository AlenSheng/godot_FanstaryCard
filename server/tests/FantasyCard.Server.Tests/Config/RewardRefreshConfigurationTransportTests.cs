using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Configuration;
using FantasyCard.Contracts.Http;
using FantasyCard.Domain.Configuration;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.Config;

public sealed class RewardRefreshConfigurationTransportTests
{
    [Fact]
    public void OriginalArchiveAndDistinctPricesProduceRealTypedInteropInputsWithoutRewritingArchive()
    {
        var root=PublishedConfigTestInputs.FindRoot();
        var output=Environment.GetEnvironmentVariable("FANTASYCARD_REFRESH_INTEROP_OUTPUT")
            ?? Path.Combine(root,"server/.artifacts/refresh-config");
        Directory.CreateDirectory(output);
        var archive=Path.Combine(root,"server/config/archive/season-v1-config-12/fantasycard.config.bytes");
        var oldBytes=File.ReadAllBytes(archive);var oldHash=SHA256.HashData(oldBytes);
        var first=RewardRefreshOriginalConfigTests.CreateConfig("refresh-price-seven");
        var next=RewardRefreshOriginalConfigTests.CreateConfig("refresh-price-eleven",alternate:true);
        var fixtures=new[] {(Name:"archive12",Catalog:GameConfigCatalog.Load(oldBytes),LegacyScope:true),
            (Name:"formal13",Catalog:GameConfigCatalog.Current,LegacyScope:false),
            (Name:"seven",Catalog:first.Catalog,LegacyScope:false),(Name:"eleven",Catalog:next.Catalog,LegacyScope:false)};
        Assert.Equal("season-v1-config-13",GameConfigCatalog.Current.Version);
        var cases=new List<object>();
        foreach(var f in fixtures)
        {
            var bytes=f.Catalog.ExportPublishedBytes();
            var dto=new PublishedConfigurationResponse(f.Catalog.Version,f.Catalog.ContentHash,bytes);
            var contract=HttpProtocolRegistry.Find("GET","/api/v1/config/"+f.Catalog.Version)!;
            var encoded=HttpDtoMapper.EncodeResponse(contract,dto);
            var wire=Wire.PublishedConfigurationResponse.Parser.ParseFrom(encoded);
            Assert.Equal(bytes,wire.Bundle.ToByteArray());Assert.Equal(dto.ContentHash,wire.ContentHash);
            var decoded=Assert.IsType<PublishedConfigurationResponse>(HttpDtoMapper.ToDto(wire,typeof(PublishedConfigurationResponse)));
            Assert.Equal(dto.ConfigVersion,decoded.ConfigVersion);Assert.Equal(bytes,decoded.Bundle);
            File.WriteAllBytes(Path.Combine(output,f.Name+".envelope"),encoded);
            File.WriteAllBytes(Path.Combine(output,f.Name+".bundle"),bytes);
            cases.Add(new {name=f.Name,version=f.Catalog.Version,hash=f.Catalog.ContentHash,legacyScope=f.LegacyScope,
                prices=Enumerable.Range(1,3).Select(f.Catalog.RewardRefreshGold).ToArray(),
                bundle_sha256=Convert.ToHexStringLower(SHA256.HashData(bytes)),envelope_sha256=Convert.ToHexStringLower(SHA256.HashData(encoded))});
        }
        Assert.Equal(oldHash,SHA256.HashData(File.ReadAllBytes(archive)));
        File.WriteAllText(Path.Combine(output,"cases.json"),JsonSerializer.Serialize(cases));
    }
}
