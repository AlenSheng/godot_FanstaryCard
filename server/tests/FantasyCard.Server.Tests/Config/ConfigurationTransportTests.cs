using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Configuration;
using FantasyCard.Contracts.Http;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.Config;

public sealed class ConfigurationTransportTests
{
    [Fact]
    public void RealPublishedBundlesRoundTripTypedHttpBytesAndProduceNativeInteropInputs()
    {
        var root = Path.Combine(PublishedConfigTestInputs.FindRoot(),"server/.artifacts/config-client");
        Directory.CreateDirectory(root);
        var cases = new List<object>();
        foreach (var alternate in new[] {false,true})
        {
            var name = alternate ? "next" : "old";
            var fixture = PublishedConfigTestInputs.Create("client-"+name,alternate);
            var exported = fixture.Catalog.ExportPublishedBytes();
            Assert.Equal(fixture.Bytes,exported);
            exported[^1] ^= 1;
            Assert.Equal(fixture.Bytes,fixture.Catalog.ExportPublishedBytes());
            var dto = new PublishedConfigurationResponse(fixture.Catalog.Version,fixture.Hash,fixture.Catalog.ExportPublishedBytes());
            var contract = HttpProtocolRegistry.Find("GET","/api/v1/config/"+fixture.Catalog.Version)!;
            var envelope = HttpDtoMapper.EncodeResponse(contract,dto);
            var wire = Wire.PublishedConfigurationResponse.Parser.ParseFrom(envelope);
            Assert.Equal(fixture.Catalog.Version,wire.ConfigVersion);
            Assert.Equal(fixture.Hash,wire.ContentHash);
            Assert.Equal(fixture.Bytes,wire.Bundle.ToByteArray());
            var roundTrip = Assert.IsType<PublishedConfigurationResponse>(HttpDtoMapper.ToDto(wire,typeof(PublishedConfigurationResponse)));
            Assert.Equal(dto.ConfigVersion,roundTrip.ConfigVersion);
            Assert.Equal(dto.ContentHash,roundTrip.ContentHash);
            Assert.Equal(dto.Bundle,roundTrip.Bundle);
            File.WriteAllBytes(Path.Combine(root,name+".bundle"),fixture.Bytes);
            File.WriteAllBytes(Path.Combine(root,name+".envelope"),envelope);
            cases.Add(new {name,version=fixture.Catalog.Version,hash=fixture.Hash,bundleSha256=Convert.ToHexString(SHA256.HashData(fixture.Bytes)).ToLowerInvariant(),
                envelopeSha256=Convert.ToHexString(SHA256.HashData(envelope)).ToLowerInvariant(),damage=alternate?400:200,bonus=alternate?7:3,backpack=alternate?22:21,whiteDamage=alternate ? .27 : .13});
        }
        File.WriteAllText(Path.Combine(root,"cases.json"),JsonSerializer.Serialize(cases));
    }

    [Fact]
    public void OversizedPublishedEnvelopeCannotBypassHttpBudget()
    {
        var contract = HttpProtocolRegistry.Find("GET","/api/v1/config/budget")!;
        Assert.Throws<InvalidDataException>(() => HttpDtoMapper.EncodeResponse(contract,
            new PublishedConfigurationResponse("budget",new string('a',64),new byte[HttpProtocolRegistry.MaximumBodyBytes])));
    }
}
