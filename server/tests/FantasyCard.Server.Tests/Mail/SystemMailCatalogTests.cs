using System.Text;
using FantasyCard.Server.Mail;

namespace FantasyCard.Server.Tests.Mail;

public sealed class SystemMailCatalogTests
{
    [Theory]
    [InlineData("seed_gold", "测试邮件：金币", "Test account reward: 100,000 gold.")]
    [InlineData("seed_souls", "测试邮件：魂晶", "Test account reward: 100,000 of each soul crystal.")]
    [InlineData("seed_white_fire", "测试邮件：白色火系装备", "Test account reward: a full set of white fire equipment.")]
    [InlineData("seed_green_water", "测试邮件：绿色水系装备", "Test account reward: a full set of green water equipment.")]
    [InlineData("seed_blue_earth", "测试邮件：蓝色土系装备", "Test account reward: a full set of blue earth equipment.")]
    [InlineData("seed_purple_wood", "测试邮件：紫色木系装备", "Test account reward: a full set of purple wood equipment.")]
    [InlineData("seed_orange_metal", "测试邮件：橙色金系装备", "Test account reward: a full set of orange metal equipment.")]
    [InlineData("seed2_mixed_set", "测试邮件2：橙紫双词缀套装", "test2 reward: an orange head piece and purple pieces for the other slots, all with matching effect and secondary affixes.")]
    [InlineData("seed2_fragments", "测试邮件2：装备碎片", "test2 reward: 100,000 equipment fragments.")]
    public void Generated_seed_fallback_keeps_legacy_title_and_static_number_format(string id, string title, string bodyEn)
    {
        var copy = SystemMailCatalog.Current.Render(id);
        Assert.Equal(title, copy.Title);
        Assert.Equal(bodyEn, copy.BodyEn);
        Assert.NotEmpty(copy.Body);
        Assert.NotEmpty(copy.TitleEn);
    }

    [Fact]
    public void Recall_reason_is_inserted_once_with_words_braces_and_whitespace_unchanged()
    {
        const string reason = "  Fire  Gold: 装备 {amount} {kind} {reason}\n管理员原文  ";
        var arguments = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["kind"] = "Gold", ["amount"] = "7", ["reason"] = reason
        };
        var copy = SystemMailCatalog.Current.Render("item_reclamation", arguments);
        Assert.Equal("道具收回通知", copy.Title);
        Assert.Equal("管理员收回：Gold × 7。原因：" + reason, copy.Body);
        Assert.Equal("Item Reclamation Notice", copy.TitleEn);
        Assert.Equal("An administrator reclaimed Gold × 7. Reason: " + reason, copy.BodyEn);
        Assert.Equal(reason + "|7|Gold", SystemMailCatalog.Format("{reason}|{amount}|{kind}", arguments));
        Assert.Equal(reason, arguments["reason"]);
    }

    [Fact]
    public void Generated_roles_and_legacy_name_fallback_preserve_wire_values()
    {
        Assert.Equal("System", SystemMailCatalog.Current.Sender("system"));
        Assert.Equal("Game Admin", SystemMailCatalog.Current.Sender("admin"));
        Assert.Equal("旅人", SystemMailCatalog.Current.TravelerFallback);
        Assert.Throws<InvalidDataException>(() => SystemMailCatalog.Current.Render("unknown"));
        Assert.Throws<InvalidDataException>(() => SystemMailCatalog.Current.Render("item_reclamation"));
        using var badSchema = new MemoryStream(Encoding.UTF8.GetBytes("{\"schema_version\":2}"));
        Assert.Throws<InvalidDataException>(() => SystemMailCatalog.Load(badSchema));
    }
}
