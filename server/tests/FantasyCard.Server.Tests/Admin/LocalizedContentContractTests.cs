using System.Text.Json;
using FantasyCard.Contracts.Mail;
using FantasyCard.Server.Admin;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;

namespace FantasyCard.Server.Tests.Admin;

public sealed class LocalizedContentContractTests
{
    private static readonly JsonSerializerOptions WebJson = new(JsonSerializerDefaults.Web);

    [Fact]
    public void PublicClientInfoIncludesBothAnnouncementLanguages()
    {
        var settings = new ClientSettings(false, "测试服更新", "中文正文", 2,
            DateTimeOffset.UtcNow, "Test Server Update", "English body");
        var info = ClientSettingsEndpoints.PublicInfo(settings, new TestEnvironment(),
            new ConfigurationBuilder().Build());

        using var json = JsonDocument.Parse(JsonSerializer.Serialize(info, WebJson));
        var announcement = json.RootElement.GetProperty("announcement");
        Assert.Equal("测试服更新", announcement.GetProperty("title").GetString());
        Assert.Equal("中文正文", announcement.GetProperty("body").GetString());
        Assert.Equal("Test Server Update", announcement.GetProperty("titleEn").GetString());
        Assert.Equal("English body", announcement.GetProperty("bodyEn").GetString());
    }

    [Fact]
    public void MailResponseIncludesBothLanguagesAndMigration()
    {
        var response = new MailItemResponse(Guid.NewGuid(), "系统通知", "中文正文", "Game Admin",
            DateTimeOffset.UtcNow, null, false, false, [], "System Mail", "English body");
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(response, WebJson));
        Assert.Equal("System Mail", json.RootElement.GetProperty("titleEn").GetString());
        Assert.Equal("English body", json.RootElement.GetProperty("bodyEn").GetString());
        Assert.True(typeof(ClientSettingsRepository).Assembly.GetManifestResourceNames().Any(
            name => name.EndsWith(".V028__localized_admin_content.sql", StringComparison.Ordinal)));
    }

    private sealed class TestEnvironment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = Environments.Production;
        public string ApplicationName { get; set; } = "FantasyCard.Server.Tests";
        public string ContentRootPath { get; set; } = "";
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
