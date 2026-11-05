namespace FantasyCard.ConfigExporter;

public static partial class SeasonConfigValidator
{
    private static readonly string[] MonsterTuningGroups=["E1","E3","E4","E6"];
    private static void ValidateMonsterTuning(IReadOnlyList<ConfigTable> tables)
    {
        var table=tables.SingleOrDefault(t=>t.Name=="SeasonMonsterTuning");if(table is null)return;
        const string schema="id:s,rule_id:s,baseline_id:s,group_id:s,member_order:i,monster_id:s,base_hp:i,base_shield:i,shield_intent_value:i";
        Check(table.Columns.Count==9&&table.Columns.Select(c=>c.Name).Distinct(StringComparer.Ordinal).Count()==9,table,"requires the exact tuning schema");
        foreach(var field in schema.Split(','))
        {
            var parts=field.Split(':');var column=table.Columns.SingleOrDefault(c=>c.Name==parts[0]);
            Check(column is not null&&column.Required&&column.Scope==PublishScope.Server&&column.Type==(parts[1]=="i"?ConfigValueType.WholeNumber:ConfigValueType.Text),table,"invalid required server-only tuning metadata");
        }
        Check(table.Rows.Count==4&&table.Rows.Select(r=>S(table,r,"group_id")).Order(StringComparer.Ordinal).SequenceEqual(MonsterTuningGroups),table,"requires all four original shield-elite groups exactly once");
        foreach(var row in table.Rows)
        {
            var group=S(table,row,"group_id");var hp=N(table,row,"base_hp");var shield=N(table,row,"base_shield");var loop=N(table,row,"shield_intent_value");
            var monster=group switch{"E1" or "E6"=>"metal-guard","E3"=>"marsh-mother","E4"=>"stone-guard",_=>""};
            Check(S(table,row,"id")==group+":1"&&N(table,row,"member_order")==1&&S(table,row,"monster_id")==monster&&
                S(table,row,"rule_id")=="season-monster-tuning-v1"&&S(table,row,"baseline_id")=="gdd-0.70-fixed-base-v1",table,"identity differs from its immutable original member");
            Check(hp is >=1 and <=10000&&shield>=0&&shield<=hp/2&&loop>=0&&loop<=hp/2,table,"HP or shield values exceed their base bounds");
        }
    }
}
