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
        if(!JsonNode.DeepEquals(JsonNode.Parse(typed),JsonNode.Parse(json))) throw new InvalidOperationException("Restored capture differs from original snapshot");
        if(room.Elapsed!=snapshot.Elapsed || room.Revision!=snapshot.Revision) throw new InvalidOperationException("Restore advanced state");
        results.Add(new{id,ok=true,revision=room.Revision,elapsed=room.Elapsed,canonical_sha256=Convert.ToHexStringLower(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(json)))});
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
