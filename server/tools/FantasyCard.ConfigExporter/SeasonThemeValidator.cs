namespace FantasyCard.ConfigExporter;

public static partial class SeasonConfigValidator
{
    private static readonly string[] ThemeElements=["Wood","Fire","Earth","Metal","Water"];
    private static readonly Dictionary<string,string> ThemeGroupMembers=new(StringComparer.Ordinal)
    {
        ["O1"]="Fire",["O2"]="Wood",["O3"]="Water",["O4"]="Earth",["O5"]="Metal",["O6"]="Fire|Fire",["O7"]="Metal|Wood",["O8"]="Water|Earth",
        ["M1"]="Fire|Fire",["M2"]="Water|Earth",["M3"]="Metal|Wood",["M4"]="Water|Water",["M5"]="Fire|Earth",
        ["E1"]="Metal",["E2"]="Fire",["E3"]="Water",["E4"]="Earth",["E5"]="Wood",["E6"]="Metal|Fire"
    };
    private static void ValidateThemes(IReadOnlyList<ConfigTable> tables)
    {
        var rules=tables.SingleOrDefault(t=>t.Name=="SeasonThemeRules");var themes=tables.SingleOrDefault(t=>t.Name=="SeasonThemes");
        var groups=tables.SingleOrDefault(t=>t.Name=="SeasonThemeGroups");
        if(rules is null&&themes is null&&groups is null)return;
        if(rules is null||themes is null||groups is null)throw new InvalidDataException("Theme policy, strategies and group references must publish together.");
        foreach(var pair in new[]{(Table:rules,Schema:"rule_id:s,enabled:b,selected_theme:s,preferred_weight:i,other_weight:i,group_weight_mode:s,global_damage_bp:i,layout:s,spawn_singles:b"),
                     (Table:themes,Schema:"theme_id:s,element:s,name_key:s,strategy_id:s,phase1_primary:s,phase1_secondary:s,phase2_primary:s,phase2_secondary:s,regeneration_budget_bp:i,regeneration_step_bp:i,phase1_shield:i,phase2_shield:i,setup_kind:s,setup_value:i"),
                     (Table:groups,Schema:"group_id:s,tier:s,member_elements:s,spawn_allowed:b,base_weight:i")})
            foreach(var field in pair.Schema.Split(','))
            {
                var parts=field.Split(':');var column=pair.Table.Columns.SingleOrDefault(c=>c.Name==parts[0]);
                Check(column is not null&&column.Required&&column.Scope==PublishScope.Both&&column.Type==(parts[1]=="i"?ConfigValueType.WholeNumber:parts[1]=="b"?ConfigValueType.Logical:ConfigValueType.Text),pair.Table,"invalid theme publication metadata");
            }
        Check(rules.Rows.Count==1,rules,"requires one theme policy");var row=rules.Rows[0];
        Check(S(rules,row,"rule_id")=="season-theme-v1"&&ThemeElements.Contains(S(rules,row,"selected_theme"),StringComparer.Ordinal)&&
            N(rules,row,"preferred_weight")==4000&&N(rules,row,"other_weight")==1500&&S(rules,row,"group_weight_mode")=="member-mean-normalized"&&
            N(rules,row,"global_damage_bp")==10000&&S(rules,row,"layout")=="chaos-6x6"&&B(rules,row,"spawn_singles"),rules,"theme weights, damage or shared layout differ");
        var preference=tables.SingleOrDefault(t=>t.Name=="SeasonLootPreference");
        Check(preference is not null&&preference.Rows.Count==1&&S(preference,preference.Rows[0],"default_element")==S(rules,row,"selected_theme"),rules,"theme must match the same original loot preference default");
        Check(themes.Rows.Count==5&&themes.Rows.Select(r=>S(themes,r,"theme_id")).Order(StringComparer.Ordinal).SequenceEqual(ThemeElements.Order(StringComparer.Ordinal)),themes,"requires exactly the five original elemental themes");
        foreach(var r in themes.Rows)
        {
            var id=S(themes,r,"theme_id");
            Check(S(themes,r,"element")==id&&S(themes,r,"name_key")=="season_theme_"+id.ToLowerInvariant(),themes,"invalid identity or localized name");
            var expected=id switch {"Fire"=>"ember-windows","Wood"=>"thorn-regrowth","Earth"=>"stone-cycle","Metal"=>"metal-telegraph","Water"=>"tide-shift",_=>""};
            Check(S(themes,r,"strategy_id")==expected,themes,"theme needs its named strategy");
            foreach(var field in ThemePhaseFields)Check(ThemeElements.Contains(S(themes,r,field),StringComparer.Ordinal),themes,"invalid phase element");
            Check(S(themes,r,"phase1_primary")==id&&S(themes,r,"phase1_primary")!=S(themes,r,"phase1_secondary")&&
                S(themes,r,"phase2_primary")!=S(themes,r,"phase2_secondary")&&
                (S(themes,r,"phase1_primary")!=S(themes,r,"phase2_primary")||S(themes,r,"phase1_secondary")!=S(themes,r,"phase2_secondary")),themes,"boss phases need distinct readable mixed elements");
            var budget=N(themes,r,"regeneration_budget_bp");var step=N(themes,r,"regeneration_step_bp");
            Check(id=="Wood"?budget is >0 and <=500&&step is >0 and <=200&&step<=budget:budget==0&&step==0,themes,"regeneration exceeds the shared five-percent fight budget");
            Check(id=="Wood"?N(themes,r,"phase1_shield")==0&&N(themes,r,"phase2_shield")==0:
                N(themes,r,"phase1_shield") is >0 and <=12&&N(themes,r,"phase2_shield") is >0 and <=10,themes,"theme shield pulse exceeds its bounded original slot");
            Check(id=="Metal"?S(themes,r,"setup_kind")=="Empower"&&N(themes,r,"setup_value")==2:
                S(themes,r,"setup_kind")=="Charge"&&N(themes,r,"setup_value")==0,themes,"unsupported telegraphed setup");
        }
        Check(groups.Rows.Count==ThemeGroupMembers.Count&&groups.Rows.Select(r=>S(groups,r,"group_id")).Order(StringComparer.Ordinal).SequenceEqual(ThemeGroupMembers.Keys.Order(StringComparer.Ordinal)),groups,"requires the original nineteen groups");
        foreach(var r in groups.Rows)
        {
            var id=S(groups,r,"group_id");var tier=id[0]=='O'?"outer":id[0]=='M'?"middle":"elite";
            Check(S(groups,r,"tier")==tier&&S(groups,r,"member_elements")==ThemeGroupMembers[id]&&N(groups,r,"base_weight") is >=1 and <=1000&&
                B(groups,r,"spawn_allowed")== (id[0]=='O'&&int.Parse(id[1..],System.Globalization.CultureInfo.InvariantCulture)<=5),groups,"group composition, spawn safety or base weight differs from its original reference");
        }
    }
    private static readonly string[] ThemePhaseFields=["phase1_primary","phase1_secondary","phase2_primary","phase2_secondary"];
}
