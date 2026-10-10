using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

return ControlProbe.Run(args);

internal static class ControlProbe
{
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();
    private static readonly DateTimeOffset Now = DateTimeOffset.UnixEpoch.AddSeconds(10);

    public static int Run(string[] args)
    {
        string Option(string name)
        {
            var i = Array.IndexOf(args, name);
            return i >= 0 && i + 1 < args.Length ? args[i + 1] : throw new ArgumentException(name);
        }
        var output = Path.GetFullPath(Option("--output"));
        var source = Option("--source-sha");
        var first = int.Parse(Option("--seed-start"));
        var samples = int.Parse(Option("--samples"));
        if (!Regex.IsMatch(source, "^[0-9a-f]{40}$") || first < 1 || first > int.MaxValue - 1000 || samples is < 1 or > 1000 || Directory.Exists(output))
            throw new ArgumentException("Exact source, bounded seeds and new output required.");
        Directory.CreateDirectory(output);
        Write(Path.Combine(output, "manifest.json"), new { source_sha = source, seed_start = first, samples,
            schema = "authoritative_control_contract_v1", heroes = new[] { "Mage", "Priest", "Guardian" }, weapon_levels = Enumerable.Range(0, 6),
            fixture = "Injected legal ET-METAL-G hands; actual BattleRoom/Resolver/target/Advance/JSON/PVP. Not a live expedition or balance recommendation." });
        var rows = 0; var errors = 0; long bytes = 0; var vectors = new List<object>();
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        var rawPath = Path.Combine(output, "controls.jsonl.gz");
        using (var file = new FileStream(rawPath, FileMode.CreateNew))
        using (var gzip = new GZipStream(file, CompressionLevel.Fastest))
        {
            for (var seed = first; seed < first + samples; seed++)
            foreach (var hero in new[] { HeroClass.Mage, HeroClass.Priest, HeroClass.Guardian })
            for (var level = 0; level < 6; level++)
            {
                var trace = new Trace(seed, hero, level, seed == first);
                try { SameWindow(trace); Boundary(trace); IndependentAndRestore(trace); }
                catch (Exception error) { trace.Error = error.GetType().Name + ": " + error.Message; errors++; }
                Require(trace.Events.Count <= 16, "Unexpected unbounded trace.");
                var raw = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { seed, hero = hero.ToString(), weapon_level = level,
                    passed = trace.Error is null && trace.Events.Count == 9, error = trace.Error, events = trace.Events, assertions = trace.Assertions }) + "\n");
                if (bytes + raw.Length > 512L * 1024 * 1024) throw new InvalidOperationException("Original raw evidence bound exceeded.");
                hash.AppendData(raw); gzip.Write(raw); bytes += raw.Length; rows++;
                if (seed == first) vectors.Add(new { seed, hero = hero.ToString(), weapon_level = level, events = trace.Events, assertions = trace.Assertions, states = trace.States });
            }
        }
        var summary = new { passed = errors == 0 && rows == samples * 18, source_sha = source, seed_start = first, samples, rows, errors,
            raw_bytes = bytes, raw_sha256 = Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant(), stored_bytes = new FileInfo(rawPath).Length,
            stored_sha256 = HashFile(rawPath), production_changed = false };
        Write(Path.Combine(output, "summary.json"), summary);
        Write(Path.Combine(output, "render-vectors.json"), new { source_sha = source, fixture_only = true, vectors });
        Console.WriteLine(JsonSerializer.Serialize(summary));
        return summary.passed ? 0 : 1;
    }

    private static void SameWindow(Trace t)
    {
        var (room, player) = Create(t, 1);
        var full = Play(t, room, player, "target-a", "PR13-B08.1-T01", "first", 10);
        var half = Play(t, room, player, "target-a", "PR13-B08.1-T01", "second", 11);
        var zero = Play(t, room, player, "target-a", "PR13-B08.1-T01", "third", 12);
        Require(half.AdmittedTicks == full.AdmittedTicks / 2 && zero.AdmittedTicks == 0, "Same-window full/half/zero differs.");
        Require(full.AddedUnionTicks == full.AdmittedTicks && half.AddedUnionTicks == 0 && zero.AddedUnionTicks == 0,
            "Overlapping control was counted more than once.");
        t.Assertions.Add(new { case_id = "PR13-B08.1-T01", passed = true, full_half_zero = true,
            admitted_sum_ticks = full.AdmittedTicks + half.AdmittedTicks, actual_union_ticks = full.AddedUnionTicks });
    }

    private static void Boundary(Trace t)
    {
        var (room, player) = Create(t, 2);
        var first = Play(t, room, player, "target-a", "PR13-B08.1-T02", "window-start", 20);
        room.Advance(TimeSpan.FromMilliseconds(7999), Now.AddMilliseconds(7999));
        var remaining = player.Combat.Capture().TargetStunWindows.Single().Remaining;
        Require(remaining == TimeSpan.FromMilliseconds(1), "7.999s did not retain the window.");
        var half = Play(t, room, player, "target-a", "PR13-B08.1-T02", "at-7999ms", 21);
        room.Advance(TimeSpan.FromMilliseconds(1), Now.AddSeconds(8));
        Require(player.Combat.Capture().TargetStunWindows.Count == 0, "Exactly 8.000s did not remove the window.");
        var restarted = Play(t, room, player, "target-a", "PR13-B08.1-T02", "at-8000ms", 22);
        Require(half.AdmittedTicks == first.AdmittedTicks / 2 && restarted.AdmittedTicks == first.AdmittedTicks, "Boundary did not restart full duration.");
        t.Assertions.Add(new { case_id = "PR13-B08.1-T02", passed = true, old_window_remaining_at_7999_ticks = remaining.Ticks,
            window_removed_at_8000 = true, independent_second_algorithm = false });
    }

    private static void IndependentAndRestore(Trace t)
    {
        var (room, player) = Create(t, 3);
        var a = Play(t, room, player, "target-a", "PR13-B08.1-T03", "target-a-first", 30);
        var b = Play(t, room, player, "target-b", "PR13-B08.1-T03", "target-b-first", 31);
        Require(a.AdmittedTicks == b.AdmittedTicks && player.Combat.Capture().TargetStunWindows.Count == 2, "Target windows are not independent.");
        var saved = room.Capture();
        room = BattleRoom.Restore(RoundTrip(saved), Catalog, t.Seed + 1);
        Require(Hash(room.Capture()) == Hash(saved), "JSON reconstruction changed the room.");
        player = room.GetPlayer(player.PlayerId);
        var frozen = player.Combat.Capture(); var frozenPve = player.Pve!.Capture();
        var opponent = Id(t, 3009);
        room.AddPlayer(new(opponent, HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null));
        var duel = room.StartDuel(player.PlayerId, opponent, Now);
        SetHand(player, t, 32);
        var card = Catalog.Get("ET-METAL-G");
        var requested = TimeSpan.FromSeconds(card.Effect.StunSeconds);
        var converted = CombatResolver.Resolve([card], player.Combat).Stun;
        Require(player.Combat.Capture().TargetStunWindows.Count == 0, "PVP did not start with independent target windows.");
        var target = room.GetPlayer(opponent); var before = target.Combat.StunRemaining;
        var resolution = room.PlayCards(player.PlayerId, duel.DuelId, opponent.ToString("D"), [player.Combat.Deck.Hand[0].InstanceId], room.Revision, Now);
        Require(TimeSpan.FromSeconds(resolution.StunSeconds) == converted && target.Combat.StunRemaining == converted, "PVP control did not take full duration.");
        t.Events.Add(new("PR13-B08.1-T03", "pvp-new-window", opponent.ToString("D"), requested.Ticks, converted.Ticks, converted.Ticks,
            before.Ticks, target.Combat.StunRemaining.Ticks, target.Combat.StunRemaining.Ticks - before.Ticks,
            player.Combat.Capture().TargetStunWindows.Single().Remaining.Ticks, t.State(room.Capture())));
        room = BattleRoom.Restore(RoundTrip(room.Capture()), Catalog, t.Seed + 2);
        room.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave);player = room.GetPlayer(player.PlayerId);
        Require(Hash(player.Combat.Capture()) == Hash(frozen) && Hash(player.Pve!.Capture()) == Hash(frozenPve), "PVP return changed frozen PVE state.");
        t.Assertions.Add(new { case_id = "PR13-B08.1-T03", passed = true, json_room_roundtrip_sha256 = Hash(saved),
            frozen_player_sha256 = Hash(frozen), returned_player_sha256 = Hash(player.Combat.Capture()), frozen_pve_sha256 = Hash(frozenPve),
            returned_pve_sha256 = Hash(player.Pve!.Capture()), separate_pvp_target_window = true, returned_room_state_sha256 = t.State(room.Capture()) });
    }

    private static ControlEvent Play(Trace t, BattleRoom room, RoomPlayerState player, string targetId, string caseId, string tag, int handTag)
    {
        SetHand(player, t, handTag);
        var card = Catalog.Get("ET-METAL-G");var requested = TimeSpan.FromSeconds(card.Effect.StunSeconds);
        var converted = CombatResolver.Resolve([card], player.Combat).Stun;
        var target = player.Pve!.GetTarget(targetId);var before = target.StunRemaining;
        var resolution = room.PlayCards(player.PlayerId, player.Pve.BattleId, targetId, [player.Combat.Deck.Hand[0].InstanceId], room.Revision, Now + room.Elapsed);
        var admitted = TimeSpan.FromSeconds(resolution.StunSeconds);var after = target.StunRemaining;
        Require(after == (admitted > before ? admitted : before), "Target timer differs from authoritative control.");
        var window = player.Combat.Capture().TargetStunWindows.Single(w => w.TargetId.EndsWith(":" + targetId, StringComparison.Ordinal));
        var e = new ControlEvent(caseId, tag, targetId, requested.Ticks, converted.Ticks, admitted.Ticks, before.Ticks, after.Ticks,
            Math.Max(0, after.Ticks - before.Ticks), window.Remaining.Ticks, t.State(room.Capture()));
        t.Events.Add(e);return e;
    }

    private static (BattleRoom Room, RoomPlayerState Player) Create(Trace t, int tag)
    {
        var room = new BattleRoom(Id(t, tag * 100), "control-boundary", Catalog, t.Seed);
        var monsters = new[] { "target-a", "target-b" }.Select(id => new MonsterCombatState(id, 10000, 10000, 0,
            TimeSpan.FromSeconds(600), [new(MonsterIntentKind.Attack, 1, CardElement.None)])).ToArray();
        var player = room.AddPlayer(new(Id(t, tag * 100 + 1), t.Hero, Enumerable.Repeat("ET-METAL-G", 20).ToArray(),
            new(Id(t, tag * 100 + 2), null, monsters), WeaponLevel: t.Level));
        return (room, player);
    }
    private static void SetHand(RoomPlayerState player, Trace t, int tag) => player.Combat.Deck.Restore(new(
        [new(Id(t, tag * 100), "ET-METAL-G")], Enumerable.Range(1, 20).Select(i => new CombatCardInstance(Id(t, tag * 100 + i), "ET-METAL-G")).ToArray(), [], 0));
    private static Guid Id(Trace t, int tag)
    {
        var bytes = new byte[16];BitConverter.GetBytes(t.Seed).CopyTo(bytes, 0);BitConverter.GetBytes(t.Level).CopyTo(bytes, 4);
        BitConverter.GetBytes(tag).CopyTo(bytes, 8);bytes[14] = (byte)t.Hero;bytes[15] = 8;return new Guid(bytes);
    }
    private static T RoundTrip<T>(T v) => JsonSerializer.Deserialize<T>(JsonSerializer.Serialize(v))!;
    private static string Hash<T>(T v) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(v)))).ToLowerInvariant();
    private static string HashFile(string p) { using var s = File.OpenRead(p);return Convert.ToHexString(SHA256.HashData(s)).ToLowerInvariant(); }
    private static void Write(string p, object v) => File.WriteAllText(p, JsonSerializer.Serialize(v));
    private static void Require(bool condition, string reason) { if (!condition) throw new InvalidOperationException(reason); }
    private sealed record ControlEvent(string CaseId, string Tag, string TargetId, long RequestedTicks, long ConvertedTicks, long AdmittedTicks,
        long BeforeRemainingTicks, long AfterRemainingTicks, long AddedUnionTicks, long WindowRemainingTicks, string RoomStateSha256);
    private sealed class Trace(int seed, HeroClass hero, int level, bool keepStates)
    {
        public int Seed { get; } = seed;
        public HeroClass Hero { get; } = hero;
        public int Level { get; } = level;
        public string? Error { get; set; }
        public List<ControlEvent> Events { get; } = [];
        public List<object> Assertions { get; } = [];
        public Dictionary<string, string> States { get; } = [];
        public string State<T>(T state)
        {
            var text = JsonSerializer.Serialize(state);var sha = Hash(state);
            if (keepStates) States.TryAdd(sha, text);return sha;
        }
    }
}
