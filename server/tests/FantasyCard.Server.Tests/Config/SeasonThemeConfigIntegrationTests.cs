using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.ConfigExporter;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Tests.Config;

public sealed class SeasonThemeConfigIntegrationTests
{
    private static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web){Converters={new JsonStringEnumConverter()}};

    [Theory]
    [InlineData("Fire")][InlineData("Wood")][InlineData("Earth")][InlineData("Metal")][InlineData("Water")]
    public void CompilerAndActualRoomKeepTheSelectedOriginalThemeAcrossRecovery(string element)
    {
        var config=Variant(element);var catalog=CombatCardCatalog.Create(config);var id=Guid.NewGuid();
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,73,season:new("theme-room",2,"season-v1",config.Version,"season-equipment-v1"));
        room.AddPlayer(new(id,HeroClass.Mage,Enumerable.Range(1,13).Select(n=>$"C{n:D2}").Concat(Enumerable.Range(1,7).Select(n=>$"MAG-{n:D2}")).ToArray(),null));
        room.InitializeMap(ChaosMapGenerator.Generate(73,1,config.SeasonThemes));
        var snapshot=room.Capture();var cell=snapshot.Map!.Cells.Single(c=>c.IsBoss);
        snapshot=snapshot with {Players=[snapshot.Players[0] with {Position=cell.Position,Phase=RoomPlayerPhase.Pve,
            Pve=PveBattleFactory.Create(cell,config.SeasonDifficulty(2),config.SeasonThemes!.Selected).Capture()}]};
        var restored=BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(JsonSerializer.Serialize(snapshot,Json),Json)!,catalog,73);
        var boss=Assert.Single(restored.GetPlayer(id).Pve!.Monsters);Assert.Equal(element,boss.ThemeProfile!.ThemeId);
        Assert.Equal(config.SeasonThemes.Selected,boss.ThemeProfile);Assert.Equal(element,restored.GetPlayer(id).LootPreferenceElement);
        var bossSnapshot=Assert.Single(snapshot.Players[0].Pve!.Monsters);
        var missing=snapshot with {Players=[snapshot.Players[0] with {Pve=snapshot.Players[0].Pve! with {Monsters=[bossSnapshot with {ThemeProfile=null}]}}]};
        if(element=="Wood")Assert.Throws<InvalidDataException>(()=>BattleRoom.Restore(missing,catalog,73));
        else Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(missing,catalog,73));
        var wrong=config.SeasonThemes.Themes.First(t=>t.ThemeId!=element);
        var changed=snapshot with {Players=[snapshot.Players[0] with {Pve=snapshot.Players[0].Pve! with {Monsters=[bossSnapshot with {ThemeProfile=wrong}]}}]};
        Assert.Throws<InvalidDataException>(()=>BattleRoom.Restore(changed,catalog,73));
    }

    [Theory]
    [InlineData("SeasonThemeRules","Fire","global_damage_bp",10001L)]
    [InlineData("SeasonThemes","Wood","regeneration_budget_bp",501L)]
    [InlineData("SeasonThemes","Wood","regeneration_step_bp",201L)]
    [InlineData("SeasonThemes","Earth","phase1_shield",13L)]
    [InlineData("SeasonThemes","Metal","setup_value",3L)]
    [InlineData("SeasonThemeGroups","O1","base_weight",0L)]
    public void InvalidThemeNumericTermsCannotBePublished(string name,string key,string field,long value)
    {
        var tables=Read();var target=name=="SeasonThemeRules"?null:key;
        Assert.Throws<InvalidDataException>(()=>ConfigCompiler.Compile("invalid-theme",Change(tables,name,field,value,target),out _));
    }

    [Theory]
    [InlineData("SeasonThemeRules","selected_theme","Wood")]
    [InlineData("SeasonThemeRules","group_weight_mode","independent-monsters")]
    [InlineData("SeasonThemeRules","layout","new100player-map")]
    [InlineData("SeasonThemeGroups","member_elements","Water")]
    public void MismatchedDefaultIndependentPairsOrInventedLayoutAreRejected(string name,string field,string value)
    {
        Assert.Throws<InvalidDataException>(()=>ConfigCompiler.Compile("invalid-theme",Change(Read(),name,field,value),out _));
    }

    [Fact]
    public void PartialThemeGroupCannotReplaceACompletePublishedPolicy()
    {
        var tables=Read().Where(t=>t.Name!="SeasonThemeGroups").ToArray();
        Assert.Throws<InvalidDataException>(()=>ConfigCompiler.Compile("partial-theme",tables,out _));
    }

    internal static GameConfigCatalog Variant(string element)
    {
        var tables=Change(Change(Read(),"SeasonThemeRules","selected_theme",element),"SeasonLootPreference","default_element",element);
        return GameConfigCatalog.Load(ConfigCompiler.Compile("theme-control-"+element.ToLowerInvariant(),tables,out _));
    }

    private static ConfigTable[] Change(IReadOnlyList<ConfigTable> tables,string name,string field,object value,string? key=null)
    {
        var table=tables.Single(t=>t.Name==name);var col=table.Columns.Select((c,i)=>(c,i)).Single(p=>p.c.Name==field);
        var selected=key is null?0:table.Rows.Select((r,i)=>(r,i)).Single(pair=>Equals(pair.r[0].Value,key)).i;
        var rows=table.Rows.ToArray();var row=rows[selected].ToArray();row[col.i]=new(col.c.Type,value);rows[selected]=row;
        return tables.Select(t=>t==table?t with {Rows=rows}:t).ToArray();
    }

    private static IReadOnlyList<ConfigTable> Read()
    {
        var directory=new DirectoryInfo(AppContext.BaseDirectory);
        while(directory is not null)
        {
            var path=Path.Combine(directory.FullName,"config/FantasyCard_Config.xlsx");
            if(File.Exists(path))return XlsxConfigReader.Read(path);directory=directory.Parent;
        }
        throw new FileNotFoundException("The pinned formal workbook is required.");
    }
}
