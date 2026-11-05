using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.ConfigExporter;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Static factory and catalog contracts. These do not advance combat or spend C16 encounters.</summary>
public sealed class SeasonMonsterTuningContractTests
{
    private static readonly string[] Names=["id","rule_id","baseline_id","group_id","member_order","monster_id","base_hp","base_shield","shield_intent_value"];
    private static readonly JsonSerializerOptions Json=new(){WriteIndented=false};

    [Fact]
    public void CurrentPublishedBundleIncludesCompleteTuningAndOld14RemainsWithoutIt()
    {
        var current=GameConfigCatalog.Current;var old=Archived();Assert.NotEqual(old.Version,current.Version);
        Assert.NotNull(current.SeasonMonsterTuning);Assert.Equal(4,current.SeasonMonsterTuning.Rows.Count);Assert.Null(old.SeasonMonsterTuning);
        var reload=GameConfigCatalog.Load(current.ExportPublishedBytes());Assert.Equal(current.ContentHash,reload.ContentHash);
        Assert.Equal(current.SeasonMonsterTuning.Rows,reload.SeasonMonsterTuning!.Rows);
    }

    [Fact]
    public void LegacyFactoryMatchesEveryPinnedInitialMemberAndIntentIncludingTreasureElements()
    {
        using var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("MonsterLegacyBaseline")!;using var bytes=new MemoryStream();stream.CopyTo(bytes);
        Assert.Equal("d0d3f5ecf05ab9189a481a48a59ab192f753453cdcecf607c34583fe0dc0b477",Convert.ToHexStringLower(SHA256.HashData(bytes.ToArray())));
        using var data=JsonDocument.Parse(bytes.ToArray());var count=0;
        foreach(var row in data.RootElement.GetProperty("rows").EnumerateArray())
        {
            var group=row.GetProperty("group_id").GetString()!;var treasure=group.StartsWith("BOX-",StringComparison.Ordinal)?Enum.Parse<CardElement>(group[4..]):(CardElement?)null;
            var actual=PveBattleFactory.Create(new(new(0,0),group[0]=='O'||treasure is not null?ChaosMapLayer.Outer:group=="BOSS"?ChaosMapLayer.Core:ChaosMapLayer.Middle,group=="BOSS",false,false,treasure is null?group:"BOX",TreasureElement:treasure)).Monsters[row.GetProperty("member_order").GetInt32()-1];
            Assert.Equal(row.GetProperty("monster_id").GetString(),actual.MonsterId);Assert.Equal(row.GetProperty("hp").GetInt32(),actual.MaximumHp);Assert.Equal(row.GetProperty("shield").GetInt32(),actual.Shield);
            Assert.Equal(row.GetProperty("interval_ms").GetInt32(),actual.AttackInterval.TotalMilliseconds);Assert.Equal(row.GetProperty("amplification_bp").GetInt32(),Math.Round(actual.ElementalAmplification*10000));
            var intents=row.GetProperty("intents").EnumerateArray().ToArray();Assert.Equal(intents.Length,actual.Intents.Count);
            for(var i=0;i<intents.Length;i++){Assert.Equal(intents[i].GetProperty("kind").GetString(),actual.Intents[i].Kind.ToString());Assert.Equal(intents[i].GetProperty("Value").GetInt32(),actual.Intents[i].Value);Assert.Equal(intents[i].GetProperty("element").GetString(),actual.Intents[i].Element.ToString());}
            count++;
        }
        Assert.Equal(35,count);
    }

