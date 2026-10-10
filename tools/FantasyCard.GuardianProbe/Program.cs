using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

return GuardianProbe.Run(args);

internal static class GuardianProbe
{
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();
    private static readonly DateTimeOffset Now = DateTimeOffset.UnixEpoch.AddSeconds(10);
    private static readonly int[] DefaultFive = [40, 40, 45, 45, 50, 50];
    private static readonly int[] CandidateFive = [40, 42, 44, 46, 48, 50];
    private static readonly int[] FromEight = [8, 2, 6, 0, 4, 8];

    public static int Run(string[] args)
    {
        string Option(string name)
        {
            var index = Array.IndexOf(args, name);
            return index >= 0 && index + 1 < args.Length ? args[index + 1] : throw new ArgumentException("Missing option: " + name);
        }
        var output = Path.GetFullPath(Option("--output"));
        var source = Option("--source-sha");
        var start = int.Parse(Option("--seed-start"));
        var samples = int.Parse(Option("--samples"));
        if (!Regex.IsMatch(source, "^[0-9a-f]{40}$") || start is < 1 or > int.MaxValue - 1000 || samples is < 1 or > 1000 || Directory.Exists(output))
            throw new ArgumentException("Exact source, bounded seeds and a new evidence directory required.");
        Directory.CreateDirectory(output);
        var manifest = new { Schema = "guardian_authoritative_sequences_v1", SourceSha = source,
            SeedStart = start, Samples = samples, WeaponLevels = Enumerable.Range(0, 6),
            Profiles = new[] { "Baseline", "Candidate" }, CardsPerSequence = 5,
            Fixture = "Injected legal hands and boundary states, actual BattleRoom/CombatDeck/Resolver/map/PVP; not full expeditions" };
        Write(Path.Combine(output, "manifest.json"), manifest);
        var rawPath = Path.Combine(output, "encounters.jsonl.gz");
        var rows = 0; var errors = 0; long rawBytes = 0;
        var vectors = new List<object>();
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        using (var file = new FileStream(rawPath, FileMode.CreateNew))
        using (var gzip = new GZipStream(file, CompressionLevel.Fastest))
        {
            for (var seed = start; seed < start + samples; seed++)
            {
                var map = ChaosMapGenerator.Generate(seed, 1).Capture();
                for (var level = 0; level <= 5; level++)
                foreach (var candidate in new[] { false, true })
                {
                    var trace = new Trace(seed, level, candidate);
                    try
                    {
                        PreviewAndReject(trace);
                        CapAndFivePlays(trace);
                        RestorePvpAndLeave(trace, map);
                        Require(trace.Passed, "Required sequence observations are incomplete.");
                    }
                    catch (Exception error)
                    {
                        trace.Error = new { type = error.GetType().Name, message = error.Message };
                        errors++;
                    }
                    var raw = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(trace) + "\n");
                    hash.AppendData(raw); gzip.Write(raw); rawBytes += raw.Length; rows++;
                    if (seed == start) vectors.Add(new { seed, level, candidate, trace.Passed, trace.Observations, trace.States, trace.NamedStates, trace.FiveWeaponContribution });
                }
            }
        }
        var rawSha = Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
        var summary = new { Schema = manifest.Schema, SourceSha = source, SeedStart = start, Samples = samples,
            RowCount = rows, ErrorCount = errors, RawSha256 = rawSha, RawBytes = rawBytes,
            Passed = errors == 0 && rows == samples * 12, ProductionActivation = false };
        Write(Path.Combine(output, "summary.native.json"), summary);
        Write(Path.Combine(output, "summary.json"), new { Native = summary, RawSha256 = rawSha,
            RawStorage = new { format = "gzip", file = "encounters.jsonl.gz", stored_bytes = new FileInfo(rawPath).Length,
                stored_sha256 = HashFile(rawPath), uncompressed_bytes = rawBytes } });
        Write(Path.Combine(output, "render-vectors.json"), new { source_sha = source, fixture_only = true, vectors });
        Console.WriteLine(JsonSerializer.Serialize(summary));
        return summary.Passed ? 0 : 1;
    }

    private static void PreviewAndReject(Trace trace)
    {
        var (room, player) = Create(trace, 1);
        SetHand(player, trace, 10, 1, "common-17");
        player.Combat.Restore(player.Combat.Capture() with { GuardianShieldRemainderTenths = trace.Candidate ? 8 : 0 });
        var ids = new[] { player.Combat.Deck.Hand[0].InstanceId };
        var before = trace.State("room-before-preview", room.Capture());
        CombatResolution? first = null;
        var previewStates = new List<string>();
        for (var index = 0; index < 10; index++)
        {
            var preview = room.PreviewCards(player.PlayerId, player.Pve!.BattleId, "fixture-monster", ids, room.Revision, Now);
            Require(Hash(room.Capture()) == before, "Preview changed the full room state.");
            if (first is not null) Require(Hash(preview) == Hash(first), "Repeated preview changed its result.");
            first = preview;
            previewStates.Add(Hash(room.Capture()));
        }
        var rejects = new List<object>();
        foreach (var fault in new[] { "missing-target", "future-revision", "duplicate-instances", "missing-instance" })
        {
            Reject(() => room.PlayCards(player.PlayerId, player.Pve!.BattleId,
                fault == "missing-target" ? "missing-target" : "fixture-monster",
                fault == "duplicate-instances" ? [ids[0], ids[0]] : fault == "missing-instance" ? [Id(trace.Seed, trace.Level, 999)] : ids,
                fault == "future-revision" ? room.Revision + 1 : room.Revision, Now));
            Require(Hash(room.Capture()) == before, "Rejected play changed the full room state.");
            rejects.Add(new { fault, state_sha256 = before, rejected = true });
        }
        var actual = room.PlayCards(player.PlayerId, player.Pve!.BattleId, "fixture-monster", ids, room.Revision, Now);
        Require(Hash(first! with { RoomRevision = actual.RoomRevision }) == Hash(actual), "Preview disagrees with successful play.");
        Require(player.Combat.GuardianShieldRemainderTenths == (trace.Candidate ? FromEight[trace.Level] : 0), "First committed remainder differs from golden value.");
        var after = trace.State("room-after-commit", room.Capture());
        Reject(() => room.PlayCards(player.PlayerId, player.Pve.BattleId, "fixture-monster", ids, room.Revision, Now));
        Require(Hash(room.Capture()) == after, "Reusing a spent instance changed the room.");
        trace.Add("PR13-B07.3-T01", "preview-and-rejections", new { previews = 10, preview_state_sha256 = previewStates, before, after, rejects,
            spent_instance = ids[0], spent_instance_rejected = true, resolution = actual, remainder = player.Combat.GuardianShieldRemainderTenths });
    }

    private static void CapAndFivePlays(Trace trace)
    {
        var (room, player) = Create(trace, 2);
        SetHand(player, trace, 20, 5, "common-17");
        var steps = new List<object>(); var total = 0;
        trace.State("five-start", player.Combat.Capture());
        for (var play = 0; play < 5; play++)
        {
            var id = player.Combat.Deck.Hand[0].InstanceId;
            var result = room.PlayCards(player.PlayerId, player.Pve!.BattleId, "fixture-monster", [id], room.Revision, Now);
            total += result.ShieldGain;
            steps.Add(new { play, instance_id = id, shield_gain = result.ShieldGain,
                state = trace.State("five-" + play, player.Combat.Capture()) });
        }
        var expected = trace.Candidate ? CandidateFive[trace.Level] : DefaultFive[trace.Level];
        Require(total == expected && player.Combat.GuardianShieldRemainderTenths == 0, "Five legal plays differ from the golden total/remainder.");
        trace.FiveWeaponContribution = total - 35;
        trace.Add("PR13-B07.3-T02", "five-successful-plays", new { steps, total, expected, weapon_contribution = trace.FiveWeaponContribution });
        var bonus = 1 + trace.Level / 2;
        foreach (var scenario in new[] { "already-full", "zero-empty", "zero-full", "exact-fill", "overflow" })
        {
            (room, player) = Create(trace, 3);
            var zero = scenario.StartsWith("zero", StringComparison.Ordinal);
            SetHand(player, trace, 30, 1, zero ? "common-01" : "common-17");
            var shield = scenario switch { "already-full" or "zero-full" => 50, "exact-fill" => 50 - (7 + bonus), "overflow" => 49, _ => 0 };
            player.Combat.Restore(player.Combat.Capture() with { Shield = shield, GuardianShieldRemainderTenths = trace.Candidate ? 4 : 0 });
            var before = trace.State(scenario + "-before", player.Combat.Capture());
            var result = room.PlayCards(player.PlayerId, player.Pve!.BattleId, "fixture-monster", [player.Combat.Deck.Hand[0].InstanceId], room.Revision, Now);
            var expectedGain = scenario switch { "exact-fill" => 7 + bonus, "overflow" => 1, _ => 0 };
            var expectedRemainder = trace.Candidate && scenario is not ("exact-fill" or "overflow") ? 4 : 0;
            Require(result.ShieldGain == expectedGain && player.Combat.Shield == shield + expectedGain && player.Combat.GuardianShieldRemainderTenths == expectedRemainder, "Cap/zero golden state differs: " + scenario);
            trace.Add("PR13-B07.3-T02", scenario, new { before, after = trace.State(scenario + "-after", player.Combat.Capture()), result.ShieldGain, expectedGain, expectedRemainder });
        }
    }

    private static void RestorePvpAndLeave(Trace trace, ChaosMapSnapshot map)
    {
        var (room, player) = Create(trace, 4);
        SetHand(player, trace, 40, 1, "common-17");
        player.Combat.Restore(player.Combat.Capture() with { Shield = 9, GuardianShieldRemainderTenths = trace.Candidate ? 4 : 0 });
        var frozen = trace.State("frozen-pve-combat", player.Combat.Capture());
        var frozenPve = trace.State("frozen-pve-battle", player.Pve!.Capture());
        var snapshot = room.Capture(); var serialized = JsonSerializer.Serialize(snapshot);
        room = BattleRoom.Restore(RoundTrip(snapshot), Catalog, trace.Seed + 1);
        Require(Hash(room.Capture()) == Hash(snapshot), "Room JSON restore differs from saved state.");
        var restoredRoomJson = JsonSerializer.Serialize(room.Capture());
        player = room.GetPlayer(player.PlayerId);
        var opponent = Id(trace.Seed, trace.Level, 45);
        room.AddPlayer(new(opponent, HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null));
        var duel = room.StartDuel(player.PlayerId, opponent, Now);
        SetHand(player, trace, 41, 1, "common-17");
        var result = room.PlayCards(player.PlayerId, duel.DuelId, opponent.ToString("D"), [player.Combat.Deck.Hand[0].InstanceId], room.Revision, Now);
        var during = trace.State("pvp-work-copy", player.Combat.Capture());
        Require(during != frozen, "The real PVP play did not change its work copy.");
        var pvpRoomJson = JsonSerializer.Serialize(room.Capture());
        room = BattleRoom.Restore(RoundTrip(room.Capture()), Catalog, trace.Seed + 2);
        room.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave);
        player = room.GetPlayer(player.PlayerId);
        Require(Hash(player.Combat.Capture()) == frozen && Hash(player.Pve!.Capture()) == frozenPve, "PVP return changed frozen PVE combat/battle.");
        trace.Add("PR13-B07.3-T03", "json-pvp-restoration", new { saved_room_sha256 = Hash(snapshot), saved_room_json = serialized, restored_room_json = restoredRoomJson, pvp_room_json = pvpRoomJson, frozen, frozenPve, during,
            after = trace.State("pve-after-return", player.Combat.Capture()), after_pve_battle = trace.State("pve-battle-after-return", player.Pve!.Capture()), pvp_resolution = result });
        // Phase injection is explicit boundary setup. The move itself uses the
        // real generated map, legality check, room method and shield clear.
        var movement = Create(trace, 5); room = movement.room; player = movement.player;
        room.InitializeMap(ChaosMapState.Restore(map));
        snapshot = room.Capture();
        snapshot = snapshot with { Players = snapshot.Players.Select(p => p with
        {
            Phase = RoomPlayerPhase.ActionBar, Pve = null,
            Combat = p.Combat with { Shield = 9, GuardianShieldRemainderTenths = trace.Candidate ? 4 : 0 }
        }).ToArray() };
        room = BattleRoom.Restore(snapshot, Catalog, trace.Seed + 3); player = room.GetPlayer(player.PlayerId);
        var from = player.Position!.Value;
        var legalMoves = room.Map!.GetNeighbors(from).Where(next => room.Map.CanMove(from, next)).ToArray();
        var target = legalMoves[0];
        var beforeMove = trace.State("leave-before", player.Combat.Capture());
        room.MovePlayerAndPair(player.PlayerId, target, room.Revision, Now);
        Require(player.Position == target && player.Combat.Shield == 0 && player.Combat.GuardianShieldRemainderTenths == 0, "Legal movement failed to clear shield and remainder.");
        trace.Add("PR13-B07.3-T03", "legal-map-leave", new { from, target, beforeMove,
            after = trace.State("leave-after", player.Combat.Capture()), legal_moves = legalMoves, actual_position = player.Position, generated_map_seed = trace.Seed, action_bar_phase_injected = true });
    }

    private static (BattleRoom room, RoomPlayerState player) Create(Trace trace, int tag)
    {
        var room = new BattleRoom(Id(trace.Seed, trace.Level, tag * 100), "guardian-boundary", Catalog, trace.Seed,
            new NumericalRules(FractionalGuardian: trace.Candidate));
        var monster = new MonsterCombatState("fixture-monster", 500, 500, 0, TimeSpan.FromSeconds(4), [new(MonsterIntentKind.Attack, 3, CardElement.None)]);
        var player = room.AddPlayer(new(Id(trace.Seed, trace.Level, tag * 100 + 1), HeroClass.Guardian,
            Enumerable.Repeat("common-17", 20).ToArray(), new(Id(trace.Seed, trace.Level, tag * 100 + 2), null, [monster]), WeaponLevel: trace.Level));
        return (room, player);
    }

    private static void SetHand(RoomPlayerState player, Trace trace, int tag, int count, string card) =>
        player.Combat.Deck.Restore(new(Enumerable.Range(0, count).Select(i => new CombatCardInstance(Id(trace.Seed, trace.Level, tag * 100 + i), card)).ToArray(),
            Enumerable.Range(0, 20).Select(i => new CombatCardInstance(Id(trace.Seed, trace.Level, tag * 100 + 50 + i), "common-17")).ToArray(), [], 0));
    private static Guid Id(int seed, int level, int tag)
    {
        var bytes = new byte[16]; BitConverter.GetBytes(seed).CopyTo(bytes, 0); BitConverter.GetBytes(level).CopyTo(bytes, 4); BitConverter.GetBytes(tag).CopyTo(bytes, 8);
        bytes[15] = 13; return new Guid(bytes);
    }
    private static T RoundTrip<T>(T value) => JsonSerializer.Deserialize<T>(JsonSerializer.Serialize(value))!;
    private static void Reject(Action action)
    {
        try { action(); } catch (DomainValidationException) { return; }
        throw new InvalidOperationException("Invalid or repeated operation was accepted.");
    }
    private static void Require(bool condition, string reason) { if (!condition) throw new InvalidOperationException(reason); }
    internal static string Hash<T>(T value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value)))).ToLowerInvariant();
    private static string HashFile(string path) { using var stream = File.OpenRead(path); return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant(); }
    private static void Write(string path, object value) => File.WriteAllText(path, JsonSerializer.Serialize(value));

    private sealed class Trace(int seed, int level, bool candidate)
    {
        public int Seed { get; } = seed;
        public int Level { get; } = level;
        public bool Candidate { get; } = candidate;
        public string Profile => Candidate ? "Candidate" : "Baseline";
        public bool Passed => Error is null && Observations.Count == 9;
        public object? Error { get; set; }
        public int FiveWeaponContribution { get; set; }
        public Dictionary<string, string> States { get; } = [];
        public Dictionary<string, string> NamedStates { get; } = [];
        public List<object> Observations { get; } = [];
        public string State<T>(string name, T value)
        {
            var hash = Hash(value); States[hash] = JsonSerializer.Serialize(value); NamedStates[name] = hash;
            return hash;
        }
        public void Add(string caseId, string scenario, object actual) => Observations.Add(new { case_id = caseId, scenario, passed = true, actual });
    }
}
