namespace FantasyCard.ConfigExporter;

public static partial class SeasonConfigValidator
{
    private static void ValidateJourneyRewards(IReadOnlyList<ConfigTable> tables)
    {
        var rewards=tables.SingleOrDefault(t=>t.Name=="SeasonJourneyRewards");
        var cosmetics=tables.SingleOrDefault(t=>t.Name=="SeasonCosmetics");
        if(rewards is null&&cosmetics is null)return;
        if(rewards is null||cosmetics is null)throw new InvalidDataException("Journey rewards and cosmetics must publish together.");
        var journey=tables.SingleOrDefault(t=>t.Name=="SeasonJourneyRules");
        var shop=tables.SingleOrDefault(t=>t.Name=="SeasonShopRules");
        Check(journey is not null&&shop is not null&&journey.Rows.Count==1&&shop.Rows.Count==1&&
            B(journey,journey.Rows[0],"enabled")&&B(shop,shop.Rows[0],"enabled"),rewards,"requires enabled original journey and card-pack policies");
        foreach(var (table,schema) in new[]{(rewards,"reward_id:s,level:i,kind:s,amount:i,ownership:s,requires_class_choice:b,cosmetic_id:o"),
                    (cosmetics,"cosmetic_id:s,kind:s,name_key:s,description_key:s")})
        {
            Check(table.Columns.Count==schema.Split(',').Length,table,"unexpected reward or cosmetic columns");
            foreach(var field in schema.Split(','))
            {
                var parts=field.Split(':');var column=table.Columns.SingleOrDefault(c=>c.Name==parts[0]);
                Check(column is not null&&column.Required==(parts[1]!="o")&&column.Scope==PublishScope.Both&&
                    column.Type==(parts[1]=="i"?ConfigValueType.WholeNumber:parts[1]=="b"?ConfigValueType.Logical:ConfigValueType.Text),table,"invalid reward publication metadata");
            }
        }
        Check(rewards.Rows.Count==30&&rewards.Rows.Select(r=>N(rewards,r,"level")).Order().SequenceEqual(Enumerable.Range(1,30).Select(n=>(double)n)),rewards,"requires exactly levels one through thirty");
        (string Id,string Kind)[] identities=[("trail-seeker","AvatarFrame"),("relic-seeker","Title"),("first-threshold","Collection"),
            ("waymark-seal","CardBack"),("veil-warden","Title"),("veilbound-seal","AvatarFrame"),("fivefold-chronicle","Collection"),
            ("convergent-sigil","CardBack"),("veil-cartographer","Title"),("relicbound-pathfinder","AvatarFrame")];
        foreach(var row in rewards.Rows)
        {
            var level=checked((int)N(rewards,row,"level"));
            var (kind,amount)=level<=20?((level%5) switch {1 or 4=>("EquipmentFragments",10),2=>("WarriorSoul",6),3=>("ClassSoul",2),_=>("CardPack",1)}):("Cosmetic",1);
            var cosmeticIndex=rewards.Columns.Select((c,i)=>(c,i)).Single(v=>v.c.Name=="cosmetic_id").i;
            Check(S(rewards,row,"reward_id")==$"journey-level-{level:D2}"&&S(rewards,row,"kind")==kind&&N(rewards,row,"amount")==amount&&
                S(rewards,row,"ownership")== (kind=="EquipmentFragments"?"SeasonalBound":"PermanentBound")&&
                B(rewards,row,"requires_class_choice")== (kind=="ClassSoul")&&
                Equals(row[cosmeticIndex].Value,level<=20?null:identities[level-21].Id),rewards,"differs from the approved reward, amount, choice or ownership");
        }
        Check(cosmetics.Rows.Count==10,cosmetics,"requires exactly ten cosmetics");
        foreach(var (id,kind) in identities)
        {
            var row=cosmetics.Rows.SingleOrDefault(r=>S(cosmetics,r,"cosmetic_id")==id);
            Check(row is not null&&S(cosmetics,row,"kind")==kind&&S(cosmetics,row,"name_key")==$"journey_cosmetic_{id.Replace('-','_')}_name"&&
                S(cosmetics,row,"description_key")==$"journey_cosmetic_{id.Replace('-','_')}_description",cosmetics,"invalid cosmetic identity, display slot or localized keys");
        }
    }
}