    [Fact]
    public void Archived14RemainsWithoutOverridesWhileCompiledControlsApplyBeforeScalingOnlyToTheSpecifiedMember()
    {
        var old=Archived();var next=Control();Assert.Null(old.SeasonMonsterTuning);Assert.NotNull(next.SeasonMonsterTuning);
        Assert.Equal("season-v1-config-14",old.Version);Assert.Equal("f015f18d13ddfa022cb50cc821574481a21976c0d0f21d3f4ae10dcbfaa28e62",old.ContentHash);
        var cell=new ChaosMapCell(new(1,1),ChaosMapLayer.Middle,false,false,false,"E6");
        var baseline=PveBattleFactory.Create(cell,next.SeasonDifficulty(5));var tuned=PveBattleFactory.Create(cell,next.SeasonDifficulty(5),tuning:next.SeasonMonsterTuning);
        Assert.Equal(1280,tuned.Monsters[0].MaximumHp);Assert.Equal(80,tuned.Monsters[0].Shield);Assert.Equal(2,Assert.Single(tuned.Monsters[0].Intents,i=>i.Kind==MonsterIntentKind.Shield).Value);
        Assert.Equal(JsonSerializer.Serialize(baseline.Monsters[1].Capture(),Json),JsonSerializer.Serialize(tuned.Monsters[1].Capture(),Json));
        Assert.Equal(baseline.Monsters[0].AttackInterval,tuned.Monsters[0].AttackInterval);Assert.Equal(baseline.Monsters[0].ElementalAmplification,tuned.Monsters[0].ElementalAmplification);
        Assert.Equal(12,Assert.Single(baseline.Monsters[0].Intents,i=>i.Kind==MonsterIntentKind.Shield).Value);
        var boss=new ChaosMapCell(new(2,2),ChaosMapLayer.Core,true,false,false,"BOSS");
        Assert.Equal(JsonSerializer.Serialize(PveBattleFactory.Create(boss,next.SeasonDifficulty(5),next.SeasonThemes!.Selected).Monsters[0].Capture(),Json),
            JsonSerializer.Serialize(PveBattleFactory.Create(boss,next.SeasonDifficulty(5),next.SeasonThemes.Selected,next.SeasonMonsterTuning).Monsters[0].Capture(),Json));
    }

    [Fact]
    public void AllUnlistedMembersAndIntentFieldsRemainUnchangedWithTuningEnabled()
    {
        var config=Control();var tuning=config.SeasonMonsterTuning!;
        using var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("MonsterLegacyBaseline")!;using var data=JsonDocument.Parse(stream);
        foreach(var row in data.RootElement.GetProperty("rows").EnumerateArray())
        {
            var group=row.GetProperty("group_id").GetString()!;var member=row.GetProperty("member_order").GetInt32();var treasure=group.StartsWith("BOX-",StringComparison.Ordinal)?Enum.Parse<CardElement>(group[4..]):(CardElement?)null;
            var cell=new ChaosMapCell(new(0,0),group[0]=='O'||treasure is not null?ChaosMapLayer.Outer:group=="BOSS"?ChaosMapLayer.Core:ChaosMapLayer.Middle,group=="BOSS",false,false,treasure is null?group:"BOX",TreasureElement:treasure);
            var old=PveBattleFactory.Create(cell,config.SeasonDifficulty(0)).Monsters[member-1];var next=PveBattleFactory.Create(cell,config.SeasonDifficulty(0),tuning:tuning).Monsters[member-1];
            var change=tuning.Rows.SingleOrDefault(r=>r.GroupId==group&&r.MemberOrder==member);
            if(change is null)Assert.Equal(JsonSerializer.Serialize(old.Capture(),Json),JsonSerializer.Serialize(next.Capture(),Json));
            else
            {
                Assert.Equal(SeasonDifficultyConfig.Scale(change.BaseHp,config.SeasonDifficulty(0).HpBasisPoints),next.MaximumHp);Assert.Equal(SeasonDifficultyConfig.Scale(change.BaseShield,config.SeasonDifficulty(0).ShieldBasisPoints),next.Shield);Assert.Equal(old.AttackInterval,next.AttackInterval);Assert.Equal(old.ElementalAmplification,next.ElementalAmplification);
                Assert.Equal(old.Intents.Count,next.Intents.Count);
                for(var i=0;i<old.Intents.Count;i++)Assert.Equal(old.Intents[i].Kind==MonsterIntentKind.Shield?old.Intents[i] with{Value=change.ShieldIntentValue}:old.Intents[i],next.Intents[i]);
            }
        }
    }

