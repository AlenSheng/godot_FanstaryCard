using FantasyCard.ConfigExporter;
using FantasyCard.Domain.Configuration;

namespace FantasyCard.Server.Tests.Config;

internal static class JourneyRewardTestInputs
{
    internal static readonly (string Id,string Kind)[] Cosmetics=
    [
        ("trail-seeker","AvatarFrame"),("relic-seeker","Title"),("first-threshold","Collection"),
        ("waymark-seal","CardBack"),("veil-warden","Title"),("veilbound-seal","AvatarFrame"),
        ("fivefold-chronicle","Collection"),("convergent-sigil","CardBack"),("veil-cartographer","Title"),
        ("relicbound-pathfinder","AvatarFrame")
    ];

    internal static IReadOnlyList<ConfigTable> Tables()
    {
        var directory=new DirectoryInfo(AppContext.BaseDirectory);string? path=null;
        while(directory is not null)
        {
            var candidate=Path.Combine(directory.FullName,"config/FantasyCard_Config.xlsx");
            if(File.Exists(candidate)){path=candidate;break;}directory=directory.Parent;
        }
        if(path is null)throw new FileNotFoundException("The pinned formal workbook is required.");
        // This is an explicit next-version fixture, not a replacement runtime source.
        var original=XlsxConfigReader.Read(path).Where(t=>t.Name is not ("SeasonJourneyRewards" or "SeasonCosmetics"));
        var rewards=Enumerable.Range(1,30).Select(level=>
        {
            var (kind,amount)=level<=20?((level%5) switch {1 or 4=>("EquipmentFragments",10),2=>("WarriorSoul",6),3=>("ClassSoul",2),_=>("CardPack",1)}):("Cosmetic",1);
            return new object?[]{$"journey-level-{level:D2}",(long)level,kind,(long)amount,
                kind=="EquipmentFragments"?"SeasonalBound":"PermanentBound",kind=="ClassSoul",level<=20?null:Cosmetics[level-21].Id};
        }).ToArray();
        return original.Concat(new[]{Table("SeasonJourneyRewards","reward_id:s,level:i,kind:s,amount:i,ownership:s,requires_class_choice:b,cosmetic_id:o",rewards),
            Table("SeasonCosmetics","cosmetic_id:s,kind:s,name_key:s,description_key:s",Cosmetics.Select(c=>new object?[]{c.Id,c.Kind,
                $"journey_cosmetic_{c.Id.Replace('-','_')}_name",$"journey_cosmetic_{c.Id.Replace('-','_')}_description"}).ToArray())}).ToArray();
    }

    internal static GameConfigCatalog Catalog(string version="journey-rewards-control")=>
        GameConfigCatalog.Load(ConfigCompiler.Compile(version,Tables(),out _));

    private static ConfigTable Table(string name,string schema,IReadOnlyList<object?[]> values)
    {
        var columns=schema.Split(',').Select(field=>
        {
            var parts=field.Split(':');return new ConfigColumn(parts[0],parts[1] switch
            {"i"=>ConfigValueType.WholeNumber,"b"=>ConfigValueType.Logical,_=>ConfigValueType.Text},parts[1]!="o",PublishScope.Both,parts[0]);
        }).ToArray();
        return new(name,columns,values.Select(row=>(IReadOnlyList<ConfigValue>)row.Select((value,index)=>new ConfigValue(columns[index].Type,value)).ToArray()).ToArray());
    }

    internal static ConfigTable[] Change(IReadOnlyList<ConfigTable> tables,string name,int row,string field,object? value)
    {
        var table=tables.Single(t=>t.Name==name);var index=table.Columns.Select((c,i)=>(c,i)).Single(v=>v.c.Name==field).i;
        var rows=table.Rows.ToArray();var changed=rows[row].ToArray();changed[index]=new(table.Columns[index].Type,value);rows[row]=changed;
        return tables.Select(t=>t==table?t with {Rows=rows}:t).ToArray();
    }
}
