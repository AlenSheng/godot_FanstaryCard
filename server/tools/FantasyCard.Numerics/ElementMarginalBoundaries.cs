using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

// Controlled boundary fixtures executed through the real Room.PlayCards path.
// They are separate from the representative paired encounter experiment.
internal static class ElementMarginalBoundaries
{
    private static readonly HeroClass[] Heroes = [HeroClass.Mage, HeroClass.Priest, HeroClass.Guardian];
    public static int Run(string[] args)
    {
        string Option(string name) { var i = Array.IndexOf(args, name);return i >= 0 && i + 1 < args.Length ? args[i + 1] : ""; }
        var sha = Option("--source-sha");var output = Path.GetFullPath(Option("--output"));
        if (!Regex.IsMatch(sha, "^[0-9a-f]{40}$") || Directory.Exists(output)) throw new ArgumentException("Exact source and new boundary output required.");
        Directory.CreateDirectory(output);
        var rows = new List<object>();
        foreach (var hero in Heroes)
        foreach (var (caseId, card) in new[] { ("PR13-B08.2-T01", "ET-WATER-G"), ("PR13-B08.2-T02", "ET-METAL-G"), ("PR13-B08.2-T03", "ET-EARTH-G") })
            rows.Add(Execute(hero, caseId, card));
        File.WriteAllText(Path.Combine(output, "boundaries.json"), JsonSerializer.Serialize(new
        {
            schema = "actual_element_marginal_boundaries_v1", source_sha = sha, rows,
            scope = "Actual Room.PlayCards boundary fixtures: fixed twenty-card budget, high-HP live target, full five-card hand, zero elapsed natural draw. Not representative encounter or LIVE acceptance.",
            weapon_level = 0, card_level = 0, candidate_activation = false, passed = true
        }));
        Console.WriteLine(JsonSerializer.Serialize(new { passed = true, rows = rows.Count, source_sha = sha }));return 0;
    }

