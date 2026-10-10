using System.IO.Compression;
using System.Text;
using System.Text.Json;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class MonsterPoolBaselineWireTests
{
    private static readonly int[] Seeds = [450001, 451001, 452001];
    [Theory]
    [InlineData(HeroClass.Mage, false)]
    [InlineData(HeroClass.Priest, false)]
    [InlineData(HeroClass.Guardian, false)]
    [InlineData(HeroClass.Mage, true)]
    [InlineData(HeroClass.Priest, true)]
    [InlineData(HeroClass.Guardian, true)]
    public void Actual_kill_projection_keeps_default_automatic_policy_and_optional_candidates_distinct(HeroClass hero, bool optional)
    {
        var config = GameConfigCatalog.Current; var catalog = CombatCardCatalog.CreatePrototype();
        Assert.False(config.Numerics.OptionalMonsterPool);
        var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", _ => "GUA" };
        var cards = Enumerable.Range(1, 13).Select(i => $"C{i:D2}").Concat(Enumerable.Range(1, 7).Select(i => $"{prefix}-{i:D2}")).ToArray();
        var owned = config.Cards.Where(c => c.Enabled && c.IsCodex && c.MonsterType is null).ToDictionary(c => c.CardId, c => new OwnedCard(c.CardId, c.HeroClass, (CardRarity)c.Rarity, 1, false));
        DeckRules.Validate(hero, cards, owned);
        var directory = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_POOL_WIRE_EVIDENCE");
        if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);
        using var raw = string.IsNullOrWhiteSpace(directory) ? null : new GZipStream(new FileStream(Path.Combine(directory, $"{hero}-{optional}.jsonl.gz"), FileMode.CreateNew), CompressionLevel.Fastest);
        foreach (var seed in Seeds)
        {
            var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, seed, config.Numerics with { OptionalMonsterPool = optional });
            var playerId = Guid.NewGuid(); var player = room.AddPlayer(new(playerId, hero, cards, null));
            var map = ChaosMapGenerator.Generate(seed, 1).Capture(); var cell = map.Cells.First(c => c.Layer == ChaosMapLayer.Outer);
            room.InitializeMap(ChaosMapState.Restore(map with { Cells = map.Cells.Select(c => c.Position == cell.Position ? c with { MonsterGroupId = "O1", HasSpring = false } : c).ToArray(), SpawnPositions = [cell.Position] }));
            var pve = player.Pve!; var target = Assert.Single(pve.Monsters); target.TakeDamage(target.Hp + target.Shield - 1);
            CombatCardInstance? selected = null;
            for (var tick = 0; tick < 300 && selected is null; tick++)
            {
                selected = player.Combat.Deck.Hand.FirstOrDefault(c => CombatResolver.Resolve([catalog.Get(c.CardId, c.Level, c.ElementOverride)], player.Combat, target.ElementalResistance).Damage > 0);
                if (selected is null) room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch.AddMilliseconds((tick + 1) * 100));
            }
            Assert.NotNull(selected);
            var result = room.PlayCards(playerId, pve.BattleId, target.MonsterId, [selected.InstanceId], room.Revision, DateTimeOffset.UnixEpoch);
            Assert.True(result.TargetDefeated);
            var payload = RoomSnapshotProjection.Build(new GetRoomClientStateCommand(playerId).Execute(room), playerId, null, DateTimeOffset.UnixEpoch);
            if (optional) { Assert.NotNull(payload.Player.MonsterPool); Assert.Single(payload.Player.MonsterPool.Pending); Assert.Contains("monster.choose", payload.AllowedActions); }
            else { Assert.Null(payload.Player.MonsterPool); Assert.DoesNotContain("monster.choose", payload.AllowedActions); }
            var message = new ServerEvent("room.snapshot", "pool-baseline", payload, "pool-event", 1, DateTimeOffset.UnixEpoch);
            var wire = RealtimeProtobufCodec.EncodeServer(message); var decoded = RealtimeProtobufCodec.DecodeServer(wire);
            Assert.Equivalent(message, decoded, strict: true); Assert.True(wire.Length <= 16 * 1024);
            var row = new { case_id = optional ? "PR13-B09.1-T02" : "PR13-B09.1-T01", source_sha = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_SOURCE_SHA"),
                seed, hero = hero.ToString(), optional, legal_deck = cards, actual_actor = playerId, actual_battle = pve.BattleId, actual_killed_monster = target.MonsterId,
                actual_resolution = result, after_state = room.Capture(), original_projection = payload, response_wire = Convert.ToBase64String(wire), wire_bytes = wire.Length,
                expected_total_pool = optional ? 20 : 21, controlled_finishing_HP_boundary = true, no_LIVE_claim = true };
            raw?.Write(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(row) + "\n"));
        }
    }
}
