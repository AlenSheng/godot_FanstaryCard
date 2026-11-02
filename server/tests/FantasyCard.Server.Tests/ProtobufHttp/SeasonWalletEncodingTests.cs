using System.Text.Json;
using FantasyCard.Contracts.Http;
using Google.Protobuf;
using Dto = FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Seasons;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class SeasonWalletEncodingTests
{
    [Fact]
    public void RequestPreservesLegacyTagsAndOptionalSeasonPresence()
    {
        var contract = HttpProtocolRegistry.Find("POST", "/api/v1/class-weapons/Mage/enhance")!;
        var request = new Wire.EnhanceEquipmentRequest { ExpectedVersion = 7, FragmentSourceSeasonId = "season-a" };
        Assert.Equal("08071a08736561736f6e2d61", Convert.ToHexStringLower(request.ToByteArray()));
        var dto = Assert.IsType<Dto.EnhanceEquipmentRequest>(HttpDtoMapper.DecodeRequest(contract, request.ToByteArray(), typeof(Dto.EnhanceEquipmentRequest)));
        Assert.Equal(7, dto.ExpectedVersion);
        Assert.Equal("season-a", dto.FragmentSourceSeasonId);
        Assert.Null(dto.MaterialEquipmentId);

        var legacy = new Wire.EnhanceEquipmentRequest { ExpectedVersion = 7 };
        var decoded = Assert.IsType<Dto.EnhanceEquipmentRequest>(HttpDtoMapper.DecodeRequest(contract, legacy.ToByteArray(), typeof(Dto.EnhanceEquipmentRequest)));
        Assert.Null(decoded.FragmentSourceSeasonId);
        legacy.FragmentSourceSeasonId = "";
        decoded = Assert.IsType<Dto.EnhanceEquipmentRequest>(HttpDtoMapper.DecodeRequest(contract, legacy.ToByteArray(), typeof(Dto.EnhanceEquipmentRequest)));
        Assert.Equal("", decoded.FragmentSourceSeasonId);
    }

    [Fact]
    public void ResponseCarriesWalletIdentityAndExactInt64Version()
    {
        var contract = HttpProtocolRegistry.Find("POST", "/api/v1/class-weapons/Mage/enhance")!;
        var equipment = new Dto.EquipmentResponse(Guid.Empty, "ClassWeapon", "Mage", 1, true, "Equipped", 2);
        var result = new Dto.EnhanceResult(equipment, 92, null, "season-a", 9_007_199_254_740_993L);
        var wire = Wire.EnhanceResult.Parser.ParseFrom(HttpDtoMapper.EncodeResponse(contract, result));
        Assert.Equal("season-a", wire.FragmentSourceSeasonId);
        Assert.Equal(9_007_199_254_740_993L, wire.FragmentWalletVersion);
        Assert.Equal(92, wire.EquipmentFragments);
        var legacy = Wire.EnhanceResult.Parser.ParseFrom(HttpDtoMapper.EncodeResponse(contract, new Dto.EnhanceResult(equipment, 92, null)));
        Assert.False(legacy.HasFragmentSourceSeasonId);
        Assert.False(legacy.HasFragmentWalletVersion);

        var sparse = new Wire.EnhanceResult { EquipmentFragments = 100, FragmentSourceSeasonId = "season-a", FragmentWalletVersion = 11 };
        Assert.Equal("10642208736561736f6e2d61280b", Convert.ToHexStringLower(sparse.ToByteArray()));
    }

    [Fact]
    public void QuoteUsesNewTagsWithoutChangingLegacyFields()
    {
        var contract = HttpProtocolRegistry.Find("GET", "/api/v1/class-weapons/Mage/enhancement-quote")!;
        var quote = new Dto.EnhancementQuoteResponse("ClassWeapon", 0, 1, 1, 8, 0, null, 100, 0, true, null, "season-a", 2);
        var wire = Wire.EnhancementQuoteResponse.Parser.ParseFrom(HttpDtoMapper.EncodeResponse(contract, quote));
        Assert.Equal(100, wire.AvailableFragments);
        Assert.Equal(8, wire.FragmentCost);
        Assert.Equal("season-a", wire.FragmentSourceSeasonId);
        Assert.Equal(2, wire.FragmentWalletVersion);
        Assert.Equal("fragment_source_season_id", Wire.EnhancementQuoteResponse.Descriptor.FindFieldByNumber(12).Name);
        Assert.Equal("fragment_wallet_version", Wire.EnhancementQuoteResponse.Descriptor.FindFieldByNumber(13).Name);
    }

    [Fact]
    public void LegacyEquipmentIdempotencyJsonRemainsByteCompatible()
    {
        Assert.Equal("{\"ExpectedVersion\":7,\"MaterialEquipmentId\":null}", JsonSerializer.Serialize(new Dto.EnhanceEquipmentRequest(7)));
        var withSource = JsonSerializer.Serialize(new Dto.EnhanceEquipmentRequest(7, null, "season-a"));
        Assert.Contains("\"FragmentSourceSeasonId\":\"season-a\"", withSource, StringComparison.Ordinal);
    }

    [Fact]
    public void BootstrapSeasonMetadataUsesAdditiveMessageTagAndKeepsExactWalletValues()
    {
        var time = new DateTimeOffset(2026, 11, 1, 16, 0, 0, TimeSpan.Zero);
        var wallet = new SeasonWalletResponse("season-a", 30, 20, 3, 9_007_199_254_740_993L, null, true);
        var season = new SeasonSummaryResponse("Active", "season-a", "season-v1", "config", "stats", time,
            time.AddDays(42), 5, 2, 0, 1000, null, null, wallet, [wallet], true, "D0");
        var bytes = HttpDtoMapper.EncodeResponse(HttpProtocolRegistry.Find("GET", "/api/v1/bootstrap")!, new { Season = season });
        var wire = Wire.BootstrapResponse.Parser.ParseFrom(bytes);
        Assert.Equal("Active", wire.Season.State);
        Assert.Equal("D0", wire.Season.DifficultyId);
        Assert.Equal(1000, wire.Season.HistoricalEquipmentFragments);
        Assert.Equal(9_007_199_254_740_993L, Assert.Single(wire.Season.FragmentWallets).Version);
        Assert.True(wire.Season.HasJoined);
        Assert.Equal("season", Wire.BootstrapResponse.Descriptor.FindFieldByNumber(18).Name);
        var closed = new Wire.BootstrapResponse { Season = new Wire.SeasonSummaryResponse { State = "Closed" } };
        Assert.Equal("9201080a06436c6f736564", Convert.ToHexStringLower(closed.ToByteArray()));
    }

    [Fact]
    public void InventoryCarriesProvenanceWithoutInventingRecipeEligibilityForLegacyItems()
    {
        var equipment = new Dto.EquipmentResponse(Guid.NewGuid(), "Head", "Purple", 0, false, "Inventory", 1,
            OriginSeasonId: "season-a", SeasonId: "season-a", AssetScope: "ActiveSeason",
            StatsVersion: "stats", SourceKind: "MarkCraft", RecipeExtracted: false);
        var inventory = new Dto.InventoryResponse(new(50, 1, 49), [equipment], new(0, 0, 0))
            { Scope = new("ActiveSeason", "season-a", false) };
        var wire = Wire.InventoryResponse.Parser.ParseFrom(HttpDtoMapper.EncodeResponse(
            HttpProtocolRegistry.Find("GET", "/api/v1/inventory")!, inventory));
        Assert.Equal("season-a", wire.Scope.SeasonId);
        var item = Assert.Single(wire.Equipments);
        Assert.Equal("season-a", item.OriginSeasonId);
        Assert.True(item.HasRecipeExtracted);
        Assert.False(item.RecipeExtracted);
        var scope = new Wire.InventoryResponse { Scope = new Wire.InventoryScopeResponse { State = "ActiveSeason", SeasonId = "season-a" } };
        Assert.Equal("22180a0c416374697665536561736f6e1208736561736f6e2d61", Convert.ToHexStringLower(scope.ToByteArray()));
    }

    [Fact]
    public void LoadoutSeasonTagIsAdditiveAndAbsentForLegacyResponses()
    {
        var contract = HttpProtocolRegistry.Find("GET", "/api/v1/loadouts/Mage")!;
        var source = new Dto.LoadoutResponse(FantasyCard.Contracts.Players.HeroClassDto.Mage,
            [null, null, null, null, null], 2, "season-a");
        var wire = Wire.LoadoutResponse.Parser.ParseFrom(HttpDtoMapper.EncodeResponse(contract, source));
        Assert.Equal("season-a", wire.SeasonId);
        Assert.Equal(2, wire.Version);
        Assert.False(Wire.LoadoutResponse.Parser.ParseFrom(HttpDtoMapper.EncodeResponse(contract, source with { SeasonId = null })).HasSeasonId);
        Assert.Equal("2208736561736f6e2d61", Convert.ToHexStringLower(new Wire.LoadoutResponse { SeasonId = "season-a" }.ToByteArray()));
    }
}
