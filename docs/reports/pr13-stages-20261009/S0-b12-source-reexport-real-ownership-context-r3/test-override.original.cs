using System.Diagnostics;
using System.Security;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresNumericalContractTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;
    private static readonly CombatCardCatalog Prototype = CombatCardCatalog.CreatePrototype();
    private static readonly DateTimeOffset Now = DateTimeOffset.UnixEpoch.AddSeconds(10);
    private static readonly string[] CompilerDiagnostics = ["CS1739", "CS1061"];
    private static readonly int[] DefaultMageDraws = [0, 0, 1, 1, 2];
    private static readonly int[] DefaultGuardianShields = [2, 2, 2, 2, 2];
    private static readonly string[] LegacyMissingFields = ["numerics", "fenxianPolicy", "guardianPolicy", "guardianShieldRemainderTenths"];
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Persisted_current_contract_does_not_revive_obsolete_boolean_or_remainder_API()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics();
        var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var room = Room(HeroClass.Mage);
        await Persist(db, repository, room);
        var before = await Raw(db, room.RoomId);
        var restored = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, Prototype, 77);
        Assert.Equal(FenxianImmediateDrawPolicy.CurrentRhythm, restored.Capture().Players[0].Combat.FenxianPolicy);
        var directory = Path.Combine(Path.GetTempPath(), "pr13-obsolete-api-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        const string source = """
            using System;
            using System.Linq;
            using FantasyCard.Domain.Combat;
            using FantasyCard.Domain.Players;
            public static class OldProbe {
                public static void Verify() {
                    PlayerCombatState state = new PlayerCombatState(HeroClass.Mage,
                        Enumerable.Repeat("common-01", 20).ToArray(), new Random(31),
                        useConsumptionBasedFenxian: true);
                    _ = state.GuardianShieldRemainder;
                }
            }
            """;
        try
        {
            var assembly = typeof(PlayerCombatState).Assembly.Location;
            await File.WriteAllTextAsync(Path.Combine(directory, "Probe.cs"), source, Ct);
            await File.WriteAllTextAsync(Path.Combine(directory, "Probe.csproj"),
                "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup>" +
                "<ItemGroup><Reference Include=\"FantasyCard.Domain\"><HintPath>" + SecurityElement.Escape(assembly) +
                "</HintPath></Reference></ItemGroup></Project>", Ct);
            var start = new ProcessStartInfo("dotnet") { WorkingDirectory = directory, RedirectStandardOutput = true, RedirectStandardError = true };
            foreach (var arg in new[] { "build", "Probe.csproj", "--nologo", "--verbosity", "minimal", "-p:UseSharedCompilation=false", "-p:NuGetAudit=false", "-maxcpucount:1" }) start.ArgumentList.Add(arg);
            using var process = Process.Start(start) ?? throw new InvalidOperationException("Native compiler did not start.");
            var stdout = process.StandardOutput.ReadToEndAsync(Ct);
            var stderr = process.StandardError.ReadToEndAsync(Ct);
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(Ct);
            timeout.CancelAfter(TimeSpan.FromSeconds(60));
            try { await process.WaitForExitAsync(timeout.Token); }
            catch (OperationCanceledException) { if (!process.HasExited) process.Kill(entireProcessTree: true); throw; }
            var log = await stdout + await stderr;
            Assert.NotEqual(0, process.ExitCode);
            Assert.Contains("CS1739", log, StringComparison.Ordinal);
            Assert.Contains("useConsumptionBasedFenxian", log, StringComparison.Ordinal);
            Assert.Contains("CS1061", log, StringComparison.Ordinal);
            Assert.Contains("GuardianShieldRemainder", log, StringComparison.Ordinal);
            Assert.Equal(before, await Raw(db, room.RoomId));
            Record("PR13-B02.1-T01", new { compilerExitCode = process.ExitCode, diagnostics = CompilerDiagnostics,
                obsoleteParameter = "useConsumptionBasedFenxian", obsoleteProperty = "GuardianShieldRemainder", compilerLog = log,
                probeSource = source, domainAssemblyHash = HashBytes(await File.ReadAllBytesAsync(assembly, Ct)),
                databaseBeforeHash = Hash(before), databaseAfterHash = Hash(await Raw(db, room.RoomId)) });
        }
        finally { Directory.Delete(directory, recursive: true); }
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Default_persisted_constructor_stays_current_rhythm_and_current_steps()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics();
        var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var rows = new List<object>();
        foreach (var hero in new[] { HeroClass.Mage, HeroClass.Guardian })
        {
            var room = Room(hero); await Persist(db, repository, room);
            var state = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, Prototype, 77).GetPlayer(room.Capture().Players[0].PlayerId).Combat;
            Assert.Equal(FenxianImmediateDrawPolicy.CurrentRhythm, state.FenxianDrawPolicy);
            Assert.Equal(GuardianShieldBonusPolicy.CurrentSteps, state.GuardianShieldPolicy);
            var observations = new List<int>();
            for (var i = 0; i < 5; i++) observations.Add(hero == HeroClass.Mage ? state.UpdateFenxian(CardElement.Fire, 1).Draw : state.ResolveShield(1));
            if (hero == HeroClass.Mage) Assert.Equal(DefaultMageDraws, observations);
            else { Assert.Equal(DefaultGuardianShields, observations); Assert.Equal(0, state.GuardianShieldRemainderTenths); }
            rows.Add(new { hero, snapshotHash = Hash(room.Capture()), state.FenxianDrawPolicy, state.GuardianShieldPolicy, observations });
        }
        Record("PR13-B02.1-T02", new { rows });
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Explicit_candidate_enums_survive_database_restore_and_have_independent_assertions()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics();
        var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var rows = new List<object>();
        foreach (var count in new[] { 1, 3, 5 })
        {
            var room = Room(HeroClass.Mage, new(CardsSpentDraw: true)); await Persist(db, repository, room);
            var state = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, Prototype, 77).GetPlayer(room.Capture().Players[0].PlayerId).Combat;
            Assert.Equal(FenxianImmediateDrawPolicy.CoreCardsSpent, state.FenxianDrawPolicy);
            var draws = Enumerable.Range(0, 8).Select(_ => state.UpdateFenxian(CardElement.Fire, count).Draw).ToArray();
            Assert.All(draws, actual => Assert.Equal(count == 1 ? 0 : count == 3 ? 1 : 2, actual));
            rows.Add(new { hero = "Mage", count, draws, state.FenxianDrawPolicy });
        }
        foreach (var level in Enumerable.Range(0, 6))
        {
            var room = Room(HeroClass.Guardian, new(FractionalGuardian: true), level); await Persist(db, repository, room);
            var state = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, Prototype, 77).GetPlayer(room.Capture().Players[0].PlayerId).Combat;
            var total = 0;
            for (var i = 0; i < 5; i++) { var draft = state.PreviewShield(1); total += state.GainShield(draft.Shield) - 1; state.CommitGuardianShieldRemainder(draft.RemainderTenthsAfter); }
            Assert.Equal(5 + 2 * level, total); Assert.Equal(0, state.GuardianShieldRemainderTenths);
            rows.Add(new { hero = "Guardian", level, totalWeaponBonus = total, state.GuardianShieldPolicy, state.GuardianShieldRemainderTenths });
        }
        Record("PR13-B02.1-T03", new { rows });
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Persisted_resolver_context_preserves_first_core_floor_tuning_and_dual_element_contracts()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var rows = new List<object>();
        var fire = Element("fire", CardElement.Fire, 8); var water = Element("water", CardElement.Water, 7);
        rows.Add(await Vector(db, "fire-first", [fire, water], 19, 3, CardElement.Fire, 1, 1, .2, 1, new(new(FireDamageBonus: .14)), new() { [CardElement.Fire] = -.30, [CardElement.Water] = .50 }));
        rows.Add(await Vector(db, "water-first", [water, fire], 6, 2, CardElement.Water, 1, 1, .2, 1, new(new(FireDamageBonus: .14)), new() { [CardElement.Fire] = -.30, [CardElement.Water] = .50 }));
        rows.Add(await Vector(db, "per-card-floor", [Element("f1", CardElement.Fire, 3), Element("f2", CardElement.Fire, 3), Element("f3", CardElement.Fire, 3)], 12, 0, CardElement.Fire, 3, 0, 0, 1.4, new(new(FireDamageBonus: .14))));
        rows.Add(await Vector(db, "tuning-core", [new("tune", new(ElementalDamage: 4, Element: CardElement.Fire, IsElementTuning: true)), fire], 13, 0, CardElement.Fire, 2, 0, 0, 1.2));
        rows.Add(await Vector(db, "tuning-no-conflict", [fire, new("tune", new(ElementalDamage: 5, Element: CardElement.Water, IsElementTuning: true))], 13, 0, CardElement.Fire, 1, 0, 0, 1));
        var boss = new CombatCardDefinition("boss", new(ElementalDamage: 8, Element: CardElement.Fire, SecondaryElementalDamage: 8, SecondaryElement: CardElement.Metal));
        rows.Add(await Vector(db, "dual-no-core", [boss], 14, 0, null, 0, 0, 0, 1, new(new(FireDamageBonus: .14)), new() { [CardElement.Fire] = -.30, [CardElement.Metal] = .60 }));
        rows.Add(await Vector(db, "dual-with-core", [water, boss], 12, 0, CardElement.Water, 1, 0, 0, 1, new(new(WaterDamageBonus: .20)), new() { [CardElement.Water] = .50 }));
        Record("PR13-B02.2-T01", new { rows });
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Exact_GDD_fire_contexts_restore_from_database_to_46_72_113()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var cards = new[] { Element("f8", CardElement.Fire, 8), Element("f3", CardElement.Fire, 3),
            new CombatCardDefinition("fuel", new(ElementalDamage: 12, Element: CardElement.Fire, SameElementBonus: 2)),
            Element("f6", CardElement.Fire, 6), Element("f10", CardElement.Fire, 10) };
        var rows = new List<object>();
        foreach (var (count, damage) in new[] { (3, 46), (4, 72), (5, 113) })
            rows.Add(await Vector(db, "GDD-fire-" + count, cards[..count], damage, 0, CardElement.Fire, count, 0, 0, 1 + .2 * (count - 1), new(new(FireDamageBonus: .14)), new() { [CardElement.Fire] = -.30 }));
        Record("PR13-B02.2-T02", new { rows, scope = "Exact listed cards, level zero, fire equipment .14 and resistance -.30; not arbitrary fire cards" });
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Priest_card_heal_and_conflict_E0_remain_separate_after_database_restore()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        CombatCardDefinition[] elemental = [Element("fire", CardElement.Fire, 8), Element("water", CardElement.Water, 7)];
        var equipment = new CombatEquipmentProfile(new(), VitalityHealBonus: .20);
        var recovery = await Vector(db, "conflict-only", elemental, 13, 2, CardElement.Fire, 1, 1, .2, 1, equipment, hero: HeroClass.Priest, damageTaken: 40);
        var cardOnly = await Vector(db, "card-only", [new("heal", new(Heal: 8))], 0, 13, null, 0, 0, 0, 1, equipment, hero: HeroClass.Priest, damageTaken: 40);
        var combined = await Vector(db, "combined", [.. elemental, new("heal", new(Heal: 8))], 13, 18, CardElement.Fire, 1, 1, .2, 1, equipment, hero: HeroClass.Priest, damageTaken: 40);
        Record("PR13-B02.2-T03", new { recovery, cardOnly, combined, expectedConflictE0 = 2, expectedCardOnly = 13, expectedCombined = 18 });
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task New_policy_source_changes_new_rooms_without_changing_current_persisted_room()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics(); var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var source = NumericalRules.Legacy; var old = Room(HeroClass.Guardian, source); await Persist(db, repository, old);
        var before = old.Capture(); var durableBefore = await Raw(db, old.RoomId);
        source = new(CardsSpentDraw: true, FractionalGuardian: true, OptionalMonsterPool: true);
        var next = Room(HeroClass.Guardian, source); await Persist(db, repository, next);
        var restored = BattleRoom.Restore((await repository.GetAsync(old.RoomId, Ct))!, Prototype, 999);
        Assert.Equivalent(before, old.Capture(), strict: true); Assert.Equivalent(before, restored.Capture(), strict: true);
        Assert.Equal(durableBefore, await Raw(db, old.RoomId)); Assert.False(restored.Numerics.FractionalGuardian); Assert.True(next.Numerics.FractionalGuardian);
        var candidateBefore = next.Capture(); source = NumericalRules.Legacy; var rollback = Room(HeroClass.Guardian, source); await Persist(db, repository, rollback);
        Assert.True(BattleRoom.Restore((await repository.GetAsync(next.RoomId, Ct))!, Prototype, 123).Numerics.FractionalGuardian); Assert.False(rollback.Numerics.FractionalGuardian);
        Record("PR13-B02.4-T01", new { oldRoom = old.RoomId, newRoom = next.RoomId, rollbackRoom = rollback.RoomId,
            oldSourceHash = Hash(before.Numerics), candidateSourceHash = Hash(candidateBefore.Numerics), rollbackSourceHash = Hash(rollback.Numerics),
            oldBeforeHash = Hash(before), oldAfterHash = Hash(restored.Capture()), databaseBeforeHash = Hash(durableBefore), databaseAfterHash = Hash(await Raw(db, old.RoomId)),
            candidateFrozen = true, newRoomCandidateEnabled = true, rollbackNewRoomDefaults = true });
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Persisted_PVP_working_copy_restores_complete_original_PVE_and_policy()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics(); var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var room = Room(HeroClass.Guardian, new(CardsSpentDraw: true, FractionalGuardian: true)); var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        player.Combat.TakeDamage(11); player.Combat.GainShield(7); player.Combat.CommitGuardianShieldRemainder(4);
        player.Combat.AddDrawCharge(.45); player.Combat.ApplyDrawSpeed(TimeSpan.FromSeconds(6), -.25); player.Combat.ApplyStun(TimeSpan.FromSeconds(1.4));
        var before = room.CapturePlayer(player.PlayerId); var opponent = Guid.NewGuid(); room.AddPlayer(new(opponent, HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null));
        await Persist(db, repository, room);
        var duel = room.StartDuel(player.PlayerId, opponent, Now); player.Combat.CommitGuardianShieldRemainder(8); player.Combat.TakeDamage(19);
        await new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics).SaveIfDueAsync(room.Capture(), Ct);
        var persistedDuel = (await repository.GetAsync(room.RoomId, Ct))!; room = BattleRoom.Restore(persistedDuel, Prototype, 333);
        Assert.Equal(PveBattlePhase.Frozen, room.GetPlayer(player.PlayerId).Pve!.Phase);
        room.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave); var after = room.CapturePlayer(player.PlayerId);
        Assert.Equivalent(before, after, strict: true); await new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics).SaveIfDueAsync(room.Capture(), Ct);
        var again = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, Prototype, 444);
        Assert.Equivalent(before, again.CapturePlayer(player.PlayerId), strict: true);
        Record("PR13-B02.4-T02", new { beforeHash = Hash(before), afterHash = Hash(after), restoredAgainHash = Hash(again.CapturePlayer(player.PlayerId)),
            pvpWorkingRemainder = 8, restoredPveRemainder = after.Combat.GuardianShieldRemainderTenths, persistedDuelHash = Hash(persistedDuel), frozenPveVerified = true });
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Missing_legacy_policy_fields_use_defaults_and_invalid_values_reject_before_mutation()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics(); var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var room = Room(HeroClass.Guardian); await Persist(db, repository, room);
        var json = JsonNode.Parse(await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", room.RoomId))!;
        json.AsObject().Remove("numerics"); var combat = json["players"]![0]!["combat"]!.AsObject();
        foreach (var name in new[] { "fenxianPolicy", "guardianPolicy", "guardianShieldRemainderTenths" }) combat.Remove(name);
        var legacy = json.ToJsonString(); await ReplaceSnapshot(db, room.RoomId, legacy);
        var restored = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, Prototype, 999); var player = restored.GetPlayer(room.Capture().Players[0].PlayerId);
        Assert.Equal(FenxianImmediateDrawPolicy.CurrentRhythm, player.Combat.FenxianDrawPolicy); Assert.Equal(GuardianShieldBonusPolicy.CurrentSteps, player.Combat.GuardianShieldPolicy);
        Assert.False(restored.Numerics.FractionalGuardian); var liveBefore = player.Combat.Capture(); var faults = new List<object>();
        foreach (var name in new[] { "fenxianPolicy", "guardianPolicy", "guardianShieldRemainderTenths" })
        {
            var invalid = JsonNode.Parse(legacy)!; invalid["players"]![0]!["combat"]![name] = name == "guardianShieldRemainderTenths" ? 10 : 999;
            invalid["players"]![0]!["combat"]!["hp"] = 1; await ReplaceSnapshot(db, room.RoomId, invalid.ToJsonString());
            var durable = await Raw(db, room.RoomId); var checkpoint = (await repository.GetAsync(room.RoomId, Ct))!;
            Assert.Throws<DomainValidationException>(() => BattleRoom.Restore(checkpoint, Prototype, 999));
            Assert.Throws<DomainValidationException>(() => player.Combat.Restore(checkpoint.Players[0].Combat));
            Assert.Equivalent(liveBefore, player.Combat.Capture(), strict: true); Assert.Equal(durable, await Raw(db, room.RoomId));
            faults.Add(new { field = name, rejected = true, liveBeforeHash = Hash(liveBefore), liveAfterHash = Hash(player.Combat.Capture()),
                injectedDatabaseHash = Hash(durable), databaseAfterRejectionHash = Hash(await Raw(db, room.RoomId)) });
        }
        Record("PR13-B02.4-T03", new { legacyMissingFields = LegacyMissingFields,
            restoredFenxian = player.Combat.FenxianDrawPolicy, restoredGuardian = player.Combat.GuardianShieldPolicy, faults });
    }

    private static BattleRoom Room(HeroClass hero, NumericalRules? rules = null, int weaponLevel = 1, CombatEquipmentProfile? equipment = null, CombatCardCatalog? catalog = null, string[]? cards = null, string? configVersion = null)
    {
        cards ??= Enumerable.Repeat("common-01", 20).ToArray(); var room = new BattleRoom(Guid.NewGuid(), configVersion ?? "b02-policy-" + Hash(rules ?? NumericalRules.Legacy)[..12], catalog ?? Prototype, 77, rules);
        var monster = new MonsterCombatState("test-monster", 500, 500, 0, TimeSpan.FromSeconds(4), [new(MonsterIntentKind.Attack, 3, CardElement.Wood)]);
        room.AddPlayer(new(Guid.NewGuid(), hero, cards, new(Guid.NewGuid(), null, [monster]), weaponLevel, Equipment: equipment)); return room;
    }

    private static async Task Persist(PostgresTestSchema db, RoomSnapshotRepository repository, BattleRoom room)
    {
        await using var command = db.DataSource.CreateCommand("INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',77,$3,'Running',now())");
        command.Parameters.AddWithValue(Guid.NewGuid()); command.Parameters.AddWithValue(room.RoomId); command.Parameters.AddWithValue(room.ConfigVersion);
        await command.ExecuteNonQueryAsync(Ct); await repository.SaveIfDueAsync(room.Capture(), Ct);
    }

    private static Task<string> Raw(PostgresTestSchema db, Guid room) => db.ScalarAsync<string>("SELECT snapshot_json::text || rng_state_json::text FROM room_snapshots WHERE room_id=$1", room);
    private static async Task ReplaceSnapshot(PostgresTestSchema db, Guid room, string json)
    {
        await using var command = db.DataSource.CreateCommand("UPDATE room_snapshots SET snapshot_json=$2::jsonb WHERE room_id=$1");
        command.Parameters.AddWithValue(room); command.Parameters.AddWithValue(json); Assert.Equal(1, await command.ExecuteNonQueryAsync(Ct));
    }
    private static CombatCardDefinition Element(string id, CardElement element, int value) => new(id, new(ElementalDamage: value, Element: element));
    private sealed record ResolverContext(CombatCardDefinition[] Cards, Dictionary<CardElement, double> Resistance, CombatEquipmentProfile Equipment);

    private static async Task<object> Vector(PostgresTestSchema db, string name, CombatCardDefinition[] cards, int damage, int heal, CardElement? core,
        int coreCount, int pairs, double cancellation, double resonance, CombatEquipmentProfile? equipment = null, Dictionary<CardElement, double>? resistance = null,
        HeroClass hero = HeroClass.Mage, int damageTaken = 0)
    {
        var input = new ResolverContext(cards, resistance ?? [], equipment ?? CombatEquipmentProfile.Empty); var inputJson = JsonSerializer.Serialize(input);
        await db.ExecuteAsync("CREATE TABLE IF NOT EXISTS pr13_resolver_context(name text PRIMARY KEY,payload jsonb NOT NULL)");
        await using (var command = db.DataSource.CreateCommand("INSERT INTO pr13_resolver_context(name,payload) VALUES($1,$2::jsonb)"))
        { command.Parameters.AddWithValue(name); command.Parameters.AddWithValue(inputJson); await command.ExecuteNonQueryAsync(Ct); }
        var context = JsonSerializer.Deserialize<ResolverContext>(await db.ScalarAsync<string>("SELECT payload::text FROM pr13_resolver_context WHERE name=$1", name))!;
        var catalog = new CombatCardCatalog(context.Cards); var room = Room(hero, weaponLevel: 0, equipment: context.Equipment, catalog: catalog, cards: Enumerable.Repeat(cards[0].CardId, 20).ToArray(), configVersion: "b02-vector-" + Hash(context)[..12]);
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId); player.Combat.TakeDamage(damageTaken);
        player.Combat.Deck.Restore(new(cards.Select(card => new CombatCardInstance(Guid.NewGuid(), card.CardId, 0)).ToArray(), [], [], 0));
        using var metrics = new ServerMetrics(); var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics); await Persist(db, repository, room);
        var durableBefore = await Raw(db, room.RoomId); room = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, catalog, 999); player = room.GetPlayer(player.PlayerId);
        var before = room.Capture(); var selected = player.Combat.Deck.Hand.Select(card => catalog.Get(card.CardId, card.Level)).ToArray();
        var actual = CombatResolver.Resolve(selected, player.Combat, element => context.Resistance.GetValueOrDefault(element));
        Assert.Equal((damage, heal, core, coreCount, pairs), (actual.Damage, actual.Heal, actual.CoreElement, actual.CoreCount, actual.ConflictPairCount));
        Assert.Equal(cancellation, actual.ConflictCancellation, 6); Assert.Equal(resonance, actual.ResonanceMultiplier, 6);
        Assert.Equivalent(before, room.Capture(), strict: true); Assert.Equal(durableBefore, await Raw(db, room.RoomId));
        return new { name, context, contextHash = Hash(context), room.ConfigVersion, selectedInstances = player.Combat.Deck.Hand, hero, weaponLevel = player.Combat.WeaponLevel,
            hp = player.Combat.Hp, expected = new { damage, heal, core, coreCount, pairs, cancellation, resonance }, actual,
            snapshotBeforeHash = Hash(before), snapshotAfterHash = Hash(room.Capture()), databaseBeforeHash = Hash(durableBefore), databaseAfterHash = Hash(await Raw(db, room.RoomId)) };
    }
    private static string Hash(object? value) => HashBytes(JsonSerializer.SerializeToUtf8Bytes(value));
    private static string HashBytes(byte[] value) => Convert.ToHexStringLower(SHA256.HashData(value));
    private static void Record(string caseId, object actual)
    {
        var directory = Environment.GetEnvironmentVariable("FANTASYCARD_PR13_NUMERICAL_EVIDENCE"); if (string.IsNullOrWhiteSpace(directory)) return;
        Directory.CreateDirectory(directory); File.WriteAllText(Path.Combine(directory, caseId + ".json"), JsonSerializer.Serialize(new { caseId, status = "Passed", actual }) + Environment.NewLine);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Source_workbook_reexport_mismatch_cannot_replace_a_persisted_room()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics();
        var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var game = GameConfigCatalog.Current;
        var catalog = new CombatCardCatalog(game.Cards.Select(card => new CombatCardDefinition(card.CardId, card.Effect)));
        var cards = Enumerable.Range(1, 13).Select(i => $"C{i:D2}")
            .Concat(Enumerable.Range(1, 7).Select(i => $"GUA-{i:D2}")).ToArray();
        var room = Room(HeroClass.Guardian, game.Numerics, weaponLevel: 0,
            catalog: catalog, cards: cards, configVersion: game.Version);
        await Persist(db, repository, room);
        var durableBefore = await Raw(db, room.RoomId);
        var before = room.Capture();
        var matchesBefore = await db.ScalarAsync<long>("SELECT count(*) FROM matches");
        var snapshotsBefore = await db.ScalarAsync<long>("SELECT count(*) FROM room_snapshots");
        using var resource = typeof(GameConfigCatalog).Assembly.GetManifestResourceStream(
            "FantasyCard.Config.fantasycard.config.bytes")!;
        using var resourceBytes = new MemoryStream();
        resource.CopyTo(resourceBytes);
        var published = File.ReadAllBytes("/control/base-root/server/config/generated/fantasycard.config.bytes");
        Assert.Equal(HashBytes(published), HashBytes(resourceBytes.ToArray()));

        async Task<(int Exit, JsonDocument Report)> Check(string root)
        {
            using var process = new Process();
            process.StartInfo = new ProcessStartInfo("python3")
            {
                RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false
            };
            process.StartInfo.ArgumentList.Add("/control/base-root/tools/source-export-guard.original.py");
            process.StartInfo.ArgumentList.Add(root);
            Assert.True(process.Start());
            var stdout = process.StandardOutput.ReadToEndAsync(Ct);
            var stderr = process.StandardError.ReadToEndAsync(Ct);
            await process.WaitForExitAsync(Ct);
            Assert.Equal(string.Empty, await stderr);
            return (process.ExitCode, JsonDocument.Parse(await stdout));
        }
        var positive = await Check("positive");
        using var positiveReport = positive.Report;
        Assert.Equal(0, positive.Exit);
        Assert.Equal("ValidExport", positiveReport.RootElement.GetProperty("state").GetString());
        Assert.Equal(game.Version, positiveReport.RootElement.GetProperty("version").GetString());
        var negative = await Check("negative");
        using var negativeReport = negative.Report;
        Assert.Equal(3, negative.Exit);
        Assert.Equal("Blocked", negativeReport.RootElement.GetProperty("state").GetString());
        Assert.False(negativeReport.RootElement.GetProperty("runtime_stage_created").GetBoolean());
        Assert.Equal("Source re-export differs from frozen published config",
            negativeReport.RootElement.GetProperty("reason").GetString());
        var witness = JsonDocument.Parse(File.ReadAllText("/control/source-export-witness.original.json"));
        using (witness)
        {
            Assert.True(witness.RootElement.GetProperty("same_export_version").GetBoolean());
            Assert.True(witness.RootElement.GetProperty("original_export_matches_published").GetBoolean());
            Assert.True(witness.RootElement.GetProperty("changed_reexport_embedded_hash_valid").GetBoolean());
            Assert.Equal(1, witness.RootElement.GetProperty("changed_semantic_cells").GetInt32());
            var after = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, catalog, 999);
            Assert.Equivalent(before, after.Capture(), strict: true);
            Assert.Equal(durableBefore, await Raw(db, room.RoomId));
            Assert.Equal(matchesBefore, await db.ScalarAsync<long>("SELECT count(*) FROM matches"));
            Assert.Equal(snapshotsBefore, await db.ScalarAsync<long>("SELECT count(*) FROM room_snapshots"));
            Record("PR13-B12.1-T01", new
            {
                roomId = room.RoomId, actualConfigVersion = game.Version, cards,
                embeddedPublishedBytesSha256 = HashBytes(resourceBytes.ToArray()),
                originalPublishedBytesSha256 = HashBytes(published),
                actualPositiveExitCode = positive.Exit, actualInvalidExitCode = negative.Exit,
                actualPositive = positiveReport.RootElement.Clone(),
                actualRejection = negativeReport.RootElement.Clone(),
                actualSourceExportWitness = witness.RootElement.Clone(),
                snapshotBeforeHash = Hash(before), snapshotAfterHash = Hash(after.Capture()),
                databaseBeforeHash = Hash(durableBefore), databaseAfterHash = Hash(await Raw(db, room.RoomId)),
                matchesBefore, matchesAfter = await db.ScalarAsync<long>("SELECT count(*) FROM matches"),
                snapshotsBefore, snapshotsAfter = await db.ScalarAsync<long>("SELECT count(*) FROM room_snapshots"),
                candidateAdmitted = false, productionSourceModified = false
            });
        }
    }
}
