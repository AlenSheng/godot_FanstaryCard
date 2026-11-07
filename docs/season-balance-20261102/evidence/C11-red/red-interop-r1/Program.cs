using System.Text.Json;
using FantasyCard.Contracts.Realtime;
var root=args[0];
if(args.Length>1 && args[1]=="decode")
{
 var decoded=RealtimeProtobufCodec.DecodeClient(File.ReadAllBytes(Path.Combine(root,"godot-claim.bin")));
 if(decoded.Type!="reward.choice.claim" || decoded.Payload is not RewardChoiceClaimCommandPayload {OptionId:"red:00000000-0000-0000-0000-000000000001",ReplaceItemId:"original-bag-item",Equip:false})throw new InvalidDataException("Godot replacement differs on the server.");
 File.WriteAllText(Path.Combine(root,"server-decode.json"),JsonSerializer.Serialize(new {ok=true,type=decoded.Type,decoded.Payload}));return;
}
var item=new RoomInventoryItemPayload("00000000-0000-0000-0000-000000000001","Equipment",1,false,new("Head","Red","Fire","Piercing","DrawInterval",0,false,"Inferno","Fire","season-equipment-v1"));
foreach(var name in new[]{"pending","evaluating","legacy"})
{
 var player=new RoomPlayerPayload(Guid.Parse("00000000-0000-0000-0000-000000000002"),"Mage","Choice",new(70,70,70,0),[],0,0,"0",[],20,[],[],RedEvaluationPending:name=="evaluating",PendingRedItem:name=="pending"?item:null);
 var snapshot=new RoomSnapshotEventPayload(Guid.Parse("00000000-0000-0000-0000-000000000003"),Guid.Parse("00000000-0000-0000-0000-000000000004"),9,"season-v1-config-7",new(0,0),[],[],new(false,"BOSS",false,[]),player,null,null,null,null,null,name=="pending"?["choice.read","choice.pick"]:[],Season:new("original-season","D2","season-v1","season-v1-config-7","season-equipment-v1"));
 var bytes=RealtimeProtobufCodec.EncodeServer(new("room.snapshot","red-interop",snapshot,"00000000-0000-0000-0000-000000000005",1,DateTimeOffset.UnixEpoch));
 var roundtrip=(RoomSnapshotEventPayload)RealtimeProtobufCodec.DecodeServer(bytes).Payload!;
 if(roundtrip.Player.RedEvaluationPending!=(name=="evaluating") || roundtrip.Player.PendingRedItem?.ItemId!=(name=="pending"?item.ItemId:null))throw new InvalidDataException("Server roundtrip failed.");
 File.WriteAllBytes(Path.Combine(root,name+".bin"),bytes);
}
Console.WriteLine("Server codec wrote three original fixture frames.");
