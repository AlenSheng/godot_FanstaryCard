using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;

if(args.Length!=1||File.Exists(args[0]))throw new InvalidOperationException("One new owned output path required.");
var rows=new List<object>();var members=0;var intentRows=0;
void Capture(string key,string group,ChaosMapLayer layer,CardElement? treasure=null)
{
    var cell=new ChaosMapCell(new(0,0),layer,group=="BOSS",false,false,group,TreasureElement:treasure);
    var battle=PveBattleFactory.Create(cell);var order=0;
    foreach(var monster in battle.Monsters)
    {
        order++;members++;intentRows+=monster.Intents.Count;
        rows.Add(new{profile_id=key+":"+order,group_id=key,member_order=order,monster_id=monster.MonsterId,hp=monster.MaximumHp,shield=monster.Shield,
            interval_ms=(int)monster.AttackInterval.TotalMilliseconds,amplification_bp=(int)Math.Round(monster.ElementalAmplification*10000),
            intents=monster.Intents.Select((i,n)=>new{order=n+1,kind=i.Kind.ToString(),i.Value,element=i.Element.ToString()}).ToArray()});
    }
}
for(var i=1;i<=8;i++)Capture("O"+i,"O"+i,ChaosMapLayer.Outer);
for(var i=1;i<=5;i++)Capture("M"+i,"M"+i,ChaosMapLayer.Middle);
for(var i=1;i<=6;i++)Capture("E"+i,"E"+i,ChaosMapLayer.Middle);
Capture("BOSS","BOSS",ChaosMapLayer.Core);
foreach(var element in Enum.GetValues<CardElement>())Capture("BOX-"+element,"BOX",ChaosMapLayer.Outer,element);
var result=new{scope="Exact legacy factory base definitions. No players, room actor, combat resolver or time advancement.",factory_calls=26,profiles=members,intent_rows=intentRows,new_combat_encounters=0,rows};
File.WriteAllText(args[0],JsonSerializer.Serialize(result,new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine(JsonSerializer.Serialize(new{factory_calls=26,profiles=members,intent_rows=intentRows,new_combat_encounters=0}));
