using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

// A deterministic encounter experiment. These players use the same combat rules
// as human players (IsBot=false), rather than the accelerated server bot timer.
// Strategies may read only hand cards, their own public state and living targets.
internal static class CombatExperience
{
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = false };
    private static readonly JsonSerializerOptions PrettyJson = new() { WriteIndented = true };
    private static readonly string[] Groups = ["O1", "O6", "E1", "BOSS"];
    // Keep the original default matrix, while allowing every actual encounter
    // to be selected explicitly for coverage and regression diagnosis.
    private static readonly string[] AllowedGroups =
        ["O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8",
         "M1", "M2", "M3", "M4", "M5", "E1", "E2", "E3", "E4", "E5", "E6", "BOSS"];
    private static readonly string[] Strategies = ["baseline_all_hand", "basic", "build"];

    public static int Run(string[] args)
    {
        var samples = ReadInt(args, "--samples", 1_000);
        var seedStart = ReadInt(args, "--seed-start", 0);
        var limit = ReadInt(args, "--cutoff-seconds", 300);
        var weaponLevel = ReadInt(args, "--weapon-level", 0);
        var candidateKind = ReadString(args, "--candidate", "class-passives");
        var groups = ReadString(args, "--groups", string.Join(',', Groups)).Split(',');
        var strategies = ReadString(args, "--strategies", string.Join(',', Strategies)).Split(',');
        var heroes = ReadString(args, "--heroes", string.Join(',', Enum.GetValues<HeroClass>())).Split(',')
            .Select(value => Enum.Parse<HeroClass>(value)).ToArray();
        var output = ReadString(args, "--output", "combat-experience");
        if (samples < 3 || seedStart < 0 || (long)seedStart + samples > int.MaxValue || limit is < 60 or > 600 ||
            weaponLevel is < 0 or > 5 || groups.Length != groups.Distinct().Count() || groups.Any(group => !AllowedGroups.Contains(group)) ||
            heroes.Length != heroes.Distinct().Count() || heroes.Any(hero => !Enum.IsDefined(hero)) ||
            strategies.Length != strategies.Distinct().Count() || strategies.Any(strategy => !Strategies.Contains(strategy)) ||
            candidateKind is not ("class-passives" or "outer-o6-hp085" or "outer-o6-hp095" or "outer-o6-hp090" or
                "outer-o6-interval110" or "outer-o6-windup025" or "outer-o6-windup050" or
                "elite-e4-hp095" or "elite-e4-hp090"))
            throw new ArgumentException("At least three seeds, a valid seed interval and a 60-600 second cutoff are required.");
        Directory.CreateDirectory(output);
        var config = GameConfigCatalog.Current;
        var catalog = CombatCardCatalog.CreatePrototype();
        var sourceSha = ReadString(args, "--source-sha", "unrecorded");
        var sourceConfigHash = Hash(JsonSerializer.Serialize(config, Json));
        var strata = new Dictionary<string, List<EncounterSample>>(StringComparer.Ordinal);
        var stopwatch = Stopwatch.StartNew();
        var rawPath = Path.Combine(output, "encounters.jsonl");
        var decks = heroes.ToDictionary(hero => hero, hero => CreateDecks(config, hero));
        var manifest = new
        {
            SchemaVersion = 1, Kind = "actual_domain_encounter_simulation", SourceSha = sourceSha,
            ConfigVersion = config.Version, SamplesPerStratum = samples, SeedStart = seedStart,
            DomainAssemblySha256 = HashFile(typeof(BattleRoom).Assembly.Location),
            SimulatorAssemblySha256 = HashFile(typeof(CombatExperience).Assembly.Location),
            PreviewAudit = "first_three_legal_actions_per_encounter",
            SeedBlocks = Enumerable.Range(0, 3).Select(block => new { Block = block,
                Seeds = Enumerable.Range(seedStart, samples).Where((_, i) => i % 3 == block).ToArray() }),
            PrimarySampleFloorMet = samples >= 1_000, CutoffSeconds = limit, ActionIntervalSeconds = .4,
            WeaponLevel = weaponLevel, Candidate = candidateKind,
            SourceConfigSha256 = sourceConfigHash,
            CandidateWhitelist = candidateKind == "class-passives" ? groups :
                new[] { candidateKind.StartsWith("elite-e4-", StringComparison.Ordinal) ? "E4" : "O6" }, SingleFactorOnly = true,
            FirstWindupScope = "Only the first positive intent windup of each O6 monster; subsequent windups and attack intervals unchanged; 100ms tick resolution",
            StrategyPolicy = "baseline_all_hand spends immediately; basic/build wait for three cards or two core cards above 25% HP, then score legal visible subsets",
            RunIdentity = new { SeedStart = seedStart, Samples = samples, Candidate = candidateKind, WeaponLevel = weaponLevel },
            Scope = "Synthetic encounter entry, not a legal full expedition route or network capacity proof",
            Outcomes = new[] { "Victory", "Death", "Censored", "Error" },
            ProductionDefaults = config.Numerics, CandidateActivation = false,
            Strategies = strategies, Groups = groups, Decks = decks.SelectMany(pair => pair.Value.Select(deck => new
            {
                Hero = pair.Key.ToString(), deck.Key, CardIds = deck.Value,
                Level = 0, Ownership = "one enabled codex copy per selected card",
                Budget = new { Rarity = Budget(config, deck.Value).Rarity, UnlockCost = Budget(config, deck.Value).UnlockCost },
                Sha256 = Hash(JsonSerializer.Serialize(deck.Value, Json))
            }))
        };
        File.WriteAllText(Path.Combine(output, "manifest.json"), JsonSerializer.Serialize(manifest, PrettyJson));
        using (var raw = new StreamWriter(rawPath, false, new UTF8Encoding(false)))
        {
            foreach (var hero in heroes)
            foreach (var deck in decks[hero])
            foreach (var group in groups)
            foreach (var strategy in strategies)
            foreach (var candidate in new[] { false, true })
            {
                var profile = candidate ? candidateKind switch
                {
                    "outer-o6-hp085" => group == "O6" ? "TargetedO6Hp085" : "BaselinePairedControl",
                    "outer-o6-hp095" => group == "O6" ? "TargetedO6Hp095" : "BaselinePairedControl",
                    "outer-o6-hp090" => group == "O6" ? "TargetedO6Hp090" : "BaselinePairedControl",
                    "outer-o6-interval110" => group == "O6" ? "TargetedO6Interval110" : "BaselinePairedControl",
                    "outer-o6-windup025" => group == "O6" ? "TargetedO6Windup025" : "BaselinePairedControl",
                    "outer-o6-windup050" => group == "O6" ? "TargetedO6Windup050" : "BaselinePairedControl",
                    "elite-e4-hp095" => group == "E4" ? "TargetedE4Hp095" : "BaselinePairedControl",
                    "elite-e4-hp090" => group == "E4" ? "TargetedE4Hp090" : "BaselinePairedControl",
                    _ => hero switch { HeroClass.Mage => "CoreCardsSpent", HeroClass.Guardian => "FractionalRemainder", _ => "BaselinePairedControl" }
                } : "Baseline";
                var key = $"{hero}/{deck.Key}/{group}/{strategy}/{profile}";
                var rows = new List<EncounterSample>(samples);
                strata.Add(key, rows);
                for (var index = 0; index < samples; index++)
                {
                    var seed = seedStart + index;
                    var rules = candidate && candidateKind == "class-passives" ? config.Numerics with
                    {
                        CardsSpentDraw = hero == HeroClass.Mage,
                        FractionalGuardian = hero == HeroClass.Guardian
                    } : config.Numerics;
                    var row = Simulate(config, catalog, hero, deck.Key, deck.Value, group, strategy,
                        profile, rules, seed, index % 3, limit, weaponLevel);
                    rows.Add(row);
                    raw.WriteLine(JsonSerializer.Serialize(row, Json));
                }
                raw.Flush();
                Console.WriteLine($"{key}: {rows.Count} seeds, wins={rows.Count(row => row.Outcome == "Victory")}, censored={rows.Count(row => row.Outcome == "Censored")}, errors={rows.Count(row => row.Outcome == "Error")}");
            }
        }
        var summary = new
        {
            SchemaVersion = 1, config.Version, SourceSha = sourceSha, ElapsedSeconds = stopwatch.Elapsed.TotalSeconds,
            RawSha256 = HashFile(rawPath), Total = strata.Values.Sum(rows => rows.Count),
            ErrorCount = strata.Values.Sum(rows => rows.Count(row => row.Outcome == "Error")),
            CandidateActivation = false, HumanExperienceVerified = false,
            Strata = strata.Select(pair => Summarize(pair.Key, pair.Value)).ToArray(),
            PairedComparisons = strata.Where(pair => pair.Key.EndsWith("/Baseline", StringComparison.Ordinal))
                .Select(pair => Compare(pair.Key, pair.Value,
                    strata.Single(other => other.Key.StartsWith(pair.Key[..^"Baseline".Length], StringComparison.Ordinal) && other.Key != pair.Key).Value)).ToArray()
        };
        if (Hash(JsonSerializer.Serialize(config, Json)) != sourceConfigHash)
            throw new InvalidOperationException("Isolated experiment mutated source configuration.");
        File.WriteAllText(Path.Combine(output, "summary.json"), JsonSerializer.Serialize(summary, PrettyJson));
        return summary.ErrorCount == 0 ? 0 : 1;
    }

    internal static Dictionary<string, string[]> CreateDecks(GameConfigCatalog config, HeroClass hero)
    {
        var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", _ => "GUA" };
        var current = Enumerable.Range(1, 13).Select(i => $"C{i:D2}")
            .Concat(Enumerable.Range(1, 7).Select(i => $"{prefix}-{i:D2}")).ToArray();
        ValidateDeck(config, hero, current);
        var result = new Dictionary<string, string[]> { ["default"] = current };
        var desired = hero switch { HeroClass.Mage => CardElement.Fire, HeroClass.Priest => CardElement.Water, _ => CardElement.Earth };
        // A one-card theme swap uses identical rarity and unlock cost. It never
        // adds copies, levels, equipment, rare budgets or cross-class cards.
        foreach (var old in current)
        {
            var definition = config.Cards.Single(card => card.CardId == old);
            if (definition.Effect.Element == desired) continue;
            var replacement = config.Cards.Where(card => card.Enabled && card.IsCodex &&
                card.MonsterType is null && (card.HeroClass is null || card.HeroClass == hero) &&
                !current.Contains(card.CardId) && card.Rarity == definition.Rarity &&
                card.UnlockCost == definition.UnlockCost && card.Effect.Element == desired)
                .OrderBy(card => card.CardId, StringComparer.Ordinal).FirstOrDefault();
            if (replacement is null) continue;
            var themed = current.Select(id => id == old ? replacement.CardId : id).ToArray();
            PairedDeckBudget.Validate(config,hero,current,themed);
            ValidateDeck(config, hero, themed);
            if (Budget(config, current) != Budget(config, themed)) throw new InvalidOperationException("Deck budgets differ.");
            result.Add("theme_single_swap", themed);
            break;
        }
        return result;
    }

    internal static (int Rarity, int UnlockCost) Budget(GameConfigCatalog config, string[] deck) =>
        (deck.Sum(id => config.Cards.Single(card => card.CardId == id).Rarity),
         deck.Sum(id => config.Cards.Single(card => card.CardId == id).UnlockCost));

    internal static void ValidateDeck(GameConfigCatalog config, HeroClass hero, string[] deck)
    {
        var owned = config.Cards.Where(card => card.Enabled && card.IsCodex && card.MonsterType is null)
            .ToDictionary(card => card.CardId, card => new OwnedCard(card.CardId, card.HeroClass,
                (CardRarity)card.Rarity, 1, false), StringComparer.Ordinal);
        DeckRules.Validate(hero, deck, owned);
    }

    internal static EncounterSample Simulate(GameConfigCatalog config, CombatCardCatalog catalog,
        HeroClass hero, string deckName, string[] deck, string group, string strategy, string profile,
        NumericalRules rules, int seed, int block, int limit, int weaponLevel, bool marginalAudit = false)
    {
        var row = new EncounterSample(seed, block, hero.ToString(), deckName, group, strategy, profile);
        try
        {
            var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, seed, rules);
            var player = room.AddPlayer(new BattleRoomPlayerSetup(Guid.NewGuid(), hero, deck, null, WeaponLevel: weaponLevel));
            row.WeaponLevel = weaponLevel;
            var map = ChaosMapGenerator.Generate(seed, 1).Capture();
            var layer = group == "BOSS" ? ChaosMapLayer.Core :
                group.StartsWith('E') || group.StartsWith('M') ? ChaosMapLayer.Middle : ChaosMapLayer.Outer;
            var cell = group == "BOSS" ? map.Cells.Single(c => c.IsBoss) : map.Cells.First(c => c.Layer == layer && !c.IsBoss);
            var encounter = cell with { MonsterGroupId = group, IsBoss = group == "BOSS", HasSpring = false };
            room.InitializeMap(ChaosMapState.Restore(map with
            {
                Cells = map.Cells.Select(c => c.Position == cell.Position ? encounter : c).ToArray(),
                SpawnPositions = new[] { cell.Position }
            }));
            if (profile is "TargetedO6Hp085" or "TargetedO6Hp095" or "TargetedO6Hp090" or "TargetedO6Interval110" or
                "TargetedE4Hp095" or "TargetedE4Hp090")
            {
                var hpScale = profile switch
                { "TargetedO6Hp095" or "TargetedE4Hp095" => .95, "TargetedO6Hp090" or "TargetedE4Hp090" => .90, _ => .85 };
                var snapshot = room.Capture();
                room = BattleRoom.Restore(snapshot with
                {
                    Players = snapshot.Players.Select(value => value with
                    {
                        Pve = value.Pve! with
                        {
                            Monsters = value.Pve.Monsters.Select(monster => profile != "TargetedO6Interval110"
                                ? monster with { MaximumHp = (int)Math.Floor(monster.MaximumHp * hpScale), Hp = (int)Math.Floor(monster.Hp * hpScale) }
                                : monster with { AttackInterval = TimeSpan.FromTicks((long)(monster.AttackInterval.Ticks * 1.10)) }).ToArray()
                        }
                    }).ToArray()
                }, catalog, seed);
                player = room.GetPlayer(player.PlayerId);
            }
            var pve = player.Pve!;
            var openingHp = pve.Monsters.Sum(monster => monster.Hp);
            row.OpeningEnemyHp = openingHp;
            row.OpeningEnemyShield = pve.Monsters.Sum(monster => monster.Shield);
            row.EnemyNonHpInputSha256 = Hash(JsonSerializer.Serialize(pve.Monsters.Select(monster => new
            { monster.MonsterId, monster.Shield, monster.AttackInterval, monster.ElementalAmplification, monster.Intents }), Json));
            var damage = 0;
            var effectiveAt = -1d;
            var tick = TimeSpan.FromMilliseconds(100);
            var firstWindupExtra = profile switch
            {
                "TargetedO6Windup025" => TimeSpan.FromMilliseconds(250),
                "TargetedO6Windup050" => TimeSpan.FromMilliseconds(500),
                _ => TimeSpan.Zero
            };
            var extendedMonsters = new HashSet<string>(StringComparer.Ordinal);
            for (var step = 0; step < limit * 10 && player.Phase == RoomPlayerPhase.Pve; step++)
            {
                var time = step / 10d;
                row.ObservedSeconds = time;
                var beforeHand = player.Combat.Deck.Hand.Select(card => card.InstanceId).ToHashSet();
                if (player.Combat.Deck.Hand.Count == 0) row.NoCardsSeconds += .1;
                if (player.Combat.StunRemaining > TimeSpan.Zero) row.PlayerStunSeconds += .1;
                if (player.Combat.DrawBlockRemaining > TimeSpan.Zero) row.DrawBlockedSeconds += .1;
                if (player.Combat.Deck.Hand.Count == CombatDeck.HandLimit) row.FullHandSeconds += .1;
                if (pve.Monsters.Any(monster => !monster.IsDead && monster.StunRemaining > TimeSpan.Zero)) row.TargetControlSeconds += .1;
                if (player.Combat.StunRemaining == TimeSpan.Zero && player.Combat.Deck.Hand.Count > 0)
                {
                    row.LegalOpportunitySeconds += .1;
                    if (step % 4 == 0 && !ShouldHold(catalog, player.Combat, strategy))
                    {
                        var target = pve.Monsters.First(monster => !monster.IsDead);
                        var selected = Select(catalog, player.Combat, target, strategy);
                        var ids = selected.Select(card => card.InstanceId).ToArray();
                        var definitions = selected.Select(card => catalog.Get(card.CardId, card.Level, card.ElementOverride)).ToArray();
                        var draft = CombatResolver.Resolve(definitions, player.Combat, target.ElementalResistance);
                        // Scalar preview parity is verified against the real play. The
                        // preview must leave even persisted RNG and remainder unchanged.
                        var now = DateTimeOffset.UnixEpoch.AddSeconds(time);
                        CombatResolution? preview = null;
                        if (row.PreviewParityChecks < 3)
                        {
                            var before = JsonSerializer.Serialize(room.Capture(), Json);
                            preview = room.PreviewCards(player.PlayerId, pve.BattleId, target.MonsterId, ids, room.Revision, now);
                            if (before != JsonSerializer.Serialize(room.Capture(), Json)) throw new InvalidOperationException("Preview mutated the room.");
                        }
                        var controlBefore = target.StunRemaining.Ticks;
                        var result = room.PlayCards(player.PlayerId, pve.BattleId, target.MonsterId, ids, room.Revision, now);
                        if (marginalAudit)
                        {
                            row.RequestedImmediateCards += result.ImmediateDraw;
                            row.RequestedHeal += draft.Heal;
                            row.RequestedShield += draft.Shield;
                            row.RequestedControlTicks += TimeSpan.FromSeconds(definitions.Max(card => card.Effect.StunSeconds)).Ticks;
                            row.ConvertedControlTicks += draft.Stun.Ticks;
                            row.AdmittedControlTicks += (long)Math.Round(result.StunSeconds * TimeSpan.TicksPerSecond);
                            if (!target.IsDead) row.AddedAliveControlUnionTicks += Math.Max(0, target.StunRemaining.Ticks - controlBefore);
                        }
                        if (preview is not null && (preview.Damage != result.Damage || preview.HpDamage != result.HpDamage ||
                            preview.ShieldDamage != result.ShieldDamage || preview.Heal != result.Heal ||
                            preview.ShieldGain != result.ShieldGain || preview.CoreElement != result.CoreElement ||
                            preview.ImmediateDraw != result.ImmediateDraw || preview.StunSeconds != result.StunSeconds))
                            throw new InvalidOperationException("Preview and actual resolution differ.");
                        if (preview is not null) row.PreviewParityChecks++;
                        row.Actions++;
                        row.CardsSpent += ids.Length;
                        var remainingOldHand = beforeHand.Except(ids).ToHashSet();
                        var drawn = player.Combat.Deck.Hand.Count(card => !remainingOldHand.Contains(card.InstanceId));
                        row.ImmediateCardsDrawn += drawn;
                        row.EffectiveHeal += result.Heal;
                        row.EffectiveShield += result.ShieldGain;
                        row.HealOverflow += Math.Max(0, draft.Heal - result.Heal);
                        row.ShieldOverflow += Math.Max(0, draft.Shield - result.ShieldGain);
                        damage += result.HpDamage + result.ShieldDamage;
                        var effective = result.HpDamage + result.ShieldDamage + result.Heal + result.ShieldGain + drawn > 0;
                        if (effective)
                        {
                            row.EffectiveActions++;
                            if (row.FirstEffectiveSeconds is null) row.FirstEffectiveSeconds = time;
                            if (effectiveAt >= 0) row.LongestEffectiveGapSeconds = Math.Max(row.LongestEffectiveGapSeconds, time - effectiveAt);
                            effectiveAt = time;
                        }
                        else row.ZeroEffectiveActions++;
                    }
                }
                if (ShouldHold(catalog, player.Combat, strategy)) row.StrategyHoldSeconds += .1;
                if (time <= 10) row.Damage10 = damage;
                if (time <= 30) row.Damage30 = damage;
                if (time <= 60) row.Damage60 = damage;
                var handBeforeAdvance = player.Combat.Deck.Hand.Select(card => card.InstanceId).ToHashSet();
                if (marginalAudit && player.Phase == RoomPlayerPhase.Pve)
                foreach (var monster in pve.Monsters.Where(monster => !monster.IsDead))
                {
                    var observed = Math.Min(tick.Ticks, monster.StunRemaining.Ticks);
                    row.ObservedAliveControlUnionTicks += observed;
                    row.ControlUnionTicksByTarget[monster.MonsterId] = row.ControlUnionTicksByTarget.GetValueOrDefault(monster.MonsterId) + observed;
                }
                room.Advance(tick, DateTimeOffset.UnixEpoch.AddSeconds(time + .1));
                if (firstWindupExtra > TimeSpan.Zero)
                foreach (var monster in pve.Monsters)
                {
                    if (monster.WindupRemaining <= TimeSpan.Zero || !extendedMonsters.Add(monster.MonsterId)) continue;
                    var state = monster.Capture();
                    monster.SetRuntimeState(state.IntentIndex, state.IntervalProgress, state.WindupRemaining + firstWindupExtra,
                        state.IsCharging, state.EmpowerBonus, state.StunRemaining,
                        state.StatusRemaining.ToDictionary(value => value.Key, value => value.Remaining, StringComparer.Ordinal),
                        state.BossPhase, state.BossPhaseTransitionPending);
                    row.FirstWindupExtensions++;
                    row.FirstWindupIntentIndexes.Add(state.IntentIndex);
                }
                row.NaturalCardsDrawn += player.Combat.Deck.Hand.Count(card => !handBeforeAdvance.Contains(card.InstanceId));
                row.ObservedSeconds = time + .1;
            }
            row.TotalEffectiveDamage = damage;
            row.FirstWindupExtraMilliseconds = firstWindupExtra.TotalMilliseconds;
            row.RemainingMonsterHp = pve.Monsters.Sum(monster => monster.Hp);
            row.MonsterHpProgressRatio = (openingHp - row.RemainingMonsterHp) / (double)openingHp;
            row.RemainingPlayerHp = player.Combat.Hp;
            row.FinalPoolSize = player.Combat.Deck.Hand.Count + player.Combat.Deck.Library.Count + player.Combat.Deck.Discard.Count;
            row.Outcome = player.Combat.IsDead ? "Death" : pve.IsCleared ? "Victory" : "Censored";
            if (row.ObservedSeconds < 10) row.Damage10 = damage;
            if (row.ObservedSeconds < 30) row.Damage30 = damage;
            if (row.ObservedSeconds < 60) row.Damage60 = damage;
            row.LongestEffectiveGapSeconds = Math.Max(row.LongestEffectiveGapSeconds, row.ObservedSeconds - Math.Max(0, effectiveAt));
        }
        catch (Exception exception)
        {
            row.Outcome = "Error";
            row.Error = exception.GetType().Name + ": " + exception.Message;
        }
        return row;
    }

    private static CombatCardInstance[] Select(CombatCardCatalog catalog, PlayerCombatState player,
        MonsterCombatState target, string strategy)
    {
        var hand = player.Deck.Hand;
        if (strategy == "baseline_all_hand") return hand.ToArray();
        // Keep hand order for basic. Build evaluates visible element-first orders
        // and subsets, without reading the library, future intent or random state.
        var candidates = new List<CombatCardInstance[]>();
        for (var mask = 1; mask < 1 << hand.Count; mask++)
        {
            var subset = hand.Where((_, i) => (mask & 1 << i) != 0).ToArray();
            candidates.Add(subset);
            if (strategy == "build")
            foreach (var element in subset.Select(card => catalog.Get(card.CardId, card.Level, card.ElementOverride).Effect.Element).Distinct())
                candidates.Add(subset.OrderByDescending(card => catalog.Get(card.CardId, card.Level, card.ElementOverride).Effect.Element == element).ToArray());
        }
        return candidates.Select(cards =>
        {
            var draft = CombatResolver.Resolve(cards.Select(card => catalog.Get(card.CardId, card.Level, card.ElementOverride)).ToArray(), player, target.ElementalResistance);
            var appliedDamage = Math.Min(target.Hp + target.Shield, draft.Damage);
            var score = appliedDamage + Math.Min(player.EffectiveMaximumHp - player.Hp, draft.Heal) * .8 +
                Math.Min(player.MaximumHp / 2 - player.Shield, draft.Shield) * .5 +
                draft.Stun.TotalSeconds * .7 + draft.ImmediateDraw * 2 + draft.DrawCharge * 2 - cards.Length * .25;
            return (cards, score);
        }).OrderByDescending(value => value.score).ThenBy(value => value.cards.Length).First().cards;
    }

    private static bool ShouldHold(CombatCardCatalog catalog, PlayerCombatState player, string strategy)
    {
        if (strategy == "baseline_all_hand" || player.Hp <= player.MaximumHp / 4 || player.Deck.Hand.Count >= 3) return false;
        var groups = player.Deck.Hand.Select(card => catalog.Get(card.CardId, card.Level, card.ElementOverride).Effect)
            .Where(effect => effect.ElementalDamage > 0 && effect.SecondaryElementalDamage == 0 && effect.Element != CardElement.None)
            .GroupBy(effect => effect.Element);
        return !groups.Any(group => group.Count() >= 2);
    }

    private static object Summarize(string key, List<EncounterSample> rows) => new
    {
        Stratum = key, N = rows.Count,
        Outcomes = rows.GroupBy(row => row.Outcome).ToDictionary(group => group.Key, group => group.Count()),
        VictoryRateWilson95 = Wilson(rows.Count(row => row.Outcome == "Victory"), rows.Count),
        ObservedSecondsAllOutcomes = Quantiles(rows.Select(row => row.ObservedSeconds)),
        VictorySeconds = Quantiles(rows.Where(row => row.Outcome == "Victory").Select(row => row.ObservedSeconds)),
        Damage10 = Quantiles(rows.Select(row => (double)row.Damage10)),
        Damage30 = Quantiles(rows.Select(row => (double)row.Damage30)),
        Damage60 = Quantiles(rows.Select(row => (double)row.Damage60)),
        LongestEffectiveGap = Quantiles(rows.Select(row => row.LongestEffectiveGapSeconds)),
        NoCardsRatio = rows.Sum(row => row.NoCardsSeconds) / Math.Max(.1, rows.Sum(row => row.ObservedSeconds)),
        ZeroEffectiveActions = rows.Sum(row => row.ZeroEffectiveActions),
        PreviewParityChecks = rows.Sum(row => row.PreviewParityChecks),
        HealOverflow = rows.Sum(row => row.HealOverflow), ShieldOverflow = rows.Sum(row => row.ShieldOverflow),
        SeedBlockOutcomes = rows.GroupBy(row => row.SeedBlock).Select(block => new
        { Block = block.Key, N = block.Count(), Wins = block.Count(row => row.Outcome == "Victory"),
            Deaths = block.Count(row => row.Outcome == "Death"), Censored = block.Count(row => row.Outcome == "Censored") })
    };

    private static object Compare(string key, List<EncounterSample> baseline, List<EncounterSample> candidate)
    {
        if (!baseline.Select(row => row.Seed).SequenceEqual(candidate.Select(row => row.Seed)))
            throw new InvalidOperationException("Paired seed mismatch.");
        var deltas = baseline.Zip(candidate, (left, right) => right.Damage60 - (double)left.Damage60).ToArray();
        var random = new Random(20260930);
        var boot = Enumerable.Range(0, 1_000).Select(_ => Enumerable.Range(0, deltas.Length)
            .Average(_ => deltas[random.Next(deltas.Length)])).Order().ToArray();
        return new { Baseline = key, Candidate = candidate[0].Profile, N = deltas.Length,
            MeanDamage60Delta = deltas.Average(), SeedBootstrapMeanDelta95 = new[] { boot[24], boot[974] },
            BaselineWins = baseline.Count(row => row.Outcome == "Victory"), CandidateWins = candidate.Count(row => row.Outcome == "Victory"),
            RetainProductionDefaults = true };
    }

    private static object? Quantiles(IEnumerable<double> values)
    {
        var sorted = values.Order().ToArray();
        if (sorted.Length == 0) return null;
        double At(double q) => sorted[(int)Math.Round((sorted.Length - 1) * q)];
        return new { N = sorted.Length, P10 = At(.1), P50 = At(.5), P90 = At(.9), P95 = At(.95), P99 = At(.99), Mean = sorted.Average() };
    }

    private static double[] Wilson(int successes, int n)
    {
        var p = successes / (double)n;
        const double z = 1.95996398454;
        var denominator = 1 + z * z / n;
        var center = (p + z * z / (2 * n)) / denominator;
        var margin = z * Math.Sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator;
        return new[] { center - margin, center + margin };
    }

    private static int ReadInt(string[] args, string name, int fallback) => int.Parse(ReadString(args, name, fallback.ToString(System.Globalization.CultureInfo.InvariantCulture)), System.Globalization.CultureInfo.InvariantCulture);
    private static string ReadString(string[] args, string name, string fallback)
    {
        var index = Array.IndexOf(args, name);
        if (index < 0) return fallback;
        if (index + 1 >= args.Length) throw new ArgumentException($"Missing value for {name}.");
        return args[index + 1];
    }
    private static string Hash(string text) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant();
    private static string HashFile(string path)
    {
        using var file = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant();
    }
}

