using System.Reflection;
using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

public sealed class SeasonD0PublishedCalibrationTests
{
    [Fact]
    public void Published16ChangesOnlyD0HpAndShieldWhileArchive15KeepsItsOriginalCurve()
    {
        using var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("ArchivedD0Config15");Assert.NotNull(stream);using var memory=new MemoryStream();stream.CopyTo(memory);
        var old=GameConfigCatalog.Load(memory.ToArray());
        // This regression compares the immutable v15-to-v16 calibration, including its original hash.
        var current=GameConfigCatalog.Load(File.ReadAllBytes(Path.Combine(PublishedConfigTestInputs.FindRoot(),"server/config/archive/season-v1-config-16/fantasycard.config.bytes")));
        Assert.Equal("season-v1-config-15",old.Version);Assert.Equal("season-v1-config-16",current.Version);
        Assert.Equal("2bc11db4b287055d119aceda45deeeb6fb00c3df524b3acad9887deaa04d9d8a",old.ContentHash);Assert.Equal("48e25ff33fed65928f059a6907dfacaa5b88f7c7e91d5fb558c3a1dbac0e0e8b",current.ContentHash);
        Assert.Equal(10000,old.SeasonDifficulty(0).HpBasisPoints);Assert.Equal(old.SeasonDifficulty(0) with {HpBasisPoints=5000,ShieldBasisPoints=5000},current.SeasonDifficulty(0));
        for(var d=1;d<6;d++)Assert.Equal(old.SeasonDifficulty(d),current.SeasonDifficulty(d));
        Assert.Equal(JsonSerializer.Serialize(old.Cards),JsonSerializer.Serialize(current.Cards));Assert.Equal(JsonSerializer.Serialize(old.CardLevels),JsonSerializer.Serialize(current.CardLevels));Assert.Equal(old.Numerics,current.Numerics);
        var seed=1400001;var map=ChaosMapGenerator.Generate(seed,1,current.SeasonThemes).Capture();var boss=map.Cells.Single(x=>x.IsBoss);map=map with {SpawnPositions=[boss.Position]};
        BattleRoom Create(GameConfigCatalog config,bool seasonal)
        {
            var room=new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),seed,season:seasonal?new SeasonContext("d0-calibration",0,"season-v1",config.Version,"season-equipment-v1"):null);
            room.AddPlayer(new(Guid.NewGuid(),HeroClass.Mage,SeasonStarterSupportTests.Deck("support-guard"),null));room.InitializeMap(ChaosMapState.Restore(map));return room;
        }
        var oldRoom=Create(old,true);var newRoom=Create(current,true);var unscoped=Create(current,false);
        Assert.Equal(280,oldRoom.Capture().Players[0].Pve!.Monsters[0].MaximumHp);Assert.Equal(140,newRoom.Capture().Players[0].Pve!.Monsters[0].MaximumHp);Assert.Equal(280,unscoped.Capture().Players[0].Pve!.Monsters[0].MaximumHp);
        var saved=oldRoom.Capture();var restored=BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(JsonSerializer.Serialize(saved))!,CombatCardCatalog.Create(old),seed);Assert.Equivalent(saved,restored.Capture(),strict:true);
    }
}