    private static object Execute(HeroClass hero, string caseId, string replacement)
    {
        var config = GameConfigCatalog.Current;var catalog = CombatCardCatalog.CreatePrototype();
        var baseline = ElementMarginals.Baseline(config, hero);
        if (caseId == "PR13-B08.2-T03") baseline = baseline.Select(id => id == "C13" ? "C15" : id).ToArray();
        CombatExperience.ValidateDeck(config, hero, baseline);
        var candidate = ElementMarginals.Swap(baseline, replacement);
        PairedDeckBudget.Validate(config, hero, baseline, candidate);
        const int seed = 403001;
        var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, seed, config.Numerics);
        var player = room.AddPlayer(new BattleRoomPlayerSetup(Guid.NewGuid(), hero, baseline, null, WeaponLevel: 0));
        var map = ChaosMapGenerator.Generate(seed, 1).Capture();var cell = map.Cells.First(c => c.Layer == ChaosMapLayer.Outer && !c.IsBoss);
        room.InitializeMap(ChaosMapState.Restore(map with { Cells = map.Cells.Select(c => c.Position == cell.Position ? c with { MonsterGroupId = "O1", HasSpring = false } : c).ToArray(), SpawnPositions = [cell.Position] }));
        var state = room.Capture();var playerState = state.Players.Single();var combat = playerState.Combat;
        var all = combat.Deck.Hand.Concat(combat.Deck.Library).Concat(combat.Deck.Discard).ToArray();
        var played = caseId == "PR13-B08.2-T03" ? new[] { "ET-FIRE-G", "C15" } : new[] { "ET-FIRE-G" };
        var hand = played.Select(id => all.Single(c => c.CardId == id)).Concat(all.Where(c => !played.Contains(c.CardId)).Take(5 - played.Length)).ToArray();
        var library = all.Except(hand).ToArray();
        combat = combat with { Hp = combat.MaximumHp, Shield = combat.MaximumHp / 2,
            Deck = new CombatDeckSnapshot(hand, library, [], 0), FenxianCombo = caseId == "PR13-B08.2-T01" ? 4 : 0,
            LastFenxianCore = caseId == "PR13-B08.2-T01" ? CardElement.Water : null, FenxianChargeLevel = 0 };
        var pve = playerState.Pve!;
        pve = pve with { Monsters = pve.Monsters.Select(m => m with { MaximumHp = 100000, Hp = 100000, Shield = 0 }).ToArray() };
        state = state with { Players = [playerState with { Combat = combat, Pve = pve }] };
        var states = new Dictionary<string, string>(StringComparer.Ordinal);
        string Capture(BattleRoom value)
        {
            var raw = JsonSerializer.Serialize(value.Capture());var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(raw))).ToLowerInvariant();states.TryAdd(hash, raw);return hash;
        }
        var arms = new List<object>();
        foreach (var swapped in new[] { false, true })
        {
            CombatCardInstance Transform(CombatCardInstance c) => swapped && c.CardId == "ET-FIRE-G" ? c with { CardId = replacement } : c;
            var deck = combat.Deck with { Hand = combat.Deck.Hand.Select(Transform).ToArray(), Library = combat.Deck.Library.Select(Transform).ToArray() };
            var arm = BattleRoom.Restore(state with { Players = [playerState with { Combat = combat with { Deck = deck }, Pve = pve }] }, catalog, seed);
            var current = arm.GetPlayer(player.PlayerId);var target = current.Pve!.Monsters[0];var events = new List<object>();
            for (var cast = 0; cast < (caseId == "PR13-B08.2-T02" ? 3 : 1); cast++)
            {
                // Recycle the same owned instance at zero elapsed time to isolate overlap.
                if (cast > 0)
                {
                    var captured = current.Combat.Deck.Capture();var id = swapped ? replacement : "ET-FIRE-G";
                    var pool = captured.Hand.Concat(captured.Library).Concat(captured.Discard).ToArray();var card = pool.Single(c => c.CardId == id);
                    var oldHand = captured.Hand.Where(c => c.InstanceId != card.InstanceId).ToArray();
                    var newHand = oldHand.Take(4).Append(card).ToArray();
                    current.Combat.Deck.Restore(new(newHand, pool.Except(newHand).ToArray(), [], captured.DrawCharge));
                }
                var selected = current.Combat.Deck.Hand.Where(c => played.Contains(c.CardId == replacement ? "ET-FIRE-G" : c.CardId)).ToArray();
                var draft = CombatResolver.Resolve(selected.Select(c => catalog.Get(c.CardId, c.Level, c.ElementOverride)).ToArray(), current.Combat, target.ElementalResistance);
                var before = Capture(arm);var oldIds = current.Combat.Deck.Hand.Select(c => c.InstanceId).Except(selected.Select(c => c.InstanceId)).ToHashSet();var timer = target.StunRemaining.Ticks;
                var result = arm.PlayCards(current.PlayerId, current.Pve.BattleId, target.MonsterId, selected.Select(c => c.InstanceId).ToArray(), arm.Revision, DateTimeOffset.UnixEpoch);
                var actualDraw = current.Combat.Deck.Hand.Count(c => !oldIds.Contains(c.InstanceId));var addedUnion = Math.Max(0, target.StunRemaining.Ticks - timer);
                if (swapped && caseId == "PR13-B08.2-T01" && (actualDraw != 1 || result.ImmediateDraw <= actualDraw)) throw new InvalidOperationException("Water cap boundary did not occur.");
                if (swapped && caseId == "PR13-B08.2-T02" && (cast == 0 ? addedUnion != draft.Stun.Ticks : addedUnion != 0)) throw new InvalidOperationException("Metal overlap boundary differs.");
                if (caseId == "PR13-B08.2-T03" && (result.Heal != 0 || result.ShieldGain != 0 || draft.Heal <= 0 || swapped && draft.Shield <= 0)) throw new InvalidOperationException("Full recovery cap boundary did not occur.");
                events.Add(new { cast, before_state_sha256 = before, after_state_sha256 = Capture(arm), selected_cards = selected.Select(c => c.CardId),
                    requested_draw = result.ImmediateDraw, actual_draw = actualDraw, immediate_overflow = result.ImmediateDraw - actualDraw,
                    requested_heal = draft.Heal, effective_heal = result.Heal, heal_overflow = draft.Heal - result.Heal,
                    requested_shield = draft.Shield, effective_shield = result.ShieldGain, shield_overflow = draft.Shield - result.ShieldGain,
                    converted_control_ticks = draft.Stun.Ticks, admitted_control_ticks = (long)Math.Round(result.StunSeconds * TimeSpan.TicksPerSecond),
                    added_control_union_ticks = addedUnion, target_control_union_ticks = target.StunRemaining.Ticks, actual_damage = result.HpDamage + result.ShieldDamage, resolution = result });
            }
            arms.Add(new { profile = swapped ? "SingleGreenReplacement" : "BaselineGreenFire", events });
        }
        var budget = CombatExperience.Budget(config, baseline);
        return new { case_id = caseId, hero = hero.ToString(), seed, replacement, baseline_deck = baseline, candidate_deck = candidate,
            budget = new { rarity = budget.Rarity, unlock_cost = budget.UnlockCost }, natural_seconds = 0, paired_budget_guard_passed = true, arms, states, passed = true };
    }
}
