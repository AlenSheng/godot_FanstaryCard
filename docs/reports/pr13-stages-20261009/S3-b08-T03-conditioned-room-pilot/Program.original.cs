using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

var source = args[0];var output = args[1];var samples = int.Parse(args[2]);var block = int.Parse(args[3]);
if (source.Length != 40 || samples is not (3 or 1000) || block is < 0 or > 2 || Directory.Exists(output))
    throw new ArgumentException("Frozen source, sample count, seed block and new output required.");
Directory.CreateDirectory(output);
var config = GameConfigCatalog.Current;var catalog = CombatCardCatalog.CreatePrototype();
var filtered=args.Length==8;
if(samples==1000&&!filtered)throw new ArgumentException("Full runs require one frozen stratum per owned unit.");
var heroes=filtered?new[]{Enum.Parse<HeroClass>(args[4])}:new[]{HeroClass.Mage,HeroClass.Priest,HeroClass.Guardian};
var groups=filtered?new[]{args[5]}:new[]{"O1","O6","E1","BOSS"};
var elements=filtered?new[]{Enum.Parse<CardElement>(args[6])}:Enum.GetValues<CardElement>().Where(e=>e!=CardElement.None).ToArray();
var levels=filtered?new[]{int.Parse(args[7])}:new[]{0,5};
var strata=heroes.Length*groups.Length*elements.Length*levels.Length;
string[] common = ["C01","C02","C03","C04","C05","C06","C07","C17","C18","C20","C25","C26","C27","C29"];
string[] slots = ["Head","Chest","Hands","Legs","Feet"];
string[] conditions = ["full","one-capacity","empty","zero-printed-full"];
var policies = config.Numerics;
if (policies.CardsSpentDraw || policies.FractionalGuardian || policies.OptionalMonsterPool)
    throw new InvalidOperationException("Production candidate must remain off.");
