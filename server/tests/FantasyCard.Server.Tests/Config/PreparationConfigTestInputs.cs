using FantasyCard.ConfigExporter;
using FantasyCard.Domain.Configuration;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Distinct legal source controls; none of these values are installed as balance data.</summary>
internal static class PreparationConfigTestInputs
{
    internal const string StatsVersion="preparation-archive-stats";

    internal static GameConfigCatalog Original()
    {
        var tables=XlsxConfigReader.Read(Path.Combine(PublishedConfigTestInputs.FindRoot(),"config/FantasyCard_Config.xlsx"));
        tables=Set(tables,"SeasonThemeRules","selected_theme","Wood");
        tables=Set(tables,"SeasonLootPreference","default_element","Wood");
        tables=Set(tables,"Backpacks","capacity",21L,"Free");
        tables=Set(tables,"SeasonDifficulty","entry_quality_cap",1L,"D1");
        tables=Set(tables,"Cards","elemental_damage",200L,"C01");
        tables=Set(tables,"SeasonEquipment","stats_version",StatsVersion,all:true);
        tables=Set(tables,"SeasonEquipmentRules","stats_version",StatsVersion);
        var loan=tables.Single(t=>t.Name=="SeasonBorrowedDecks");
        var hero=Index(loan,"hero_class");var template=Index(loan,"template_id");var slot=Index(loan,"slot_index");var card=Index(loan,"card_id");
        var rows=loan.Rows.Select(row=>
        {
            if(!Equals(row[hero].Value,"Mage"))return row;
            var changed=row.ToArray();changed[template]=new(changed[template].Type,"archive-loan-mage");
            if(Convert.ToInt64(row[slot].Value,System.Globalization.CultureInfo.InvariantCulture)==12)
                changed[card]=new(changed[card].Type,"C30");
            return changed;
        }).ToArray();
        tables=tables.Select(t=>t==loan?t with {Rows=rows}:t).ToArray();
        return GameConfigCatalog.Load(ConfigCompiler.Compile("active-preparation-archive",tables,out _));
    }

    private static int Index(ConfigTable table,string field)=>table.Columns.Select((c,i)=>(c,i)).Single(p=>p.c.Name==field).i;
    private static ConfigTable[] Set(IReadOnlyList<ConfigTable> tables,string name,string field,object value,string? key=null,bool all=false)
    {
        var table=tables.Single(t=>t.Name==name);var column=Index(table,field);
        var rows=table.Rows.Select((row,index)=>
        {
            if(!all&&(key is null?index!=0:!Equals(row[0].Value,key)))return row;
            var changed=row.ToArray();changed[column]=new(changed[column].Type,value);return changed;
        }).ToArray();
        return tables.Select(t=>t==table?t with {Rows=rows}:t).ToArray();
    }
}
