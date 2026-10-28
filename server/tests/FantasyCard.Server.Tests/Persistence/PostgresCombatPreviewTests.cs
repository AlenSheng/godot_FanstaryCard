using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresCombatPreviewTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();
    private static readonly DateTimeOffset Now = DateTimeOffset.UnixEpoch.AddSeconds(10);

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData(HeroClass.Mage, false)]
    [InlineData(HeroClass.Priest, false)]
    [InlineData(HeroClass.Guardian, false)]
    [InlineData(HeroClass.Guardian, true)]
    [Trait("Category", "PostgresIntegration")]
    public async Task Repeated_preview_of_restored_checkpoint_is_pure_and_matches_commit(HeroClass hero, bool fractional)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics();
        var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var player = await PlayerAsync(db);
        var room = CreateRoom(player.UserId, hero, fractional, "C01", "common-17", "common-15", "common-19", "common-22");
        await PersistAsync(db, repository, room);
        var persistedBefore = await RawAsync(db, room.RoomId);
        room = BattleRoom.Restore((await repository.GetAsync(room.RoomId, TestContext.Current.CancellationToken))!, Catalog, 77);
        var before = room.Capture();
        var actor = room.GetPlayer(player.UserId);
        var selected = actor.Combat.Deck.Hand.Select(card => card.InstanceId).ToArray();
        CombatResolution? preview = null;
        for (var i = 0; i < 10; i++)
        {
            var current = room.PreviewCards(player.UserId, actor.Pve!.BattleId, "preview-monster", selected, room.Revision, Now);
            if (preview is not null) Assert.Equivalent(preview, current, strict: true);
            preview = current;
            Assert.Equivalent(before, room.Capture(), strict: true);
            Assert.Empty(room.DrainCombatFeedback());
            await repository.SaveIfDueAsync(room.Capture(), TestContext.Current.CancellationToken);
            Assert.Equal(persistedBefore, await RawAsync(db, room.RoomId));
        }
        var afterPreview = room.Capture();
        var persistedAfterPreview = await RawAsync(db, room.RoomId);
        var actual = room.PlayCards(player.UserId, actor.Pve!.BattleId, "preview-monster", selected, room.Revision, Now);
        Assert.Equivalent(preview! with { RoomRevision = actual.RoomRevision }, actual, strict: true);
        await new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics).SaveIfDueAsync(room.Capture(), TestContext.Current.CancellationToken);
        Assert.Equivalent(room.Capture(), await repository.GetAsync(room.RoomId, TestContext.Current.CancellationToken), strict: true);
        Record("PR13-B02.3-T01", hero + (fractional ? "-fractional" : "-default"), new
        {
            repeatedPreviews = 10, stateBeforeHash = Hash(before), stateAfterPreviewHash = Hash(afterPreview),
            databaseBeforeHash = Hash(persistedBefore), databaseAfterPreviewHash = Hash(persistedAfterPreview),
            randomBeforeHash = Hash(before.RandomStreams), randomAfterHash = Hash(afterPreview.RandomStreams),
            deckBeforeHash = Hash(before.Players[0].Combat.Deck), deckAfterHash = Hash(afterPreview.Players[0].Combat.Deck),
            guardianRemainderBefore = before.Players[0].Combat.GuardianShieldRemainderTenths,
            guardianRemainderAfterPreview = afterPreview.Players[0].Combat.GuardianShieldRemainderTenths,
            guardianRemainderAfterCommit = room.Capture().Players[0].Combat.GuardianShieldRemainderTenths,
            preview, actual, stateAfterCommitHash = Hash(room.Capture()), restoredAfterCommit = true
        });
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Protocol_roundtrip_preserves_order_and_authoritative_core_after_database_restore()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics();
        var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var player = await PlayerAsync(db);
        var room = CreateRoom(player.UserId, HeroClass.Mage, false, "C09", "C06");
        await PersistAsync(db, repository, room);
        room = BattleRoom.Restore((await repository.GetAsync(room.RoomId, TestContext.Current.CancellationToken))!, Catalog, 77);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, Guid.NewGuid(), startTicker: false);
        var clock = new PreviewClock();
        var router = new RealtimeCommandRouter(new RealtimeEventStore(clock), clock, registry);
        var hand = room.GetPlayer(player.UserId).Combat.Deck.Hand.Select(card => card.InstanceId).ToArray();
        var rows = new List<object>();
        foreach (var order in new[] { hand, hand.Reverse().ToArray() })
        {
            var command = new ClientCommand("combat.preview", Guid.NewGuid().ToString("N"), room.Revision,
                new BattlePlayCardsCommandPayload(room.GetPlayer(player.UserId).Pve!.BattleId, "preview-monster", order));
            var wire = RealtimeProtobufCodec.EncodeClient(command);
            var decoded = RealtimeProtobufCodec.DecodeClient(wire);
            Assert.Equal(order, Assert.IsType<BattlePlayCardsCommandPayload>(decoded.Payload).CardInstanceIds);
            var response = Assert.Single(await router.RouteAsync(player, decoded, "order", TestContext.Current.CancellationToken));
            Assert.Equal("combat.previewed", response.Type);
            var roundtrip = RealtimeProtobufCodec.DecodeServer(RealtimeProtobufCodec.EncodeServer(response));
            Assert.Equivalent(response, roundtrip, strict: true);
            var resolution = Assert.IsType<BattleComboResolvedEventPayload>(roundtrip.Payload);
            Assert.Equal(order, resolution.CardInstanceIds);
            Assert.Equal(order[0] == hand[0] ? "Earth" : "Water", resolution.CoreElement);
            var control = BattleRoom.Restore((await repository.GetAsync(room.RoomId, TestContext.Current.CancellationToken))!, Catalog, 77);
            var committed = control.PlayCards(player.UserId, control.GetPlayer(player.UserId).Pve!.BattleId,
                "preview-monster", order, control.Revision, Now);
            Assert.Equal(committed.CoreElement!.ToString(), resolution.CoreElement);
            Assert.Equal((committed.Damage, committed.Heal, committed.ShieldGain, committed.StunSeconds),
                (resolution.Damage, resolution.Heal, resolution.ShieldGain, double.Parse(resolution.StunSeconds!, System.Globalization.CultureInfo.InvariantCulture)));
            rows.Add(new { order, resolution.CoreElement, commandWire = Convert.ToBase64String(wire),
                responseWire = Convert.ToBase64String(RealtimeProtobufCodec.EncodeServer(response)), committed });
        }
        Assert.Equivalent(room.Capture(), await repository.GetAsync(room.RoomId, TestContext.Current.CancellationToken), strict: true);
        Record("PR13-B02.3-T02", "ordered-protobuf", new { rows, databaseUnchanged = true });
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Stale_preview_after_committed_checkpoint_is_rejected_without_overwriting_current_state()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics();
        var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var player = await PlayerAsync(db);
        var room = CreateRoom(player.UserId, HeroClass.Guardian, false, "C09", "C06", "common-15");
        await PersistAsync(db, repository, room);
        var oldRevision = room.Revision;
        var hand = room.GetPlayer(player.UserId).Combat.Deck.Hand;
        room.PlayCards(player.UserId, room.GetPlayer(player.UserId).Pve!.BattleId, "preview-monster", [hand[0].InstanceId], room.Revision, Now);
        await new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics).SaveIfDueAsync(room.Capture(), TestContext.Current.CancellationToken);
        var durable = await RawAsync(db, room.RoomId);
        room = BattleRoom.Restore((await repository.GetAsync(room.RoomId, TestContext.Current.CancellationToken))!, Catalog, 77);
        var before = room.Capture();
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, Guid.NewGuid(), startTicker: false);
        var router = new RealtimeCommandRouter(new RealtimeEventStore(TimeProvider.System), TimeProvider.System, registry);
        var command = new ClientCommand("combat.preview", "stale-preview", oldRevision,
            new BattlePlayCardsCommandPayload(room.GetPlayer(player.UserId).Pve!.BattleId, "preview-monster",
                [room.GetPlayer(player.UserId).Combat.Deck.Hand[0].InstanceId]));
        var rejected = Assert.Single(await router.RouteAsync(player,
            RealtimeProtobufCodec.DecodeClient(RealtimeProtobufCodec.EncodeClient(command)), "stale", TestContext.Current.CancellationToken));
        Assert.Equal("error.command_rejected", rejected.Type);
        Assert.Equivalent(before, room.Capture(), strict: true);
        await repository.SaveIfDueAsync(room.Capture(), TestContext.Current.CancellationToken);
        Assert.Equal(durable, await RawAsync(db, room.RoomId));
        Record("PR13-B02.3-T03", "stale-revision", new { oldRevision, currentRevision = room.Revision,
            rejected.Type, beforeHash = Hash(before), afterHash = Hash(room.Capture()),
            durableBeforeHash = Hash(durable), durableAfterHash = Hash(await RawAsync(db, room.RoomId)) });
    }

    private static BattleRoom CreateRoom(Guid playerId, HeroClass hero, bool fractional, params string[] cards)
    {
        var monster = new MonsterCombatState("preview-monster", 500, 500, 7, TimeSpan.FromSeconds(4),
            [new(MonsterIntentKind.Attack, 3, CardElement.Wood)]);
        var room = new BattleRoom(Guid.NewGuid(), "preview-pg", Catalog, 77, new NumericalRules(FractionalGuardian: fractional));
        room.AddPlayer(new(playerId, hero, Enumerable.Repeat("common-01", 20).ToArray(),
            new(Guid.NewGuid(), null, [monster])));
        var player = room.GetPlayer(playerId);
        player.Combat.TakeDamage(30);
        if (fractional) player.Combat.Restore(player.Combat.Capture() with { GuardianShieldRemainderTenths = 9 });
        player.Combat.Deck.Restore(new(cards.Select(id => new CombatCardInstance(Guid.NewGuid(), id, 0)).ToArray(),
            Enumerable.Range(0, 20).Select(_ => new CombatCardInstance(Guid.NewGuid(), "common-01")).ToArray(), [], 0));
        return room;
    }

    private static async Task<PlayerProfile> PlayerAsync(PostgresTestSchema db)
    {
        var now = DateTimeOffset.UtcNow;
        return await new IdentityRepository(db.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString("N"), "Preview " + Guid.NewGuid().ToString("N")[..8], RandomNumberGenerator.GetBytes(32),
            now, now.AddHours(1), TestContext.Current.CancellationToken);
    }

    private static async Task PersistAsync(PostgresTestSchema db, RoomSnapshotRepository repository, BattleRoom room)
    {
        await using var command = db.DataSource.CreateCommand(
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',77,'preview-pg','Running',now())");
        command.Parameters.AddWithValue(Guid.NewGuid());
        command.Parameters.AddWithValue(room.RoomId);
        await command.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
        await repository.SaveIfDueAsync(room.Capture(), TestContext.Current.CancellationToken);
    }

    private static Task<string> RawAsync(PostgresTestSchema db, Guid room) => db.ScalarAsync<string>(
        "SELECT snapshot_json::text || rng_state_json::text FROM room_snapshots WHERE room_id=$1", room);
    private static string Hash(object? value) => Convert.ToHexStringLower(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(value)));
    private static void Record(string caseId, string variant, object actual)
    {
        var directory = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_PREVIEW_EVIDENCE");
        if (string.IsNullOrWhiteSpace(directory)) return;
        Directory.CreateDirectory(directory);
        File.WriteAllText(Path.Combine(directory, caseId + "-" + variant + ".json"),
            JsonSerializer.Serialize(new { caseId, variant, status = "Passed", actual }) + Environment.NewLine);
    }

    private sealed class PreviewClock : TimeProvider
    {
        // Realtime wire timestamps have millisecond precision. Keep the frozen
        // fixture clock representable on both sides of the protocol contract.
        public override DateTimeOffset GetUtcNow() => Now;
    }
}
