using System.Text.Json;
using System.Globalization;
using FantasyCard.Contracts.Realtime;
using FantasyCard.ConfigExporter;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using Wire = FantasyCard.Contracts.Wire.Realtime.V1;

namespace FantasyCard.Server.Tests.Config;

public sealed class SeasonSustainPublishedConfigTests
{
    [Theory]
    [InlineData(0.0)]
    [InlineData(0.75)]
    [InlineData(1.0)]
    [InlineData(2.0)]
    public void ActualRoomProjectionAndBothCodecsPreserveZeroFractionAndFullCredit(double credit)
    {
        VerifyWire(GameConfigCatalog.Current, credit);
    }

    [Fact]
    public void Original16WireDoesNotInventCreditOrReturnRate() => VerifyWire(Original(), null);

    private static void VerifyWire(GameConfigCatalog config, double? credit)
    {
        var context = new SeasonContext("wire-policy", 5, "season-v1", config.Version, "season-equipment-v1");
        var catalog = CombatCardCatalog.Create(config); var player = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, 73, season: context);
        room.AddPlayer(new(player, HeroClass.Mage, SeasonClassEfficiencyPilotTests.Deck(HeroClass.Mage, "flow-loop"), null, WeaponLevel: 5));
        room.InitializeMap(ChaosMapGenerator.Generate(73, 1));
        var state = room.Capture(); var self = Assert.Single(state.Players);
        room = BattleRoom.Restore(state with { Players = [self with { Combat = self.Combat with { FenxianReturnCredit = credit } }] }, catalog, 73);
        var before = JsonSerializer.Serialize(room.Capture());
        var payload = RoomSnapshotProjection.Build(new GetRoomClientStateCommand(player).Execute(room), player, null, DateTimeOffset.UnixEpoch);
        var expected = credit?.ToString("R", CultureInfo.InvariantCulture);
        Assert.Equal(expected, payload.Player.NumericalState!.FenxianReturnCredit);
        Assert.Equal(config.SeasonDifficulty(5).MageReturnRateBasisPoints, payload.Player.NumericalState.FenxianReturnRateBasisPoints);
        var envelope = new ServerEvent("room.snapshot", "sustain-wire", payload, "sustain-wire", 1, DateTimeOffset.UnixEpoch);
        var bytes = RealtimeProtobufCodec.EncodeServer(envelope);
        var official = Wire.RoomSnapshotEvent.Parser.ParseFrom(Wire.ServerEnvelope.Parser.ParseFrom(bytes).Payload).Player.NumericalState;
        Assert.Equal(credit is not null, official.HasFenxianReturnCredit);
        Assert.Equal(credit is not null, official.HasFenxianReturnRateBasisPoints);
        if (credit is not null) { Assert.Equal(expected, official.FenxianReturnCredit); Assert.Equal(500, official.FenxianReturnRateBasisPoints); }
        var decoded = Assert.IsType<RoomSnapshotEventPayload>(RealtimeProtobufCodec.DecodeServer(bytes).Payload);
        Assert.Equal(payload.Player.NumericalState, decoded.Player.NumericalState);
        Assert.Equal(before, JsonSerializer.Serialize(room.Capture()));
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_SUSTAIN_WIRE_OUTPUT");
        if (!string.IsNullOrEmpty(output))
        {
            Directory.CreateDirectory(output);
            var name = credit is null ? "original16" : "credit-" + credit.Value.ToString("R", CultureInfo.InvariantCulture);
            var path = Path.Combine(output, name + ".original.json"); Assert.False(File.Exists(path));
            File.WriteAllText(path, JsonSerializer.Serialize(new { config.Version, expected_credit = expected, expected_rate = config.SeasonDifficulty(5).MageReturnRateBasisPoints, wire = Convert.ToBase64String(bytes) }));
        }
    }

    private static string Root()
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
            if (File.Exists(Path.Combine(directory.FullName, "server/config/archive/season-v1-config-16/fantasycard.config.bytes"))) return directory.FullName;
        throw new FileNotFoundException("Original16 archive is required.");
    }

    private static GameConfigCatalog Original() => GameConfigCatalog.Load(File.ReadAllBytes(Path.Combine(Root(), "server/config/archive/season-v1-config-16/fantasycard.config.bytes")));

    [Fact]
    public void Formal17MatchesTheValidatedCardAndRateWhileOriginal16RetainsItsExactPolicy()
    {
        var formal = GameConfigCatalog.Current; var original = Original(); var probe = SeasonMageCardCandidate.Current;
        Assert.Equal("season-v1-config-17", formal.Version); Assert.Equal("season-v1-config-16", original.Version);
        Assert.Equal(probe.Cards, formal.Cards); Assert.Equal(original.CardLevels, formal.CardLevels);
        Assert.Equal(original.EquipmentQualities, formal.EquipmentQualities); Assert.Equal(original.LootLayers, formal.LootLayers);
        Assert.Equal(1, original.Cards.Single(x => x.CardId == "MAG-10").Effect.ImmediateDraw);
        Assert.Equal(0, formal.Cards.Single(x => x.CardId == "MAG-10").Effect.ImmediateDraw);
        Assert.False(formal.Numerics.SeasonMageRhythm); // Legacy mode is not silently turned into a season.
        for (var d = 0; d < 6; d++)
        {
            Assert.Equal(original.SeasonDifficulty(d) with { MageReturnRateBasisPoints = 500 }, formal.SeasonDifficulty(d));
            Assert.False(NumericalRules.ForSeason(original, d).SeasonMageSustainBudget);
            Assert.Null(NumericalRules.ForSeason(original, d).SeasonMageReturnRateBasisPoints);
            var policy = NumericalRules.ForSeason(formal, d);
            Assert.True(policy.SeasonMageSustainBudget); Assert.Equal(500, policy.SeasonMageReturnRateBasisPoints);
        }
        Assert.False(NumericalRules.SeasonV1.SeasonMageSustainBudget);
    }

    [Fact]
    public void NewRoomsFreezePublishedParametersAndOldRoomJsonCannotUseTheCurrentCatalog()
    {
        var original = Original();
        foreach (var config in new[] { original, GameConfigCatalog.Current })
        {
            var catalog = CombatCardCatalog.Create(config); var context = new SeasonContext("published-policy", 5, "season-v1", config.Version, "season-equipment-v1");
            var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, 73, season: context);
            room.AddPlayer(new(Guid.NewGuid(), HeroClass.Mage, SeasonClassEfficiencyPilotTests.Deck(HeroClass.Mage, "flow-loop"), null, WeaponLevel: 5));
            var snapshot = room.Capture(); var player = Assert.Single(snapshot.Players);
            Assert.Equal(config.Version == "season-v1-config-17" ? FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm : FenxianImmediateDrawPolicy.SeasonBoundedRhythm, player.Combat.FenxianPolicy);
            Assert.Equal(config.SeasonDifficulty(5).MageReturnRateBasisPoints, player.Combat.FenxianReturnRateBasisPoints);
            var raw = JsonSerializer.Serialize(snapshot);
            Assert.Equal(raw, JsonSerializer.Serialize(BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(raw)!, catalog, 73).Capture()));
            if (config == original)
                Assert.Throws<DomainValidationException>(() => BattleRoom.Restore(snapshot, CombatCardCatalog.Create(GameConfigCatalog.Current), 73));
        }
    }

    [Theory]
    [InlineData(0L)]
    [InlineData(1001L)]
    public void CompilerRejectsOutOfRangeExplicitReturnRates(long invalid)
    {
        var tables = XlsxConfigReader.Read(Path.Combine(Root(), "config/FantasyCard_Config.xlsx"));
        var table = tables.Single(x => x.Name == "SeasonDifficulty"); var column = table.Columns.Select((c, i) => (c, i)).Single(x => x.c.Name == "mage_return_rate_bp");
        var rows = table.Rows.ToArray(); var row = rows[0].ToArray(); row[column.i] = new(column.c.Type, invalid); rows[0] = row;
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Compile("invalid-return-rate", tables.Select(x => x == table ? x with { Rows = rows } : x).ToArray(), out _));
    }

    [Fact]
    public void ExistingColumnWithMissingDataCannotBecomeAnImplicitZeroOrOldPolicy()
    {
        var tables = XlsxConfigReader.Read(Path.Combine(Root(), "config/FantasyCard_Config.xlsx"));
        var table = tables.Single(x => x.Name == "SeasonDifficulty"); var column = table.Columns.Select((c, i) => (c, i)).Single(x => x.c.Name == "mage_return_rate_bp");
        var rows = table.Rows.ToArray(); var row = rows[0].ToArray(); row[column.i] = new(column.c.Type, null); rows[0] = row;
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Compile("missing-return-rate", tables.Select(x => x == table ? x with { Rows = rows } : x).ToArray(), out _));
        var columns = table.Columns.ToArray(); columns[column.i] = column.c with { Scope = PublishScope.Server };
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Compile("hidden-return-rate", tables.Select(x => x == table ? x with { Columns = columns } : x).ToArray(), out _));
    }
}
