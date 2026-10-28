using System.Collections;
using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using FantasyCard.ConfigExporter;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Persistence;
using FantasyCard.Server.Rooms;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;
using NpgsqlTypes;

internal static class ExactCases
{
    private static readonly string Root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../"));
    private static readonly string Evidence = Path.Combine(Root,"evidence/exact");
    private static readonly CombatCardCatalog Catalog=CombatCardCatalog.CreatePrototype();
    private static readonly DateTimeOffset Now=DateTimeOffset.UnixEpoch.AddSeconds(10);
    private static readonly List<object> Receipts=[];
    private static readonly JsonSerializerOptions PgJson=new(){PropertyNamingPolicy=JsonNamingPolicy.CamelCase,Converters={new JsonStringEnumConverter()}};
    private static int IdCounter;
    private static Guid Id(){var bytes=new byte[16];BitConverter.GetBytes(++IdCounter).CopyTo(bytes,0);return new Guid(bytes);}
    private static void Check(bool condition,string message){if(!condition)throw new InvalidOperationException(message);}
    private static string Hash(object? value)=>Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(value))).ToLowerInvariant();
    private static void Save(string name,object value)=>File.WriteAllText(Path.Combine(Evidence,name+".json"),JsonSerializer.Serialize(value,new JsonSerializerOptions{WriteIndented=true}));
    private static void Receipt(string id,object actual){var row=new{case_id=id,status="Passed",actual};Receipts.Add(row);Console.WriteLine(JsonSerializer.Serialize(row));File.WriteAllText(Path.Combine(Evidence,"cases.jsonl"),string.Join("\n",Receipts.Select(x=>JsonSerializer.Serialize(x)))+"\n");}
    private static PlayerCombatState State(HeroClass c=HeroClass.Mage,CombatEquipmentProfile? eq=null)=>new(c,Enumerable.Repeat("common-01",20).ToArray(),new Random(31),equipment:eq);
    private static CombatCardDefinition Fire(int n)=>Element(CardElement.Fire,n);
    private static CombatCardDefinition Element(CardElement e,int n)=>new($"{e}-{n}",new(ElementalDamage:n,Element:e));
    private static BattleRoom Room(HeroClass c=HeroClass.Mage,NumericalRules? rules=null){var room=new BattleRoom(Id(),"f812-b02",Catalog,77,rules);var m=new MonsterCombatState("test-monster",500,500,7,TimeSpan.FromSeconds(4),[new(MonsterIntentKind.Attack,3,CardElement.Wood)]);room.AddPlayer(new(Id(),c,Enumerable.Repeat("common-01",20).ToArray(),new(Id(),null,[m]),WeaponLevel:1));return room;}
    private static RoomPlayerState Player(BattleRoom r)=>r.GetPlayer(r.Capture().Players[0].PlayerId);
    private static void Hand(RoomPlayerState p,params string[] ids)=>p.Combat.Deck.Restore(new(ids.Select(x=>new CombatCardInstance(Id(),x)).ToArray(),Enumerable.Range(0,20).Select(_=>new CombatCardInstance(Id(),"common-01")).ToArray(),[],.35));
    private static CardResolutionDraft Resolve(CombatCardDefinition[] cards,CombatEquipmentProfile? eq=null,Func<CardElement,double>? resist=null)=>CombatResolver.Resolve(cards,State(eq:eq),resist);
    private static NumericalRules RulesFromTable(IReadOnlyList<FantasyCard.ConfigExporter.ConfigTable> tables)
    {
        // Use production ReadNumerics, with its internal ConfigBundle supplied by this isolated seam.
        var assembly=typeof(GameConfigCatalog).Assembly;var tableType=assembly.GetType("FantasyCard.Domain.Configuration.ConfigTable")!;
        var list=(IList)Activator.CreateInstance(typeof(List<>).MakeGenericType(tableType))!;
        foreach(var t in tables){var cols=t.Columns.Select(c=>c.Name).ToArray();var rows=t.Rows.Select(r=>r.Select(v=>v.Value).ToArray()).ToArray();list.Add(Activator.CreateInstance(tableType,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic,null,[t.Name,cols,rows],null)!);}
        var bundle=Activator.CreateInstance(assembly.GetType("FantasyCard.Domain.Configuration.ConfigBundle")!,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic,null,["b02-hot-fixture",list],null)!;
        return (NumericalRules)typeof(GameConfigCatalog).GetMethod("ReadNumerics",BindingFlags.Static|BindingFlags.NonPublic)!.Invoke(null,[bundle])!;
    }
    private static async Task<NpgsqlDataSource> Database()
    {
        var conn=Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES")??throw new InvalidOperationException("owned PG required");
        var ds=NpgsqlDataSource.Create(conn);await new DatabaseMigrator(ds,NullLogger<DatabaseMigrator>.Instance).StartAsync(CancellationToken.None);return ds;
    }
    private static async Task Persist(RoomSnapshotRepository repo,NpgsqlDataSource db,BattleRoomSnapshot s)
    {
        await using(var cmd=db.CreateCommand("INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',77,$3,'Running',$4) ON CONFLICT(room_id) DO NOTHING")){cmd.Parameters.AddWithValue(Id());cmd.Parameters.AddWithValue(s.RoomId);cmd.Parameters.AddWithValue(s.ConfigVersion);cmd.Parameters.AddWithValue(Now);await cmd.ExecuteNonQueryAsync();}
        await repo.SaveIfDueAsync(s);
    }
    public static async Task Main()
    {
        Directory.CreateDirectory(Evidence);
        var defaultMage=State();var defaultGuardian=State(HeroClass.Guardian);
        Check(defaultMage.FenxianDrawPolicy==FenxianImmediateDrawPolicy.CurrentRhythm && defaultGuardian.GuardianShieldPolicy==GuardianShieldBonusPolicy.CurrentSteps,"defaults");
        var draws=Enumerable.Range(0,5).Select(_=>defaultMage.UpdateFenxian(CardElement.Fire,1).Draw).ToArray();Check(draws.SequenceEqual(new[]{0,0,1,1,2}),"default rhythm");
        Receipt("PR13-B02.1-T02",new{fenxian=defaultMage.FenxianDrawPolicy.ToString(),guardian=defaultGuardian.GuardianShieldPolicy.ToString(),single_core_five_cast_draws=draws});
        var candidateMage=new PlayerCombatState(HeroClass.Mage,Enumerable.Repeat("common-01",20).ToArray(),new Random(31),fenxianImmediateDrawPolicy:FenxianImmediateDrawPolicy.CoreCardsSpent);
        var candidateDraws=Enumerable.Range(0,5).Select(_=>candidateMage.UpdateFenxian(CardElement.Fire,1).Draw).ToArray();Check(candidateDraws.All(x=>x==0),"candidate distinct");
        var candidateGuardian=new PlayerCombatState(HeroClass.Guardian,Enumerable.Repeat("common-01",20).ToArray(),new Random(31),weaponLevel:1,guardianShieldBonusPolicy:GuardianShieldBonusPolicy.FractionalRemainder);
        var bonus=0;var remain=new List<int>();for(var i=0;i<5;i++){var d=candidateGuardian.PreviewShield(1);bonus+=candidateGuardian.GainShield(d.Shield)-1;candidateGuardian.CommitGuardianShieldRemainder(d.RemainderTenthsAfter);remain.Add(candidateGuardian.GuardianShieldRemainderTenths);}Check(bonus==7 && remain.SequenceEqual(new[]{4,8,2,6,0}),"fractional exact");
        Receipt("PR13-B02.1-T03",new{fenxian=candidateMage.FenxianDrawPolicy.ToString(),guardian=candidateGuardian.GuardianShieldPolicy.ToString(),single_core_five_cast_draws=candidateDraws,guardian_bonus_five_casts=bonus,remainder_tenths=remain,independent_from_defaults=true});
        var eq=new CombatEquipmentProfile(new(FireDamageBonus:.14));Func<CardElement,double> resistance=e=>e==CardElement.Fire?-.30:.50;
        var firstFire=Resolve([Fire(8),Element(CardElement.Water,7)],eq,resistance);var firstWater=Resolve([Element(CardElement.Water,7),Fire(8)],eq,resistance);
        Check(firstFire.Damage==19 && firstWater.Damage==6 && firstFire.CoreElement==CardElement.Fire && firstWater.CoreElement==CardElement.Water,"ordered first core");
        var minority=Resolve([Fire(8),Element(CardElement.Water,7),Element(CardElement.Water,7)],eq,_=>-.30);Check(minority.Damage==23 && minority.CoreCount==1 && minority.ConflictPairCount==2,"minority first core");
        Receipt("PR13-B02.2-T01",new{fire_first=firstFire,water_first=firstWater,minority_first_core=minority,input=new{fire=8,water=7,fire_bonus=.14,fire_resistance=-.30,water_resistance=.50}});
        var fuel=new CombatCardDefinition("fuel12",new(ElementalDamage:12,Element:CardElement.Fire,SameElementBonus:2));
        var vector3=Resolve([Fire(8),Fire(3),Fire(12)],eq,_=>-.30);var vector4=Resolve([Fire(8),Fire(3),Fire(6),fuel],eq,_=>-.30);var vector5=Resolve([Fire(8),Fire(3),Fire(6),Fire(10),fuel],eq,_=>-.30);
        Check(new[]{vector3.Damage,vector4.Damage,vector5.Damage}.SequenceEqual(new[]{46,72,113}),"golden vectors");
        var perFloor=Resolve([Fire(3),Fire(3),Fire(3)],eq);Check(perFloor.Damage==12,"per card floor");
        var tune=new CombatCardDefinition("tune4",new(ElementalDamage:4,Element:CardElement.Fire,IsElementTuning:true));var tuning=Resolve([Fire(8),tune,Element(CardElement.Water,7)]);Check(tuning.Damage==17&&tuning.Heal==2,"tuning E0");
        var boss=new CombatCardDefinition("dual",new(ElementalDamage:8,Element:CardElement.Fire,SecondaryElementalDamage:8,SecondaryElement:CardElement.Metal));var dual=Resolve([boss],eq,e=>e==CardElement.Fire?-.30:.60);Check(dual.Damage==14&&dual.CoreElement is null,"dual");
        Receipt("PR13-B02.2-T02",new{inputs=new{vectors=new[]{new[]{8,3,12},new[]{8,3,6,12},new[]{8,3,6,10,12}},fire_bonus=.14,target_fire_resistance=-.30,fuel_base=12,same_element_bonus=2,level=0,weapon=0,no_reveal=true,no_piercing=true},vector3,vector4,vector5,per_card_floor=perFloor,tuning,dual});
        var priest=State(HeroClass.Priest,new(new(),VitalityHealBonus:.20));priest.TakeDamage(40);
        CombatCardDefinition[] withHeal=[Fire(8),Element(CardElement.Water,7),new("heal8",new(Heal:8))];var healing=CombatResolver.Resolve(withHeal,priest);var conflictOnly=CombatResolver.Resolve([Fire(8),Element(CardElement.Water,7)],priest);var plain=Resolve(withHeal);
        Check(healing.Heal==18 && conflictOnly.Heal==2 && plain.Heal==12,"two heal paths");
        Receipt("PR13-B02.2-T03",new{priest_hp=40,maximum_hp=80,weapon_level=0,vitality=.20,ordinary_card_base=8,conflict_pairs=1,ordinary_heal_after_priest_weapon_vitality=16,conflict_E0_recovery_after_vitality=2,healing,conflictOnly,plain});
        var previewRows=new List<object>();
        foreach(var tuple in new[]{(HeroClass.Mage,new[]{"common-22","common-01","common-02","common-03","common-15"}),(HeroClass.Guardian,new[]{"common-17"}),(HeroClass.Priest,new[]{"common-19","common-20","common-15"})})
        {
            var r=Room(tuple.Item1,new(CardsSpentDraw:true,FractionalGuardian:true));var p=Player(r);p.Combat.TakeDamage(30);if(tuple.Item1==HeroClass.Guardian)p.Combat.Restore(p.Combat.Capture() with {GuardianShieldRemainderTenths=8});Hand(p,tuple.Item2);
            var ids=p.Combat.Deck.Hand.Select(x=>x.InstanceId).ToArray();var before=r.Capture();var a=r.PreviewCards(p.PlayerId,p.Pve!.BattleId,"test-monster",ids,r.Revision,Now);var b=r.PreviewCards(p.PlayerId,p.Pve.BattleId,"test-monster",ids,r.Revision,Now);
            var after=r.Capture();Check(Hash(before)==Hash(after)&&Hash(a)==Hash(b),"continuous preview pure");Check(r.DrainCombatFeedback().Count==0,"preview feedback");
            var actual=r.PlayCards(p.PlayerId,p.Pve.BattleId,"test-monster",ids,r.Revision,Now);Check(Hash(a with{RoomRevision=actual.RoomRevision})==Hash(actual),"preview settlement parity");
            Save("preview-"+tuple.Item1,new{before,after,preview=a,second_preview=b,actual,committed=r.Capture()});previewRows.Add(new{hero=tuple.Item1.ToString(),before_state_hash=Hash(before),after_state_hash=Hash(after),before_rng_hash=Hash(before.RandomStreams),after_rng_hash=Hash(after.RandomStreams),before_player_rng_hash=Hash(before.Players[0].Combat.RandomState),after_player_rng_hash=Hash(after.Players[0].Combat.RandomState),before_deck_hash=Hash(before.Players[0].Combat.Deck),after_deck_hash=Hash(after.Players[0].Combat.Deck),before_remainder=before.Players[0].Combat.GuardianShieldRemainderTenths,after_remainder=after.Players[0].Combat.GuardianShieldRemainderTenths,preview=a,actual});
        }
        Receipt("PR13-B02.3-T01",new{seed=77,rows=previewRows});
        var protocolRoom=Room();var pp=Player(protocolRoom);Hand(pp,"common-02","common-06");var fireId=pp.Combat.Deck.Hand[0].InstanceId;var waterId=pp.Combat.Deck.Hand[1].InstanceId;var protoRows=new List<object>();
        foreach(var kind in new[]{"battle.play_cards","combat.preview"})foreach(var ids in new[]{new[]{fireId,waterId},new[]{waterId,fireId}})
        {
            var command=new ClientCommand(kind,"b02-order-"+kind,protocolRoom.Revision,new BattlePlayCardsCommandPayload(pp.Pve!.BattleId,"test-monster",ids));var bytes=RealtimeProtobufCodec.EncodeClient(command);var decoded=RealtimeProtobufCodec.DecodeClient(bytes);var payload=(BattlePlayCardsCommandPayload)decoded.Payload!;Check(ids.SequenceEqual(payload.CardInstanceIds),"wire list order");var direct=protocolRoom.PreviewCards(pp.PlayerId,pp.Pve.BattleId,payload.TargetId,ids,protocolRoom.Revision,Now);var wired=protocolRoom.PreviewCards(pp.PlayerId,payload.BattleId,payload.TargetId,payload.CardInstanceIds,decoded.ExpectedRevision!.Value,Now);Check(Hash(direct)==Hash(wired),"wire resolve parity");File.WriteAllBytes(Path.Combine(Evidence,$"wire-{kind.Replace('.','-')}-{ids[0]}.bin"),bytes);protoRows.Add(new{kind,selected=ids,decoded=payload.CardInstanceIds,wire_sha256=Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),result=wired});
        }
        Receipt("PR13-B02.3-T02",new{codec="production RealtimeProtobufCodec",rows=protoRows});
        var beforeInvalid=protocolRoom.Capture();var revisionRejected=false;try{protocolRoom.PreviewCards(pp.PlayerId,pp.Pve!.BattleId,"test-monster",[fireId],protocolRoom.Revision-1,Now);}catch(DomainValidationException){revisionRejected=true;}Check(revisionRejected&&Hash(beforeInvalid)==Hash(protocolRoom.Capture()),"old revision pure reject");Receipt("PR13-B02.3-T03",new{layer="Domain; client receipt separately",current_revision=protocolRoom.Revision,requested_revision=protocolRoom.Revision-1,rejected=revisionRejected,before_hash=Hash(beforeInvalid),after_hash=Hash(protocolRoom.Capture())});
        await using var db=await Database();using var metrics=new ServerMetrics();var repo=new RoomSnapshotRepository(db,TimeProvider.System,metrics);
        var fixture=Path.Combine(Root,"fixtures");Directory.CreateDirectory(fixture);var workbook=Path.Combine(fixture,"hot-source.xlsx");File.Copy(Path.Combine(Root,"source/config/FantasyCard_Config.xlsx"),workbook,true);var sourceBefore=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(workbook))).ToLowerInvariant();
        var oldTables=XlsxConfigReader.Read(workbook);var oldRules=RulesFromTable(oldTables);var locked=Room(HeroClass.Guardian,oldRules);var lockedBefore=locked.Capture();
        var psi=new ProcessStartInfo("python3"){RedirectStandardOutput=true,RedirectStandardError=true};psi.ArgumentList.Add(Path.Combine(Root,"harness/mutate_workbook.py"));psi.ArgumentList.Add(workbook);using(var proc=Process.Start(psi)!){await proc.WaitForExitAsync();Check(proc.ExitCode==0,"workbook hot update");}
        var newTables=XlsxConfigReader.Read(workbook);var bytesHot=ConfigCompiler.Compile("b02-isolated-hot-on",newTables,out var contentHash);File.WriteAllBytes(Path.Combine(fixture,"hot.config.bytes"),bytesHot);var changedRules=RulesFromTable(newTables);Check(changedRules.CardsSpentDraw&&changedRules.FractionalGuardian&&!oldRules.CardsSpentDraw&&!oldRules.FractionalGuardian,"source table changed");
        Check(Hash(lockedBefore)==Hash(locked.Capture()),"existing room cannot change policy");await Persist(repo,db,locked.Capture());var persistedLocked=(await repo.GetAsync(locked.RoomId))!;var restoredLocked=BattleRoom.Restore(persistedLocked,Catalog,999);Check(Hash(locked.Capture())==Hash(restoredLocked.Capture()),"PG locked policy preserve");var fresh=Room(HeroClass.Guardian,changedRules);Check(Player(fresh).Combat.GuardianShieldPolicy==GuardianShieldBonusPolicy.FractionalRemainder,"new explicit source rules");
        Save("locked-room",new{before=lockedBefore,persisted=persistedLocked,restored=restoredLocked.Capture(),fresh=fresh.Capture()});Receipt("PR13-B02.4-T01",new{source_before_sha256=sourceBefore,source_after_sha256=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(workbook))).ToLowerInvariant(),compiled_content_sha256=contentHash,oldRules,changedRules,room_hash_before=Hash(lockedBefore),room_hash_after=Hash(locked.Capture()),pg_restored_hash=Hash(restoredLocked.Capture()),old_room_guardian_policy=Player(locked).Combat.GuardianShieldPolicy.ToString(),new_room_guardian_policy=Player(fresh).Combat.GuardianShieldPolicy.ToString(),hot_update_scope="isolated workbook/export; no runtime reload API is present"});
        var duelRoom=Room(HeroClass.Guardian,new(CardsSpentDraw:true,FractionalGuardian:true));var dp=Player(duelRoom);dp.Combat.TakeDamage(31);dp.Combat.GainShield(11);dp.Combat.ApplyDrawSpeed(TimeSpan.FromSeconds(9),-.15);dp.Combat.ApplyDrawBlockSpeed(TimeSpan.FromSeconds(3));dp.Combat.SetFenxian(CardElement.Fire,3,4);dp.Combat.Restore(dp.Combat.Capture()with{GuardianShieldRemainderTenths=4});Hand(dp,"common-17","common-19","common-01");dp.Pve!.Monsters[0].SetRuntimeState(1,TimeSpan.FromSeconds(2),TimeSpan.FromSeconds(.4),true,2,TimeSpan.FromSeconds(.5),new Dictionary<string,TimeSpan>());var pveBefore=dp.Pve.Capture();var combatBefore=dp.Combat.Capture();var opponent=Id();duelRoom.AddPlayer(new(opponent,HeroClass.Mage,Enumerable.Repeat("common-01",20).ToArray(),null));var duel=duelRoom.StartDuel(dp.PlayerId,opponent,Now);
        Check(dp.Combat.GuardianShieldPolicy==GuardianShieldBonusPolicy.FractionalRemainder,"duel work policy");dp.Combat.TakeDamage(9);dp.Combat.CommitGuardianShieldRemainder(8);Hand(dp,"common-11");await Persist(repo,db,duelRoom.Capture());var duelPersisted=(await repo.GetAsync(duelRoom.RoomId))!;var restoredDuel=BattleRoom.Restore(duelPersisted,Catalog,333);restoredDuel.EndDuelSurvived(duel.DuelId,DuelEndReason.MutualLeave);var restoredDp=restoredDuel.GetPlayer(dp.PlayerId);Check(Hash(combatBefore)==Hash(restoredDp.Combat.Capture()),"PVE combat complete restored");Check(Hash(pveBefore)==Hash(restoredDp.Pve!.Capture()),"PVE monsters complete restored");Save("duel-recovery",new{combatBefore,pveBefore,duelPersisted,restored=restoredDuel.Capture()});Receipt("PR13-B02.4-T02",new{combat_before_hash=Hash(combatBefore),combat_after_hash=Hash(restoredDp.Combat.Capture()),pve_before_hash=Hash(pveBefore),pve_after_hash=Hash(restoredDp.Pve.Capture()),restored_remainder=restoredDp.Combat.GuardianShieldRemainderTenths,restored_policy=restoredDp.Combat.GuardianShieldPolicy.ToString(),pg_persisted_duel=true,end_reason="MutualLeave"});
        var legacy=JsonNode.Parse(JsonSerializer.Serialize(fresh.Capture(),PgJson))!.AsObject();legacy.Remove("numerics");foreach(var pl in legacy["players"]!.AsArray()){var c=pl!["combat"]!.AsObject();c.Remove("fenxianPolicy");c.Remove("guardianPolicy");c.Remove("guardianShieldRemainderTenths");}var legacySnapshot=JsonSerializer.Deserialize<BattleRoomSnapshot>(legacy.ToJsonString(),PgJson)!;await Persist(repo,db,legacySnapshot);await using(var cmd=db.CreateCommand("UPDATE room_snapshots SET snapshot_json=$1 WHERE room_id=$2")){cmd.Parameters.Add(new NpgsqlParameter{NpgsqlDbType=NpgsqlDbType.Jsonb,Value=legacy.ToJsonString()});cmd.Parameters.AddWithValue(legacySnapshot.RoomId);await cmd.ExecuteNonQueryAsync();}var oldPg=(await repo.GetAsync(legacySnapshot.RoomId))!;var oldRestored=BattleRoom.Restore(oldPg,Catalog,91);Check(Player(oldRestored).Combat.FenxianDrawPolicy==FenxianImmediateDrawPolicy.CurrentRhythm&&Player(oldRestored).Combat.GuardianShieldPolicy==GuardianShieldBonusPolicy.CurrentSteps,"missing defaults");
        var live=Player(locked).Combat;var liveBefore=live.Capture();var invalidRows=new List<object>();foreach(var invalid in new[]{liveBefore with{Hp=1,FenxianPolicy=(FenxianImmediateDrawPolicy)999},liveBefore with{Hp=1,GuardianPolicy=(GuardianShieldBonusPolicy)999},liveBefore with{Hp=1,GuardianShieldRemainderTenths=10}}){var rejected=false;try{live.Restore(invalid);}catch(DomainValidationException){rejected=true;}Check(rejected&&Hash(liveBefore)==Hash(live.Capture()),"invalid before mutation");invalidRows.Add(new{rejected,before_hash=Hash(liveBefore),after_hash=Hash(live.Capture()),invalid});}
        var invalidRoom=legacySnapshot with{Players=legacySnapshot.Players.Select((p,i)=>i==0?p with{Combat=p.Combat with{Hp=1,FenxianPolicy=(FenxianImmediateDrawPolicy)999}}:p).ToArray()};await using(var cmd=db.CreateCommand("UPDATE room_snapshots SET snapshot_json=$1 WHERE room_id=$2")){cmd.Parameters.Add(new NpgsqlParameter{NpgsqlDbType=NpgsqlDbType.Jsonb,Value=JsonSerializer.Serialize(invalidRoom,PgJson)});cmd.Parameters.AddWithValue(invalidRoom.RoomId);await cmd.ExecuteNonQueryAsync();}var invalidPg=(await repo.GetAsync(invalidRoom.RoomId))!;var roomRejected=false;try{BattleRoom.Restore(invalidPg,Catalog,91);}catch(DomainValidationException){roomRejected=true;}Check(roomRejected&&Hash(lockedBefore)==Hash(locked.Capture()),"invalid room no partial live restore");Save("old-invalid",new{legacy_json=legacy,legacy_pg=oldPg,legacy_restored=oldRestored.Capture(),invalidRows,invalidRoom,invalidPg});Receipt("PR13-B02.4-T03",new{legacy_missing_fields=new[]{"numerics","fenxianPolicy","guardianPolicy","guardianShieldRemainderTenths"},legacy_policy=oldRestored.Numerics,legacy_fenxian=Player(oldRestored).Combat.FenxianDrawPolicy.ToString(),legacy_guardian=Player(oldRestored).Combat.GuardianShieldPolicy.ToString(),invalidRows,invalid_room_rejected=roomRejected,live_room_hash=Hash(locked.Capture()),pg_legacy_roundtrip=true,pg_input_has_missing_fields=true,pg_invalid_loaded_via_production_repository=true});
    }
}
