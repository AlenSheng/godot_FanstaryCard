using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

internal static class Probe
{
    static readonly JsonSerializerOptions Json = new() { WriteIndented = false };
    static readonly MethodInfo SelectMethod = typeof(CombatExperience).GetMethod("Select", BindingFlags.NonPublic | BindingFlags.Static)!;
    static readonly MethodInfo HoldMethod = typeof(CombatExperience).GetMethod("ShouldHold", BindingFlags.NonPublic | BindingFlags.Static)!;
    static string Encode(object value) => JsonSerializer.Serialize(value, Json);
    static string Hash(object value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(Encode(value))));
    static void Require(bool condition, string reason) { if (!condition) throw new InvalidOperationException(reason); }
    static CombatCardInstance[] Select(CombatCardCatalog cards, PlayerCombatState state, MonsterCombatState target, string policy) =>
        (CombatCardInstance[])SelectMethod.Invoke(null, [cards, state, target, policy])!;
    static bool Hold(CombatCardCatalog cards, PlayerCombatState state, string policy) =>
        (bool)HoldMethod.Invoke(null, [cards, state, policy])!;

    public static int Main(string[] args)
    {
        var output = args.Single();
        var config = GameConfigCatalog.Current;
        var catalog = CombatCardCatalog.CreatePrototype();
        var metamorphic = new List<object>();
        var full = new List<object>();
        var failures = new List<object>();
        var actualFull = 0; var actualArms = 0; var casts = 0; var censoring = new Dictionary<string, int>();
        foreach (var hero in new[] { HeroClass.Mage, HeroClass.Priest, HeroClass.Guardian })
        foreach (var strategy in new[] { "baseline_all_hand", "basic", "build" })
        foreach (var candidate in new[] { false, true })
        foreach (var seed in new[] { 202610160, 202610161, 202610162 })
        {
            var profile = candidate ? "CandidateClassPassives" : "Baseline";
            var context = new { hero = hero.ToString(), strategy, profile, seed };
            var rules = candidate ? config.Numerics with { CardsSpentDraw = hero == HeroClass.Mage,
                FractionalGuardian = hero == HeroClass.Guardian } : config.Numerics;
            var deck = CombatExperience.CreateDecks(config, hero)["default"];
            try
            {
                var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, seed, rules);
                var actor = room.AddPlayer(new BattleRoomPlayerSetup(Guid.NewGuid(), hero, deck, null, WeaponLevel: 0));
                var map = ChaosMapGenerator.Generate(seed, 1).Capture();
                var cell = map.Cells.First(value => value.Layer == ChaosMapLayer.Outer && !value.IsBoss);
                var encounter = cell with { MonsterGroupId = "O6", IsBoss = false, HasSpring = false };
                room.InitializeMap(ChaosMapState.Restore(map with {
                    Cells = map.Cells.Select(value => value.Position == cell.Position ? encounter : value).ToArray(),
                    SpawnPositions = [cell.Position] }));
                var snapshot = room.Capture();
                var same = BattleRoom.Restore(snapshot, catalog, seed);
                var original = actor.Combat.Capture();
                var altered = original with { RandomState = original.RandomState ^ 0x9E3779B97F4A7C15UL,
                    Deck = original.Deck with { Library = original.Deck.Library.Reverse().ToArray() } };
                Require(Encode(original.Deck.Library) != Encode(altered.Deck.Library), "Hidden library control did not change");
                Require(original.RandomState != altered.RandomState, "Hidden RNG control did not change");
                var hidden = BattleRoom.Restore(snapshot with { Players = snapshot.Players.Select(value =>
                    value.PlayerId == actor.PlayerId ? value with { Combat = altered } : value).ToArray() }, catalog, seed);
                var sameActor = same.GetPlayer(actor.PlayerId);
                var hiddenActor = hidden.GetPlayer(actor.PlayerId);
                var visibleProjection = hiddenActor.Combat.Capture() with { RandomState = original.RandomState,
                    Deck = hiddenActor.Combat.Capture().Deck with { Library = original.Deck.Library } };
                Require(Encode(original) == Encode(visibleProjection), "Visible combat state differs");
                var before = new[] { Encode(room.Capture()), Encode(same.Capture()), Encode(hidden.Capture()) };
                var target = actor.Pve!.Monsters.First(monster => !monster.IsDead);
                var chosen = Select(catalog, actor.Combat, target, strategy);
                var repeated = Select(catalog, sameActor.Combat, sameActor.Pve!.Monsters.First(monster => !monster.IsDead), strategy);
                var changed = Select(catalog, hiddenActor.Combat, hiddenActor.Pve!.Monsters.First(monster => !monster.IsDead), strategy);
                Require(chosen.Length > 0, "No selected cards");
                Require(Encode(chosen) == Encode(repeated), "Same visible state and seed changed ordered action");
                Require(Encode(chosen) == Encode(changed), "Hidden library/RNG changed ordered action");
                Require(Hold(catalog, actor.Combat, strategy) == Hold(catalog, hiddenActor.Combat, strategy), "Hidden future changed hold decision");
                Require(before.SequenceEqual(new[] { Encode(room.Capture()), Encode(same.Capture()), Encode(hidden.Capture()) }), "Strategy selection mutated state");
                foreach (var arm in new[] { (Room: room, Actor: actor, Cards: chosen), (Room: hidden, Actor: hiddenActor, Cards: changed) })
                {
                    actualArms++;
                    Require(arm.Cards.Select(card => card.InstanceId).Distinct().Count() == arm.Cards.Length, "Duplicate card instance issued");
                    Require(arm.Cards.All(card => arm.Actor.Combat.Deck.Hand.Any(held => held.InstanceId == card.InstanceId)), "Non-hand card selected");
                    var result = arm.Room.PlayCards(arm.Actor.PlayerId, arm.Actor.Pve!.BattleId,
                        arm.Actor.Pve.Monsters.First(monster => !monster.IsDead).MonsterId,
                        arm.Cards.Select(card => card.InstanceId).ToArray(), arm.Room.Revision, DateTimeOffset.UnixEpoch);
                    Require(result is not null, "Actual domain play did not return a resolution");
                }
                metamorphic.Add(new { context, passed = true, same_state_action_equal = true, hidden_future_action_equal = true,
                    state_unmodified_by_selection = true, visible_projection_equal = true,
                    library_count = original.Deck.Library.Count, original_rng = original.RandomState, changed_rng = altered.RandomState,
                    action = chosen.Select(card => new { card.InstanceId, card.CardId, card.Level, card.ElementOverride }),
                    actual_legal_play_arms = 2, limitation = "Actions after the altered future becomes visible may legitimately diverge." });
            }
            catch (Exception error) { failures.Add(new { context, phase = "metamorphic", error = error.ToString() }); }

            var traces = new List<string[]>();
            var samples = new List<string>();
            for (var repeat = 0; repeat < 2; repeat++)
            {
                var trace = new List<string>();
                actualFull++;
                var sample = CombatExperience.Simulate(config, catalog, hero, "default", deck, "O6", strategy,
                    profile, rules, seed, (seed - 202610160) % 3, 60, 0, marginalAudit: true,
                    tuningObserver: value => { casts++; trace.Add(Encode(new {
                        value.Cast, value.AtSeconds, value.TargetId,
                        ordered_cards = value.Selected.Select(card => new { card.CardId, card.Level, card.ElementOverride }),
                        value.HpBefore, value.MaximumHp, value.ShieldBefore, value.Passed,
                        result = new { value.Actual.Damage, value.Actual.HpDamage, value.Actual.ShieldDamage,
                            value.Actual.Heal, value.Actual.ShieldGain, value.Actual.CoreElement,
                            value.Actual.ImmediateDraw, value.Actual.StunSeconds } })); });
                traces.Add(trace.ToArray()); samples.Add(Encode(sample));
                censoring[sample.Outcome] = censoring.GetValueOrDefault(sample.Outcome) + 1;
                full.Add(new { context, repeat, sample, ordered_action_trace = trace, trace_sha256 = Hash(trace) });
                if (sample.Error is not null) failures.Add(new { context, phase = "actual_simulate", repeat, error = sample.Error });
                if (sample.Actions != trace.Count) failures.Add(new { context, phase = "trace_count", repeat, sample.Actions, trace_count = trace.Count });
            }
            if (!traces[0].SequenceEqual(traces[1]) || samples[0] != samples[1])
                failures.Add(new { context, phase = "full_reproducibility", ordered_actions_equal = traces[0].SequenceEqual(traces[1]), samples_equal = samples[0] == samples[1] });
        }
        File.WriteAllText(Path.Combine(output, "metamorphic.original.json"), Encode(metamorphic));
        File.WriteAllText(Path.Combine(output, "encounters.original.json"), Encode(full));
        File.WriteAllText(Path.Combine(output, "failures.original.json"), Encode(failures));
        var summary = new { passed = failures.Count == 0 && metamorphic.Count == 54 && full.Count == 108,
            contexts = 54, metamorphic_passes = metamorphic.Count, actual_domain_play_arms = actualArms,
            full_encounters = actualFull, total_encounters = actualArms + actualFull, actual_full_casts = casts,
            full_outcomes = censoring, failures = failures.Count, case_targets = new[] { "PR13-B03.1-T01 EXPERIMENT", "PR13-B03.1-T02 EXPERIMENT" },
            T03_closed = false, production_defaults_activated = false, no_cloud_transfer = true,
            scope = "Existing strategies and actual Domain/Resolver/Deck; synthetic encounter entry, not natural route, capacity, strength or human experience." };
        File.WriteAllText(Path.Combine(output, "summary.json"), Encode(summary));
        Console.WriteLine(Encode(summary));
        return summary.passed ? 0 : 1;
    }
}