var rawPath = Path.Combine(output,"witnesses.original.jsonl.gz");var statesPath = Path.Combine(output,"states.original.jsonl.gz");
long witnesses=0,rawBytes=0,stateBytes=0;var stateHashes = new HashSet<string>();
using var stream = new GZipStream(new FileStream(rawPath,FileMode.CreateNew),CompressionLevel.Fastest);
using var stateStream = new GZipStream(new FileStream(statesPath,FileMode.CreateNew),CompressionLevel.Fastest);
string Capture(BattleRoom room)
{
    var text=JsonSerializer.Serialize(room.Capture());var bytes=Encoding.UTF8.GetBytes(text);var hash=Convert.ToHexStringLower(SHA256.HashData(bytes));
    if(stateHashes.Add(hash))
    {
        var row=Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { sha256=hash, original_state_json=text })+"\n");
        stateBytes+=row.Length;if(stateBytes>2147483648L)throw new InvalidOperationException("State capture budget exceeded.");stateStream.Write(row);
    }
    return hash;
}
void Require(bool value,string reason){if(!value)throw new InvalidOperationException(reason);}
foreach(var hero in heroes)
foreach(var group in groups)
foreach(var element in elements)
foreach(var level in levels)
for(var seed=440001+block*1000;seed<440001+block*1000+samples;seed++)
{
    var prefix=hero switch{HeroClass.Mage=>"MAG",HeroClass.Priest=>"PRI",_=>"GUA"};
    var cards=common.Concat(Enumerable.Range(1,6).Select(i=>$"{prefix}-{i:D2}")).ToArray();
    var owned=config.Cards.Where(c=>c.Enabled&&c.IsCodex&&c.MonsterType is null).ToDictionary(c=>c.CardId,c=>new OwnedCard(c.CardId,c.HeroClass,(CardRarity)c.Rarity,1,false));
    DeckRules.Validate(hero,cards,owned);Require(cards.Length==20&&cards.Distinct().Count()==20,"Twenty-card legal budget changed.");
    var baselineItems=slots.Select((slot,i)=>new CombatEquipmentItem(new Guid(seed,0,0,0,0,0,0,0,0,0,(byte)(i+1)),slot,"Purple",level,element,"Bulwark","DrawInterval")).ToArray();
    var baselineProfile=EquipmentCombatRules.Calculate(baselineItems);
    var original=new BattleRoom(Guid.NewGuid(),config.Version,catalog,seed,policies);
    var actor=original.AddPlayer(new BattleRoomPlayerSetup(Guid.NewGuid(),hero,cards,null,WeaponLevel:level,Equipment:baselineProfile));
    var map=ChaosMapGenerator.Generate(seed,1).Capture();var cell=map.Cells.First(c=>c.Layer==ChaosMapLayer.Outer&&!c.IsBoss);
    original.InitializeMap(ChaosMapState.Restore(map with {Cells=map.Cells.Select(c=>c.Position==cell.Position?c with{MonsterGroupId=group,HasSpring=false}:c).ToArray(),SpawnPositions=[cell.Position]}));
    var baseline=original.Capture();var player=baseline.Players.Single();var all=player.Combat.Deck.Hand.Concat(player.Combat.Deck.Library).Concat(player.Combat.Deck.Discard).ToArray();
    Require(all.Length==20&&all.Select(c=>c.InstanceId).Distinct().Count()==20&&all.All(c=>c.Level==0),"Original card instances or level changed.");
    foreach(var upgraded in new[]{false,true})
    foreach(var condition in conditions)
    {
        var items=baselineItems.Select((item,i)=>upgraded&&i==0?item with{Quality="Orange"}:item).ToArray();var profile=EquipmentCombatRules.Calculate(items);
        var chosen=all.Single(c=>c.CardId==(condition=="zero-printed-full"?"C01":"C17"));
        var hand=new[]{chosen}.Concat(all.Where(c=>c.InstanceId!=chosen.InstanceId).Take(4)).ToArray();
        var shieldCap=player.Combat.MaximumHp/2;var initial=condition switch{"full"=>shieldCap,"one-capacity"=>shieldCap-1,"zero-printed-full"=>shieldCap,_=>0};
        var combat=player.Combat with{Hp=player.Combat.MaximumHp,Shield=initial,Equipment=profile,Deck=new CombatDeckSnapshot(hand,all.Except(hand).ToArray(),[],0)};
        var room=BattleRoom.Restore(baseline with{Players=[player with{Combat=combat}]},catalog,seed);var current=room.GetPlayer(actor.PlayerId);var pve=current.Pve!;
        var target=pve.Monsters.First(m=>!m.IsDead);var selected=new[]{chosen.InstanceId};var before=Capture(room);var rawCard=catalog.Get(chosen.CardId,chosen.Level,chosen.ElementOverride);
        var requested=CombatResolver.Resolve([rawCard],current.Combat,target.ElementalResistance).Shield;
        var expected=condition=="zero-printed-full"?0:(int)Math.Floor(rawCard.Effect.Shield*(hero==HeroClass.Guardian?1.45:1)*(1+profile.BulwarkShieldBonus))+(hero==HeroClass.Guardian?new[]{1,1,2,2,3,3}[level]:0);
        Require(requested==expected,"Published requested shield oracle mismatch.");
        if(condition!="zero-printed-full")Require(rawCard.Effect.Shield>0&&requested>0,"Real positive shield card required.");
        else Require(rawCard.Effect.Shield==0&&requested==0,"Zero printed source must not create free shield.");
        var preview=room.PreviewCards(current.PlayerId,pve.BattleId,target.MonsterId,selected,room.Revision,DateTimeOffset.UnixEpoch);
        Require(Capture(room)==before,"Preview mutated the original room.");
        var revision=room.Revision;var resolution=room.PlayCards(current.PlayerId,pve.BattleId,target.MonsterId,selected,revision,DateTimeOffset.UnixEpoch);
        var effective=Math.Min(requested,shieldCap-initial);var overflow=requested-effective;
        Require(resolution.ShieldGain==effective&&current.Combat.Shield==initial+effective,"Cap/effective shield differs.");
        Require(JsonSerializer.Serialize(preview with{RoomRevision=resolution.RoomRevision})==JsonSerializer.Serialize(resolution),"Preview/play mismatch.");
        var after=Capture(room);var resulting=current.Combat.Deck.Capture();var resultingCards=resulting.Hand.Concat(resulting.Library).Concat(resulting.Discard).ToArray();
        Require(resultingCards.Length==20&&all.Select(c=>c.InstanceId).Order().SequenceEqual(resultingCards.Select(c=>c.InstanceId).Order()),"Card budget or identity changed.");
        Require(!resulting.Hand.Any(c=>c.InstanceId==chosen.InstanceId)&&resulting.Discard.Count(c=>c.InstanceId==chosen.InstanceId)==1,"Selected instance not spent exactly once.");
        Require(room.Numerics==policies&&current.Combat.GuardianShieldRemainderTenths==0,"Frozen current policy/remainder changed.");
        var row=Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new {schema="controlled_room_T03_boundary_v1",source_sha=source,hero=hero.ToString(),group,element=element.ToString(),level,block,seed,arm=upgraded?"SingleOrangeHead":"BaselinePurple",condition,items,selected=chosen.InstanceId,card_id=chosen.CardId,printed_shield=rawCard.Effect.Shield,initial_shield=initial,shield_cap=shieldCap,requested,effective,overflow,before,after,preview,resolution,twenty_original_instances=true,candidate_activation=false})+"\n");
        rawBytes+=row.Length;if(rawBytes>134217728L)throw new InvalidOperationException("Witness part budget exceeded.");stream.Write(row);witnesses++;
    }
}
stream.Dispose();stateStream.Dispose();
File.WriteAllText(Path.Combine(output,"summary.original.json"),JsonSerializer.Serialize(new {passed=true,source_sha=source,samples,block,strata,arms=2,conditions=4,expected_witnesses=(long)strata*samples*2*4,witnesses,rawBytes,stateBytes,original_state_count=stateHashes.Count,candidate_activation=false,whole_experiment_accepted=false,scope="Controlled legal real Room.PlayCards boundary setup; not representative encounters, natural cycles or capacity"}));
Require(witnesses==(long)strata*samples*2*4,"Complete controlled matrix required.");
