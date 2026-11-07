using System.Globalization;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Configuration;

public sealed record SeasonMonsterTuningRow(string Id,string RuleId,string BaselineId,string GroupId,int MemberOrder,
    string MonsterId,int BaseHp,int BaseShield,int ShieldIntentValue);

/// <summary>Published seasonal overrides applied to the immutable legacy base before difficulty scaling.</summary>
public sealed class SeasonMonsterTuningConfig
{
    public const string Version="season-monster-tuning-v1";
    public const string Baseline="gdd-0.70-fixed-base-v1";
    private static readonly string[] Groups=["E1","E3","E4","E6"];
    private readonly Dictionary<string,SeasonMonsterTuningRow> _groups;
    public IReadOnlyList<SeasonMonsterTuningRow> Rows {get;}

    public SeasonMonsterTuningConfig(IReadOnlyList<SeasonMonsterTuningRow> rows)
    {
        if(rows.Count!=4||!rows.Select(r=>r.GroupId).Order(StringComparer.Ordinal).SequenceEqual(Groups))
            throw new InvalidDataException("SeasonMonsterTuning requires exactly the four original shield-elite groups.");
        foreach(var row in rows)
        {
            if(row.RuleId!=Version||row.BaselineId!=Baseline||row.MemberOrder!=1||row.Id!=row.GroupId+":"+row.MemberOrder.ToString(CultureInfo.InvariantCulture)||
                row.BaseHp is <1 or >10000||row.BaseShield<0||row.BaseShield>row.BaseHp/2||row.ShieldIntentValue<0||row.ShieldIntentValue>row.BaseHp/2)
                throw new InvalidDataException("SeasonMonsterTuning identity or bounded base values are invalid.");
            var original=PveBattleFactory.Create(new(new(1,1),ChaosMapLayer.Middle,false,false,false,row.GroupId)).Monsters[0];
            if(original.MonsterId!=row.MonsterId||original.Intents.Count(i=>i.Kind==MonsterIntentKind.Shield)!=1)
                throw new InvalidDataException("SeasonMonsterTuning does not reference its original group member and shield step.");
        }
        Rows=Array.AsReadOnly(rows.ToArray());_groups=Rows.ToDictionary(r=>r.GroupId,StringComparer.Ordinal);
    }

    internal MonsterCombatState[] ApplyBase(string groupId,MonsterCombatState[] members)
    {
        if(!_groups.TryGetValue(groupId,out var row))return members;
        if(members.Length<row.MemberOrder||members[row.MemberOrder-1].MonsterId!=row.MonsterId)
            throw new InvalidDataException("The frozen monster tuning target differs from the factory base.");
        var result=members.ToArray();var original=result[row.MemberOrder-1];
        result[row.MemberOrder-1]=new(original.MonsterId,row.BaseHp,row.BaseHp,row.BaseShield,original.AttackInterval,
            original.Intents.Select(i=>i.Kind==MonsterIntentKind.Shield?i with{Value=row.ShieldIntentValue}:i).ToArray(),original.ElementalAmplification);
        return result;
    }
}