    [Fact]
    public void ExplicitZeroShieldIsAValueRatherThanAMissingOverride()
    {
        var table=Table();var rows=table.Rows.ToArray();var row=rows[0].ToArray();
        row[Array.IndexOf(Names,"base_shield")]=new(ConfigValueType.WholeNumber,0L);row[Array.IndexOf(Names,"shield_intent_value")]=new(ConfigValueType.WholeNumber,0L);rows[0]=row;
        var config=GameConfigCatalog.Load(ConfigCompiler.Compile("monster-explicit-zero",Tables(table with{Rows=rows}),out _));var tuning=config.SeasonMonsterTuning!;
        var monster=Assert.Single(PveBattleFactory.Create(new(new(1,1),ChaosMapLayer.Middle,false,false,false,"E1"),config.SeasonDifficulty(0),tuning:tuning).Monsters);
        Assert.Equal(0,monster.Shield);Assert.Equal(0,Assert.Single(monster.Intents,i=>i.Kind==MonsterIntentKind.Shield).Value);
    }

    [Theory]
    [InlineData("missing")][InlineData("duplicate")][InlineData("species")][InlineData("member")][InlineData("hp")][InlineData("shield")][InlineData("loop")][InlineData("rule")][InlineData("baseline")][InlineData("id")]
    public void RuntimeRejectsIncompleteOrInvalidCoverageInsteadOfUsingLegacyValues(string change)
    {
        var rows=Control().SeasonMonsterTuning!.Rows.ToList();var first=rows[0];
        if(change=="missing")rows.RemoveAt(0);
        else rows[0]=change switch{"duplicate"=>rows[1],"species"=>first with{MonsterId="fire-herald"},"member"=>first with{MemberOrder=2},"hp"=>first with{BaseHp=0},"shield"=>first with{BaseShield=-1},"loop"=>first with{ShieldIntentValue=10000},"rule"=>first with{RuleId="unknown"},"baseline"=>first with{BaselineId="current"},_=>first with{Id="wrong"}};
        Assert.Throws<InvalidDataException>(()=>new SeasonMonsterTuningConfig(rows));
    }

    [Theory]
    [InlineData("scope")][InlineData("required")][InlineData("type")][InlineData("blank-zero")]
    public void CompilerOrLoaderRejectsInvalidMetadataAndMissingExplicitZero(string change)
    {
        var table=Table();var index=Array.IndexOf(Names,"base_shield");
        if(change=="blank-zero")
        {
            var rows=table.Rows.ToArray();var row=rows[0].ToArray();row[index]=new(ConfigValueType.WholeNumber,null);rows[0]=row;table=table with{Rows=rows};
        }
        else
        {
            var columns=table.Columns.ToArray();columns[index]=change switch{"scope"=>columns[index] with{Scope=PublishScope.Both},"required"=>columns[index] with{Required=false},_=>columns[index] with{Type=ConfigValueType.Text}};table=table with{Columns=columns};
        }
        Assert.Throws<InvalidDataException>(()=>GameConfigCatalog.Load(ConfigCompiler.Compile("invalid-monster-tuning",Tables(table),out _)));
    }