internal sealed class EncounterSample(int seed, int seedBlock, string hero, string deck, string group, string strategy, string profile)
{
    public int Seed { get; } = seed;
    public int SeedBlock { get; } = seedBlock;
    public string Hero { get; } = hero;
    public string Deck { get; } = deck;
    public string Group { get; } = group;
    public string Strategy { get; } = strategy;
    public string Profile { get; } = profile;
    public int WeaponLevel { get; set; }
    public int OpeningEnemyHp { get; set; }
    public int OpeningEnemyShield { get; set; }
    public string? EnemyNonHpInputSha256 { get; set; }
    public string Outcome { get; set; } = "Censored";
    public string? Error { get; set; }
    public double ObservedSeconds { get; set; }
    public double? FirstEffectiveSeconds { get; set; }
    public double LongestEffectiveGapSeconds { get; set; }
    public double NoCardsSeconds { get; set; }
    public double PlayerStunSeconds { get; set; }
    public double DrawBlockedSeconds { get; set; }
    public double FullHandSeconds { get; set; }
    public double TargetControlSeconds { get; set; }
    public double LegalOpportunitySeconds { get; set; }
    public double StrategyHoldSeconds { get; set; }
    public int Actions { get; set; }
    public int EffectiveActions { get; set; }
    public int ZeroEffectiveActions { get; set; }
    public int CardsSpent { get; set; }
    public int ImmediateCardsDrawn { get; set; }
    public int RequestedImmediateCards { get; set; }
    public int RequestedHeal { get; set; }
    public int RequestedShield { get; set; }
    public long RequestedControlTicks { get; set; }
    public long ConvertedControlTicks { get; set; }
    public long AdmittedControlTicks { get; set; }
    public long AddedAliveControlUnionTicks { get; set; }
    public long ObservedAliveControlUnionTicks { get; set; }
    public Dictionary<string, long> ControlUnionTicksByTarget { get; } = new(StringComparer.Ordinal);
    public int NaturalCardsDrawn { get; set; }
    public int EffectiveHeal { get; set; }
    public int EffectiveShield { get; set; }
    public int HealOverflow { get; set; }
    public int ShieldOverflow { get; set; }
    public int Damage10 { get; set; }
    public int Damage30 { get; set; }
    public int Damage60 { get; set; }
    public int TotalEffectiveDamage { get; set; }
    public int RemainingMonsterHp { get; set; }
    public double MonsterHpProgressRatio { get; set; }
    public int RemainingPlayerHp { get; set; }
    public int FinalPoolSize { get; set; }
    public int PreviewParityChecks { get; set; }
    public int FirstWindupExtensions { get; set; }
    public double FirstWindupExtraMilliseconds { get; set; }
    public List<int> FirstWindupIntentIndexes { get; } = [];
}
