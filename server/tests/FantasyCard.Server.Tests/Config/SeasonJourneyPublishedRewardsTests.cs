using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.ConfigExporter;
using FantasyCard.Domain.Configuration;

namespace FantasyCard.Server.Tests.Config;

public sealed class SeasonJourneyPublishedRewardsTests
{
    [Fact]
    public void FormalWorkbookAndEmbeddedBytesExposeAllThirtyRewardsAndTenLocalizedCosmetics()
    {
        var root=PublishedConfigTestInputs.FindRoot();var config=GameConfigCatalog.Current;
        Assert.Equal("season-v1-config-17",config.Version);
        var compiled=ConfigCompiler.Compile(config.Version,XlsxConfigReader.Read(Path.Combine(root,"config/FantasyCard_Config.xlsx")),out var hash);
        Assert.Equal(config.ContentHash,hash);Assert.Equal(config.ExportPublishedBytes(),compiled);
        var policy=Assert.IsType<SeasonJourneyRewardsConfig>(config.SeasonJourneyRewards);
        Assert.Equal(new SeasonJourneyRewardBudget(80,24,8,4,12),policy.Budget());
        using var catalog=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"client/data/catalog.json")));
        Assert.Equal(config.Version,catalog.RootElement.GetProperty("version").GetString());
        var publicTables=catalog.RootElement.GetProperty("tables");Assert.Equal(32,publicTables.EnumerateObject().Count());
        var rewards=publicTables.GetProperty("SeasonJourneyRewards");Assert.Equal(30,rewards.GetArrayLength());
        foreach(var row in rewards.EnumerateArray())
        {
            var reward=policy.At(row.GetProperty("level").GetInt32());
            Assert.Equal(reward.RewardId,row.GetProperty("reward_id").GetString());Assert.Equal(reward.Kind,row.GetProperty("kind").GetString());
            Assert.Equal(reward.Amount,row.GetProperty("amount").GetInt32());Assert.Equal(reward.Ownership,row.GetProperty("ownership").GetString());
            Assert.Equal(reward.RequiresClassChoice,row.GetProperty("requires_class_choice").GetBoolean());
            Assert.Equal(reward.CosmeticId,row.GetProperty("cosmetic_id").ValueKind==JsonValueKind.Null?null:row.GetProperty("cosmetic_id").GetString());
        }
        var cosmetics=publicTables.GetProperty("SeasonCosmetics");Assert.Equal(10,cosmetics.GetArrayLength());
        foreach(var code in new[]{"zh-CN","en","es","fr","pt","id","hi","ar","ru","ja","ko"})
        {
            using var pack=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,$"client/data/locales/{code}.json")));
            foreach(var cosmetic in policy.Cosmetics)
            {
                Assert.False(string.IsNullOrWhiteSpace(pack.RootElement.GetProperty("strings").GetProperty(cosmetic.NameKey).GetString()));
                Assert.False(string.IsNullOrWhiteSpace(pack.RootElement.GetProperty("strings").GetProperty(cosmetic.DescriptionKey).GetString()));
            }
        }
    }

    [Fact]
    public void OriginalThirteenBytesRemainImmutableAndCannotDrawNewJourneyRewards()
    {
        var root=PublishedConfigTestInputs.FindRoot();var path=Path.Combine(root,"server/config/archive/season-v1-config-13/fantasycard.config.bytes");
        var bytes=File.ReadAllBytes(path);Assert.Equal("29a0e4715aa2a82cecda5056d34d7e7262e66bfbb9405f7ce86121dda4abf75c",Convert.ToHexStringLower(SHA256.HashData(bytes)));
        var original=GameConfigCatalog.Load(bytes);Assert.Equal("season-v1-config-13",original.Version);
        Assert.Null(original.SeasonJourneyRewards);var journey=Assert.IsType<SeasonJourneyConfig>(original.SeasonJourney);
        Assert.Equal(30,journey.Progress(12525,42).Level);Assert.Equal(60,original.RewardRefreshGold(1));
        Assert.Throws<FantasyCard.Domain.Players.DomainValidationException>(()=>GameConfigCatalog.Current.SeasonJourneyRewards!.Draw(5,null,original,_=>0));
        Assert.Equal(bytes,File.ReadAllBytes(path));
    }
}
