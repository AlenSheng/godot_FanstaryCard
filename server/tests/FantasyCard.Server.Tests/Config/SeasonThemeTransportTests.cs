using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Config;

public sealed class SeasonThemeTransportTests
{
    [Fact]
    public async Task RealRegenerationIntentPublishesBoundedHpRatherThanRawBasisPointsAndKeepsExistingWireTags()
    {
        var config=SeasonThemeConfigIntegrationTests.Variant("Wood");var catalog=CombatCardCatalog.Create(config);var id=Guid.NewGuid();
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,73,season:new("theme-wire",0,"season-v1",config.Version,"season-equipment-v1"));
        room.AddPlayer(new(id,HeroClass.Mage,Enumerable.Range(1,13).Select(n=>$"C{n:D2}").Concat(Enumerable.Range(1,7).Select(n=>$"MAG-{n:D2}")).ToArray(),null));
        room.InitializeMap(ChaosMapGenerator.Generate(73,1,config.SeasonThemes));var snapshot=room.Capture();var cell=snapshot.Map!.Cells.Single(c=>c.IsBoss);
        snapshot=snapshot with {Players=[snapshot.Players[0] with {Position=cell.Position,Phase=RoomPlayerPhase.Pve,
            Pve=PveBattleFactory.Create(cell,config.SeasonDifficulty(0),config.SeasonThemes!.Selected).Capture()}]};
        room=BattleRoom.Restore(snapshot,catalog,73);var boss=Assert.Single(room.GetPlayer(id).Pve!.Monsters);Assert.Equal(140,boss.MaximumHp);boss.TakeDamage(boss.Shield+boss.MaximumHp/3);
        for(var tick=0;tick<1000&&!(boss.IntentIndex==2&&boss.WindupRemaining>TimeSpan.Zero);tick++)
        {
            var intent=boss.Advance(TimeSpan.FromMilliseconds(100));if(intent is not null)boss.ResolveIntentDamage(intent);
        }
        var payload=RoomSnapshotProjection.Build(new GetRoomClientStateCommand(id).Execute(room),id,Guid.NewGuid(),DateTimeOffset.UnixEpoch);
        var published=Assert.Single(payload.Pve!.Monsters);Assert.Equal("Regenerate",published.IntentKind);Assert.Equal(2,published.IntentValue);
        var bytes=RealtimeProtobufCodec.EncodeServer(new("room.snapshot","theme-wire",payload,Guid.NewGuid().ToString("D"),1,DateTimeOffset.UnixEpoch));
        var decoded=Assert.IsType<RoomSnapshotEventPayload>(RealtimeProtobufCodec.DecodeServer(bytes).Payload);
        Assert.Equal("Regenerate",Assert.Single(decoded.Pve!.Monsters).IntentKind);Assert.Equal(2,decoded.Pve.Monsters[0].IntentValue);
        var directory=Environment.GetEnvironmentVariable("FANTASYCARD_THEME_INTEROP_DIR");
        if(!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);await File.WriteAllBytesAsync(Path.Combine(directory,"regeneration.bin"),bytes,TestContext.Current.CancellationToken);
            var encoded=System.Text.Json.JsonSerializer.Serialize(new {version=config.Version,tables=config.SeasonThemes!.Themes.Select(t=>new {t.ThemeId,t.StrategyId})});
            await File.WriteAllTextAsync(Path.Combine(directory,"control-description.json"),encoded,TestContext.Current.CancellationToken);
        }
    }
}