    [Fact]
    public void FreshInitializationAndRecoveredMoveUseTheirOriginalCatalogAndUnscopedRoomsKeepTheLegacyBase()
    {
        var old=Archived();var next=Control();Assert.NotEqual(old.Version,next.Version);
        foreach(var config in new[]{old,next})
        {
            var (room,id,target)=Room(config,true);var expected=config.SeasonMonsterTuning is null?1472:1344;
            Assert.Equal(expected,Assert.Single(room.GetPlayer(id).Pve!.Monsters).MaximumHp);
            var snapshot=room.Capture();snapshot=snapshot with{Players=snapshot.Players.Select(p=>p with{Phase=RoomPlayerPhase.ActionBar,Pve=null,ClearedCells=[p.Position!.Value]}).ToArray()};
            var restored=BattleRoom.Restore(snapshot,CombatCardCatalog.Create(config),73);restored.MovePlayerAndPair(id,target,restored.Revision,DateTimeOffset.UnixEpoch);
            Assert.Equal(expected,Assert.Single(restored.GetPlayer(id).Pve!.Monsters).MaximumHp);Assert.Equal(config.Version,restored.ConfigVersion);
        }
        var (legacy,player,_)=Room(next,false);Assert.Equal(184,Assert.Single(legacy.GetPlayer(player).Pve!.Monsters).MaximumHp);
    }

    private static (BattleRoom Room,Guid Id,MapPosition Target) Room(GameConfigCatalog config,bool seasonal)
    {
        var map=ChaosMapGenerator.Generate(73,1,config.SeasonThemes).Capture();var state=ChaosMapState.Restore(map);var start=map.Cells.First(c=>c.MonsterGroupId.StartsWith('E')).Position;
        var target=state.GetNeighbors(start).First(p=>state.CanMove(start,p)&&state.GetCell(p).Layer==ChaosMapLayer.Middle);
        map=map with{SpawnPositions=[start],Cells=map.Cells.Select(c=>c.Position==start||c.Position==target?c with{MonsterGroupId="E4"}:c).ToArray()};
        var room=new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),73,season:seasonal?new("monster-state-contract",5,"season-v1",config.Version,"season-equipment-v1"):null);
        var id=Guid.NewGuid();var cards=Enumerable.Range(1,13).Select(n=>$"C{n:D2}").Concat(Enumerable.Range(1,7).Select(n=>$"MAG-{n:D2}")).ToArray();room.AddPlayer(new(id,HeroClass.Mage,cards,null));room.InitializeMap(ChaosMapState.Restore(map));return(room,id,target);
    }
    private static GameConfigCatalog Archived()
    {
        using var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("ArchivedMonsterConfig14")!;using var bytes=new MemoryStream();stream.CopyTo(bytes);return GameConfigCatalog.Load(bytes.ToArray());
    }
    private static GameConfigCatalog Control()=>GameConfigCatalog.Load(ConfigCompiler.Compile("monster-tuning-control",Tables(Table()),out _));
    private static ConfigTable[] Tables(ConfigTable table)=>XlsxConfigReader.Read(Path.Combine(PublishedConfigTestInputs.FindRoot(),"config/FantasyCard_Config.xlsx")).Where(t=>t.Name!="SeasonMonsterTuning").Append(table).ToArray();
    private static ConfigTable Table()
    {
        var columns=Names.Select(n=>new ConfigColumn(n,n is "member_order" or "base_hp" or "base_shield" or "shield_intent_value"?ConfigValueType.WholeNumber:ConfigValueType.Text,true,PublishScope.Server,"Monster tuning contract input")).ToArray();
        object?[][] rows=[["E1:1",SeasonMonsterTuningConfig.Version,SeasonMonsterTuningConfig.Baseline,"E1",1L,"metal-guard",180L,8L,2L],
            ["E3:1",SeasonMonsterTuningConfig.Version,SeasonMonsterTuningConfig.Baseline,"E3",1L,"marsh-mother",172L,4L,2L],
            ["E4:1",SeasonMonsterTuningConfig.Version,SeasonMonsterTuningConfig.Baseline,"E4",1L,"stone-guard",168L,12L,2L],
            ["E6:1",SeasonMonsterTuningConfig.Version,SeasonMonsterTuningConfig.Baseline,"E6",1L,"metal-guard",160L,10L,2L]];
        return new("SeasonMonsterTuning",columns,rows.Select(r=>(IReadOnlyList<ConfigValue>)r.Select((v,i)=>new ConfigValue(columns[i].Type,v)).ToArray()).ToArray());
    }
}
