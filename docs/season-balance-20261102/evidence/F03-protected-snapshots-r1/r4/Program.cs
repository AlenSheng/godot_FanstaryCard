using System.Text.Json;
using System.Text.Json.Nodes;
using System.Security.Cryptography;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;

var inputs=JsonDocument.Parse(File.ReadAllText(args[0])).RootElement;
var config=GameConfigCatalog.Current;
var catalog=CombatCardCatalog.Create(config);
var results=new List<object>();
var errors=0;
foreach(var input in inputs.EnumerateArray())
{
    var id=input.GetProperty("id").GetString();
    try
    {
        var raw=File.ReadAllBytes(input.GetProperty("path").GetString()!);
        if(Convert.ToHexStringLower(SHA256.HashData(raw))!=input.GetProperty("sha256").GetString()) throw new InvalidOperationException("Input SHA mismatch");
        var snapshot=JsonSerializer.Deserialize<BattleRoomSnapshot>(raw) ?? throw new InvalidOperationException("Null snapshot");
        var typed=JsonSerializer.Serialize(snapshot);
        if(!JsonNode.DeepEquals(JsonNode.Parse(raw),JsonNode.Parse(typed))) throw new InvalidOperationException("Typed JSON surface differs from source snapshot");
        var room=BattleRoom.Restore(snapshot,catalog,input.GetProperty("seed").GetInt32());
        var restored=room.Capture();
        var json=JsonSerializer.Serialize(restored);
        var left=JsonNode.Parse(typed)!;
        var right=JsonNode.Parse(json)!;
        var inactiveTimerNormalizations=0;
        var activeBotTimersPreserved=0;
        for(var index=0;index<snapshot.Players.Count;index++)
        {
            var before=snapshot.Players[index];
            var after=restored.Players[index];
            if(before.PlayerId!=after.PlayerId) throw new InvalidOperationException("Player ordering/identity changed");
            if(before.IsBot && before.Phase is RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted && before.BotPveRemaining is not null)
            {
                if(!after.IsBot || after.Phase!=before.Phase || after.BotPveRemaining is not null) throw new InvalidOperationException("Unexpected terminal bot timer change");
                left["Players"]![index]!["BotPveRemaining"]=null;
                right["Players"]![index]!["BotPveRemaining"]=null;
                inactiveTimerNormalizations++;
            }
            else if(before.IsBot && before.Phase==RoomPlayerPhase.Pve && before.Pve?.Phase==PveBattlePhase.Active && before.BotPveRemaining>TimeSpan.Zero)
            {
                if(after.BotPveRemaining!=before.BotPveRemaining) throw new InvalidOperationException("Active bot PVE timer changed");
                activeBotTimersPreserved++;
            }
        }
        if(!JsonNode.DeepEquals(left,right)) throw new InvalidOperationException("Restored capture differs outside the explicitly verified terminal-bot timer normalization");
        if(room.Elapsed!=snapshot.Elapsed || room.Revision!=snapshot.Revision) throw new InvalidOperationException("Restore advanced state");
        results.Add(new{id,ok=true,inactiveTimerNormalizations,activeBotTimersPreserved,revision=room.Revision,elapsed=room.Elapsed,canonical_sha256=Convert.ToHexStringLower(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(json)))});
    }
    catch(Exception error)
    {
        errors++;
        results.Add(new{id,ok=false,type=error.GetType().FullName,message=error.Message});
    }
}
var assemblies=new Dictionary<string,string>();
foreach(var assembly in new[]{typeof(BattleRoom).Assembly,typeof(FantasyCard.Contracts.Players.HeroClassDto).Assembly})
    assemblies[Path.GetFileName(assembly.Location)]=Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(assembly.Location)));
File.WriteAllText(args[1],JsonSerializer.Serialize(new{ok=errors==0,errors,count=results.Count,config.Version,config.ContentHash,assemblies,results,new_gameplay_starts=0,clock_advance_calls=0},new JsonSerializerOptions{WriteIndented=true}));
return errors==0?0:1;
