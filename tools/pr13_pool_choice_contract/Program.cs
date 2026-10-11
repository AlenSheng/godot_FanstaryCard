using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

// Natural choice contract coverage supplement, with actual typed codec/router/RoomActor intents.
// Real PVE, no artificial HP/map/offer/pile changes; default rule stays off.
if (args.SequenceEqual(new[] { "--help" }))
{
    Console.WriteLine("--output DIRECTORY --source SHA --hero Mage|Priest|Guardian --seed-start N --seeds 128 [--development-smoke]");
    return;
}
if (!OperatingSystem.IsLinux()) throw new InvalidOperationException("Cloud Linux execution required.");
var smoke = args.Contains("--development-smoke");
var arguments = args.Where(a => a != "--development-smoke").ToArray();
if (arguments.Length != 10) throw new ArgumentException("Five named arguments required; see --help.");
var options = Enumerable.Range(0, 5).ToDictionary(i => arguments[i * 2], i => arguments[i * 2 + 1]);
var source = options["--source"];
if (source.Length != 40 || source.Any(c => !Uri.IsHexDigit(c))) throw new ArgumentException("Exact source SHA required.");
var heroSelected = Enum.Parse<HeroClass>(options["--hero"]);
if (heroSelected is not (HeroClass.Mage or HeroClass.Priest or HeroClass.Guardian)) throw new ArgumentException("Unknown hero.");
var seedStart = int.Parse(options["--seed-start"]);
var seedCount = int.Parse(options["--seeds"]);
if (smoke ? seedCount is < 1 or > 16 : seedCount != 128 || seedStart != 484001)
    throw new ArgumentException("Contract budget is exactly 128 paired seeds in the frozen block 484001.");
var directory = Path.GetFullPath(options["--output"]);
Directory.CreateDirectory(directory);
if (File.Exists(Path.Combine(directory, "routes.jsonl"))) throw new InvalidOperationException("Preserve previous attempt.");
var config = GameConfigCatalog.Current;
if (config.Numerics.OptionalMonsterPool) throw new InvalidOperationException("Official default must remain disabled.");
var catalog = CombatCardCatalog.CreatePrototype();
var seeds = Enumerable.Range(seedStart, seedCount);
var profiles = new[] { 0, 3, 5, 8 };
var json = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
var rows = new List<RouteRow>();
var capturedOperations = new HashSet<string>(StringComparer.Ordinal);
using var events = new StreamWriter(Path.Combine(directory, "events.jsonl"), false, new UTF8Encoding(false));
foreach (var hero in new[] { heroSelected })
foreach (var seed in seeds)
foreach (var capacity in profiles)
{
    var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", _ => "GUA" };
    var cards = Enumerable.Range(1, 13).Select(i => $"C{i:D2}")
        .Concat(Enumerable.Range(1, 7).Select(i => $"{prefix}-{i:D2}")).ToArray();
    var owned = config.Cards.Where(c => c.Enabled && c.IsCodex && c.MonsterType is null)
        .ToDictionary(c => c.CardId, c => new OwnedCard(c.CardId, c.HeroClass, (CardRarity)c.Rarity, 1, false));
    DeckRules.Validate(hero, cards, owned);
    var rules = capacity == 0 ? config.Numerics : config.Numerics with { OptionalMonsterPool = true, MonsterCapacity = capacity };
    var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, seed, rules);
    var player = room.AddPlayer(new BattleRoomPlayerSetup(Guid.NewGuid(), hero, cards, null, IsBot: false));
    room.InitializeMap(ChaosMapGenerator.Generate(seed, 1));
    await using var session = new TypedSession(room, player.PlayerId, seed, capacity);
    var initial = AuditCards(player);
    var originalIds = initial.Select(c => c.InstanceId).ToHashSet();
    var focus = cards.Select(id => catalog.Get(id).Effect).Where(e => e.ElementalDamage > 0 && e.Element != CardElement.None)
        .GroupBy(e => e.Element).OrderByDescending(g => g.Count()).ThenBy(g => g.Key).First().Key;
    var visited = new HashSet<MapPosition> { player.Position!.Value };
    var usedSprings = new HashSet<MapPosition>();
    var knownExits = new HashSet<MapPosition>();
    var row = new RouteRow(hero.ToString(), seed, capacity, source, config.Version, focus.ToString());
    var initialInventory = player.Inventory.Items.ToArray();
    Require(initialInventory.Length == 0, "Unregistered starting asset.");
    var watch = Stopwatch.StartNew();
    var cpuBefore = Process.GetCurrentProcess().TotalProcessorTime;
    var extractionRequested = false;
    var hiddenNegativeDone = false;
    // Identical 1800 simulated second budget. Continuing Guardian fights are
    // censored observations, not errors or evidence that balance must be changed.
    for (var step = 0; step < 18000 && room.Elapsed.TotalSeconds < 1800 && player.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted); step++)
    {
        row.SimulatedSeconds = room.Elapsed.TotalSeconds;
        var now = DateTimeOffset.UnixEpoch + room.Elapsed;
        if (player.Phase == RoomPlayerPhase.Pve && player.Pve is { } pve)
        {
            if (player.Combat.Deck.Hand.Count == 0) row.NoHandSeconds += .1;
            var visible = VisibleHand.Read(player.Combat.Deck.Hand, catalog, focus);
            if (visible.CoreCount >= 2) row.CoreAvailableSeconds += .1;
            if (!hiddenNegativeDone)
            {
                // Change only hidden library order on a detached restored room.
                // Policy must see exactly the same visible input and decision.
                var snapshot = room.Capture();
                var altered = snapshot with { Players = snapshot.Players.Select(p => p with
                { Combat = p.Combat with { Deck = p.Combat.Deck with { Library = p.Combat.Deck.Library.Reverse().ToArray() } } }).ToArray() };
                var restored = BattleRoom.Restore(altered, catalog, seed).GetPlayer(player.PlayerId);
                var other = VisibleHand.Read(restored.Combat.Deck.Hand, catalog, focus);
                Require(JsonSerializer.Serialize(visible, json) == JsonSerializer.Serialize(other, json), "Hidden order leaked into visible input.");
                Require(visible.Select().SequenceEqual(other.Select()), "Hidden order changed the current visible decision.");
                try { RequireAllowedInformation(["hand", "library-order"]); throw new InvalidOperationException("Leaky policy was accepted."); }
                catch (InformationLeakRejected) { row.HiddenOrderNegativeRejected = true; }
                hiddenNegativeDone = true;
            }
            if (step % 4 == 0 && player.Combat.StunRemaining == TimeSpan.Zero && visible.Cards.Count > 0 &&
                (visible.Cards.Count >= 3 || visible.CoreCount >= 2 || player.Combat.Hp <= player.Combat.MaximumHp / 4))
            {
                var target = pve.Monsters.FirstOrDefault(m => !m.IsDead);
                if (target is not null)
                {
                    var ids = visible.Select();
                    row.Casts++;
                    if (visible.CoreCount >= 2) row.CoreCasts++;
                    var alive = pve.Monsters.Where(m => !m.IsDead).Select(m => m.MonsterId).ToHashSet();
                    await session.Route("battle.play_cards", new BattlePlayCardsCommandPayload(pve.BattleId, target.MonsterId, ids));
                    row.NativeCommandCalls++;
                    foreach (var monster in pve.Monsters.Where(m => m.IsDead && alive.Contains(m.MonsterId)))
                    {
                        row.Kills++;
                        Emit("native-kill", new { battleId = pve.BattleId, monster.MonsterId });
                    }
                    Audit();
                }
            }
        }
        else if (player.Phase == RoomPlayerPhase.Choice && player.RewardChoice is { } choice)
        {
            row.RewardChoices++;
            foreach (var candidate in player.MonsterPool.Pending.ToArray())
            {
                // Public candidate/pool and choice counter only. This policy exercises
                // contracts; it is not the earlier strength/dilution comparison policy.
                var full = player.MonsterPool.Active.Count >= capacity;
                var skipFirstAssigned = (seed - seedStart) % 2 == 0; // Frozen external coverage scenario, not hidden game information.
                var accept = !(skipFirstAssigned && row.MonsterChoices == 0) && (!full || row.Replaced == 0 || row.MonsterChoices % 2 == 0);
                Guid? replacement = accept && full ? player.MonsterPool.Active[0].InstanceId : null;
                var operation = accept ? replacement is null ? "accept" : "replace" : full ? "skip-full" : player.MonsterPool.Active.Count == 0 ? "skip-empty" : "skip-partial";
                var resourcesBefore = NonCardState(room.CapturePlayer(player.PlayerId), json);
                var deckBefore = player.Combat.Deck.Capture();
                var cardsBefore = AuditCards(player);
                var businessBefore = JsonSerializer.Serialize(room.Capture(), json);
                await session.ExpectForeignCandidateRejected(candidate.InstanceId);
                var foreignCommand = session.LastRejectedCommand.ToArray();
                var foreignResponses = session.LastRejectedResponses.Select(x => x.ToArray()).ToArray();
                Require(JsonSerializer.Serialize(room.Capture(), json) == businessBefore, "Foreign submission mutated native room.");
                var poolBefore = player.MonsterPool.Capture();
                var handBefore = player.Combat.Deck.Hand.ToArray();
                var choiceWatch = Stopwatch.StartNew();
                var captureVector = !capturedOperations.Contains($"{capacity}:{operation}");
                var beforeChoice = captureVector ? await session.SnapshotFrame() : [];
                await session.Route("monster.choose", new MonsterCardChooseCommandPayload(candidate.InstanceId, accept, replacement));
                row.ChoiceCommandWallSeconds += choiceWatch.Elapsed.TotalSeconds;
                row.NativeCommandCalls++;
                var commandOriginal = session.LastCommand.ToArray();
                var firstResponses = session.LastResponses.Select(x => x.ToArray()).ToArray();
                var afterChoice = room.CapturePlayer(player.PlayerId);
                Require(NonCardState(afterChoice, json) == resourcesBefore, "Choice changed HP/status/inventory/resources.");
                var afterCards = AuditCards(player);
                Require(player.MonsterPool.Pending.All(c => c.InstanceId != candidate.InstanceId), "Decided candidate still pending.");
                Require(player.MonsterPool.Active.Count == poolBefore.Active.Count + (accept && replacement is null ? 1 : 0), "Active pool count changed incorrectly.");
                if (accept)
                {
                    Require(player.Combat.Deck.Discard.Count(c => c.InstanceId == candidate.InstanceId) == 1, "Accepted card did not enter discard once.");
                    Require(afterCards.Select(c => c.InstanceId).ToHashSet().SetEquals(cardsBefore.Where(c => c.InstanceId != replacement).Select(c => c.InstanceId).Append(candidate.InstanceId)), "Choice removed or duplicated another card.");
                }
                else
                {
                    Require(JsonSerializer.Serialize(deckBefore, json) == JsonSerializer.Serialize(player.Combat.Deck.Capture(), json), "Skip changed a pile.");
                    Require(poolBefore.Active.SequenceEqual(player.MonsterPool.Active), "Skip changed active pool.");
                }
                var stateAfterFirst = JsonSerializer.Serialize(room.Capture(), json);
                await session.Route("monster.choose", new MonsterCardChooseCommandPayload(candidate.InstanceId, accept, replacement), commandOriginal);
                row.NativeCommandCalls++;
                Require(JsonSerializer.Serialize(room.Capture(), json) == stateAfterFirst, "Same request replay changed native room.");
                await session.ExpectConflictRejected(commandOriginal, candidate.InstanceId, !accept, replacement);
                Require(JsonSerializer.Serialize(room.Capture(), json) == stateAfterFirst, "Conflicting replay changed native room.");
                row.MonsterChoices++;
                if (accept) row.Accepted++; else row.Skipped++;
                if (replacement is not null) row.Replaced++;
                // Natural offers must carry a real native kill source. Never Offer().
                Require(poolBefore.GrantedSources.Count > 0, "Candidate lacks native provenance.");
                Require(player.Combat.Deck.Hand.SequenceEqual(handBefore.Where(c => c.InstanceId != replacement)), "Choice created a compensating draw.");
                Emit("monster-choice", new { candidate, accept, replacement, grantedSources = poolBefore.GrantedSources,
                    operation, beforeDeck = deckBefore, afterDeck = player.Combat.Deck.Capture(),
                    resourcesBefore, resourcesAfter = NonCardState(afterChoice, json),
                    activeBefore = poolBefore.Active, activeAfter = player.MonsterPool.Active,
                    candidateNativeBattleId = player.Pve?.BattleId,
                    actualNativeDeadMonsters = player.Pve?.Monsters.Where(m => m.IsDead).Select(m => m.MonsterId).ToArray(),
                    sameRequestReplayPreserved = true, conflictingReplayRejected = true, foreignOwnerRejected = true,
                    foreignCommandWire = Convert.ToBase64String(foreignCommand), foreignResponseWires = foreignResponses.Select(Convert.ToBase64String).ToArray(),
                    conflictCommandWire = Convert.ToBase64String(session.LastRejectedCommand), conflictResponseWires = session.LastRejectedResponses.Select(Convert.ToBase64String).ToArray(),
                    firstCommandWire = Convert.ToBase64String(commandOriginal), firstResponseWires = firstResponses.Select(Convert.ToBase64String).ToArray(),
                    replacedPile = replacement is null ? "none" : deckBefore.Hand.Any(c => c.InstanceId == replacement) ? "hand" : deckBefore.Library.Any(c => c.InstanceId == replacement) ? "library" : "discard",
                    controlledWaitSeconds = 2, measuredDecisionWallSeconds = choiceWatch.Elapsed.TotalSeconds });
                if (captureVector)
                {
                    capturedOperations.Add($"{capacity}:{operation}");
                    var vector = new { source, hero = hero.ToString(), seed, capacity, ownerId = player.PlayerId, roomId = room.RoomId,
                        matchId = session.MatchId, operation, candidateId = candidate.InstanceId, accept, replacement, beforeWire = Convert.ToBase64String(beforeChoice),
                        commandWire = Convert.ToBase64String(commandOriginal), afterWires = firstResponses.Select(Convert.ToBase64String).ToArray() };
                    File.AppendAllText(Path.Combine(directory, "render-vectors.jsonl"), JsonSerializer.Serialize(vector, json) + "\n");
                }
                Audit();
                // A declared controlled player input delay, not a human timing result.
                var waitStarted = room.Elapsed;
                for (var t = 0; t < 20 && room.Elapsed.TotalSeconds < 1800; t++) room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch + room.Elapsed);
                row.ControlledMonsterChoiceWaitSeconds += (room.Elapsed - waitStarted).TotalSeconds;
            }
            var heal = choice.Options.FirstOrDefault(o => o.Kind == RewardChoiceKind.ImmediateHeal);
            var fragments = choice.Options.FirstOrDefault(o => o.Kind == RewardChoiceKind.EquipmentFragments);
            var selectedReward = player.Combat.Hp < player.Combat.MaximumHp || player.Inventory.FreeSlots == 0 ? heal : fragments;
            await session.Route("reward.choice.claim", new RewardChoiceClaimCommandPayload((selectedReward ?? heal ?? choice.Options[0]).OptionId));
            row.NativeCommandCalls++;
            Audit();
        }
        else if (player.Phase == RoomPlayerPhase.ActionBar && !extractionRequested)
        {
            var map = room.GetMapProjection(player.PlayerId); // Public cells and legal moves only.
            if (map.CurrentCell.HasEvacuation) knownExits.Add(map.Self);
            var current = map.Cells.Single(c => c.Position == map.Self);
            var newCell = PublicFirstHop(map, p => !visited.Contains(p));
            var spring = player.Combat.Hp <= player.Combat.MaximumHp / 2
                ? PublicFirstHop(map, p => map.Cells.Single(c => c.Position == p).HasSpring && !usedSprings.Contains(p)) : null;
            if (current.HasSpring && !map.CurrentCell.SpringConsumed && player.Combat.Hp < player.Combat.MaximumHp)
            {
                await session.Route("action.spring", new ActionSpringCommandPayload());
                row.NativeCommandCalls++; row.SpringUses++;
                for (var tick = 0; tick < 13 && room.Elapsed.TotalSeconds < 1800; tick++)
                { room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch + room.Elapsed); Audit(); }
                var springCompleted = room.GetMapProjection(player.PlayerId).CurrentCell.SpringConsumed;
                if (!springCompleted)
                {
                    Require(room.Elapsed.TotalSeconds >= 1800, "Legal spring did not complete before the available observation budget.");
                    row.CensorReason = "SpringChannelAtFrozenBudget";
                }
                else usedSprings.Add(map.Self);
            }
            else if (map.CurrentCell.HasEvacuation && (capacity == 0 ? visited.Count >= 3 : row.Replaced > 0 && row.Skipped > 0 || newCell is null))
            {
                await session.Route("action.extract", new ActionExtractCommandPayload());
                extractionRequested = true; row.NativeCommandCalls++;
            }
            else
            {
                var next = spring ?? newCell ?? PublicFirstHop(map, knownExits.Contains);
                if (next is null)
                { row.CensorReason = "NoFurtherPublicExplorationOrKnownReachableExit"; break; }
                Require(map.LegalMoves.Contains(next.Value), "Public route planner selected an illegal first hop.");
                await session.Route("room.move", new RoomMoveCommandPayload(next.Value.Row, next.Value.Column));
                visited.Add(next.Value); row.NativeCommandCalls++;
            }
        }
        if (room.Elapsed.TotalSeconds < 1800) room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch + room.Elapsed);
        Audit();
    }
    row.Outcome = player.Phase is RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted ? player.Phase.ToString() : "ObservationBudgetCensored";
    row.SimulatedSeconds = room.Elapsed.TotalSeconds;
    row.FinalPhase = player.Phase.ToString();
    row.FinalAliveMonsters = player.Pve?.Monsters.Count(m => !m.IsDead) ?? 0;
    if (row.Outcome == "ObservationBudgetCensored" && row.CensorReason.Length == 0) row.CensorReason = player.Phase == RoomPlayerPhase.Pve ? "ContinuingPveAtFrozenBudget" : "NonPveAtFrozenBudget";
    row.RemainingHp = player.Combat.Hp;
    row.CellsVisited = visited.Count;
    row.WallSeconds = watch.Elapsed.TotalSeconds;
    row.CpuSeconds = (Process.GetCurrentProcess().TotalProcessorTime - cpuBefore).TotalSeconds;
    row.PeakWorkingSetBytes = Process.GetCurrentProcess().PeakWorkingSet64;
    row.TypedRequestCount = session.RequestCount;
    row.TypedRequestBytes = session.RequestBytes;
    row.TypedResponseCount = session.ResponseCount;
    row.TypedResponseBytes = session.ResponseBytes;
    row.RouterTraceSha256 = session.TraceSha256();
    row.CollectorSnapshotRequests = session.CollectorSnapshotRequests;
    row.WireTypes = session.RequestTypes;
    row.FinalInventory = player.Inventory.Items.Select(i => new EconomicItem(i.Kind.ToString(), i.ItemId, i.Quantity, i.IsSafe)).ToArray();
    row.RetainedEconomicItems = player.Inventory.Items.Where(i => player.Phase == RoomPlayerPhase.Extracted || i.IsSafe).Select(i => new EconomicItem(i.Kind.ToString(), i.ItemId, i.Quantity, i.IsSafe)).ToArray();
    Require(row.NativeCommandCalls == row.TypedRequestCount, "Intent/router request counts differ.");
    rows.Add(row);
    Console.WriteLine(JsonSerializer.Serialize(row, json));
    events.Flush();

    void Emit(string kind, object data) => events.WriteLine(JsonSerializer.Serialize(new { source, hero = hero.ToString(), seed, capacity, kind, simulatedSeconds = room.Elapsed.TotalSeconds, data }, json));
    void Audit()
    {
        var all = AuditCards(player);
        Require(all.Select(c => c.InstanceId).Distinct().Count() == all.Length, "Instance duplicated across piles.");
        Require(originalIds.IsSubsetOf(all.Select(c => c.InstanceId).ToHashSet()), "Base instance was removed.");
        if (capacity > 0)
        {
            Require(player.MonsterPool.Active.Count <= capacity, "Optional cap exceeded.");
            Require(all.Length == 20 + player.MonsterPool.Active.Count, "Unexpected optional card conservation.");
            Require(player.MonsterPool.Pending.All(c => all.All(a => a.InstanceId != c.InstanceId)), "Pending instance already entered a pile.");
        }
        row.InstanceConservationChecks++;
    }
}
File.WriteAllText(Path.Combine(directory, "routes.jsonl"), string.Join('\n', rows.Select(r => JsonSerializer.Serialize(r, json))) + "\n", new UTF8Encoding(false));
Require(rows.Count == seedCount * 4 && rows.All(r => r.HiddenOrderNegativeRejected && r.InstanceConservationChecks > 0), "Incomplete formal matrix.");
File.WriteAllText(Path.Combine(directory, "result.json"), JsonSerializer.Serialize(new { ok = true, source, hero = heroSelected.ToString(), seedStart, seedCount,
    routes = rows.Count, profiles, developmentSmoke = smoke, naturalCombat = true, typedRouterIntents = true,
    productionChanged = false, controlledChoiceWaitIsHumanTiming = false, requestTrafficIsLiveNetwork = false,
    contractCoverageSupplement = true, previous36000RouteStatisticsUnchanged = true, fullCoverageNotInferredFromProcessExit = true, capturedOperations = capturedOperations.Order().ToArray(), wholeTaskAccepted = false }, json) + "\n");

static MapPosition? PublicFirstHop(ChaosMapProjection map, Func<MapPosition, bool> target)
{
    // Traverse only the published positions/layers. Monster groups, hidden
    // library/discard order and internal room map are never policy inputs.
    var cells = map.Cells.ToDictionary(c => c.Position); var seen = new HashSet<MapPosition> { map.Self };
    var queue = new Queue<(MapPosition Position, MapPosition First)>();
    foreach (var p in map.LegalMoves.OrderBy(p => cells[p].Layer).ThenBy(p => p.Row).ThenBy(p => p.Column))
        if (seen.Add(p)) queue.Enqueue((p,p));
    while (queue.TryDequeue(out var item))
    {
        if (target(item.Position)) return item.First;
        var p = item.Position;
        foreach (var next in new MapPosition[] { new(p.Row-1,p.Column),new(p.Row+1,p.Column),new(p.Row,p.Column-1),new(p.Row,p.Column+1) }
            .Where(cells.ContainsKey).Where(n => cells[n].Layer >= cells[p].Layer).OrderBy(n => cells[n].Layer).ThenBy(n => n.Row).ThenBy(n => n.Column))
            if (seen.Add(next)) queue.Enqueue((next,item.First));
    }
    return null;
}
static string NonCardState(RoomPlayerSnapshot snapshot, JsonSerializerOptions options)
{
    var node = JsonSerializer.SerializeToNode(snapshot, options)!.AsObject();
    node.Remove("monsterPool");
    node["combat"]!.AsObject().Remove("deck");
    return node.ToJsonString(options);
}
static CombatCardInstance[] AuditCards(RoomPlayerState player)
{
    var snapshot = player.Combat.Deck.Capture(); // Audit only: never passed to policy.
    return snapshot.Hand.Concat(snapshot.Library).Concat(snapshot.Discard).ToArray();
}
static void Require(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
static void RequireAllowedInformation(string[] fields)
{
    if (fields.Any(f => f is not ("hand" or "base-deck-composition" or "visible-active-pool" or "candidate" or "public-map" or "hp"))) throw new InformationLeakRejected();
}
sealed class InformationLeakRejected : Exception { }
sealed record VisibleCard(Guid InstanceId, bool Core);
sealed record VisibleHand(IReadOnlyList<VisibleCard> Cards)
{
    public int CoreCount => Cards.Count(c => c.Core);
    public Guid[] Select() => Cards.Select(c => c.InstanceId).ToArray(); // Preserve server hand order.
    public static VisibleHand Read(IReadOnlyList<CombatCardInstance> hand, CombatCardCatalog catalog, CardElement focus) =>
        new(hand.Select(c => new VisibleCard(c.InstanceId, catalog.Get(c.CardId, c.Level, c.ElementOverride).Effect.Element == focus &&
            catalog.Get(c.CardId, c.Level, c.ElementOverride).Effect.ElementalDamage > 0)).ToArray());
}
sealed class RouteRow(string hero, int seed, int capacity, string source, string configVersion, string focus)
{
    public string Hero { get; } = hero;
    public int Seed { get; } = seed;
    public int Capacity { get; } = capacity;
    public string Source { get; } = source;
    public string ConfigVersion { get; } = configVersion;
    public string Focus { get; } = focus;
    public string Outcome { get; set; } = "Pending";
    public double SimulatedSeconds { get; set; }
    public double NoHandSeconds { get; set; }
    public double CoreAvailableSeconds { get; set; }
    public int CoreCasts { get; set; }
    public int Casts { get; set; }
    public int Kills { get; set; }
    public int MonsterChoices { get; set; }
    public int RewardChoices { get; set; }
    public int Accepted { get; set; }
    public int Skipped { get; set; }
    public int Replaced { get; set; }
    public int NativeCommandCalls { get; set; }
    public int InstanceConservationChecks { get; set; }
    public int RemainingHp { get; set; }
    public int SpringUses { get; set; }
    public string FinalPhase { get; set; } = "";
    public int FinalAliveMonsters { get; set; }
    public string CensorReason { get; set; } = "";
    public int CellsVisited { get; set; }
    public double ControlledMonsterChoiceWaitSeconds { get; set; }
    public double ChoiceCommandWallSeconds { get; set; }
    public double WallSeconds { get; set; }
    public double CpuSeconds { get; set; }
    public long PeakWorkingSetBytes { get; set; }
    public bool HiddenOrderNegativeRejected { get; set; }
    public int TypedRequestCount { get; set; }
    public long TypedRequestBytes { get; set; }
    public int TypedResponseCount { get; set; }
    public long TypedResponseBytes { get; set; }
    public string RouterTraceSha256 { get; set; } = "";
    public int CollectorSnapshotRequests { get; set; }
    public IReadOnlyDictionary<string, int> WireTypes { get; set; } = new Dictionary<string, int>();
    public EconomicItem[] FinalInventory { get; set; } = [];
    public EconomicItem[] RetainedEconomicItems { get; set; } = [];
}

sealed record EconomicItem(string Kind, string ItemId, int Quantity, bool IsSafe);
sealed class RoomClock(BattleRoom room) : TimeProvider
{
    public override DateTimeOffset GetUtcNow() => DateTimeOffset.UnixEpoch + room.Elapsed;
}
sealed class TypedSession : IAsyncDisposable
{
    private readonly BattleRoom _room;
    private readonly Guid _owner;
    private readonly int _seed;
    private readonly int _capacity;
    private readonly RoomRegistry _registry;
    private readonly RealtimeEventStore _events;
    private readonly RealtimeCommandRouter _router;
    private readonly RoomClock _clock;
    private readonly IncrementalHash _trace = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
    public Guid MatchId { get; } = Guid.NewGuid();
    public int RequestCount { get; private set; }
    public long RequestBytes { get; private set; }
    public int ResponseCount { get; private set; }
    public long ResponseBytes { get; private set; }
    public Dictionary<string, int> RequestTypes { get; } = new();
    public int CollectorSnapshotRequests { get; private set; }
    public byte[] LastCommand { get; private set; } = [];
    public byte[][] LastResponses { get; private set; } = [];
    public byte[] LastRejectedCommand { get; private set; } = [];
    public byte[][] LastRejectedResponses { get; private set; } = [];
    public TypedSession(BattleRoom room, Guid owner, int seed, int capacity)
    {
        _room = room; _owner = owner; _seed = seed; _capacity = capacity;
        _clock = new(room); _events = new(_clock); _registry = new(_clock);
        _registry.Register(room, MatchId, startTicker: false);
        _router = new(_events, _clock, _registry);
    }
    public async Task<byte[]> SnapshotFrame()
    {
        // Instrumentation uses the real public typed snapshot command. These
        // first-seed collector calls are separate from gameplay intent counts.
        var command = new ClientCommand("room.snapshot.read", $"collector:{_seed}:{_capacity}:{CollectorSnapshotRequests}", _room.Revision,
            new RoomSnapshotCommandPayload(), _room.RoomId, MatchId);
        var wire = RealtimeProtobufCodec.EncodeClient(command);
        var events = await _router.RouteAsync(PlayerProfile.Create(_owner, "ContinuityFormal", _clock.GetUtcNow()),
            RealtimeProtobufCodec.DecodeClient(wire), "continuity-collector", CancellationToken.None);
        CollectorSnapshotRequests++;
        return RealtimeProtobufCodec.EncodeServer(events.Single(e => e.Type == "room.snapshot"));
    }
    public async Task Route(string type, object payload, byte[]? replay = null)
    {
        var command = new ClientCommand(type, $"continuity:{_seed}:{_capacity}:{RequestCount}", _room.Revision, payload, _room.RoomId, MatchId);
        LastCommand = replay ?? RealtimeProtobufCodec.EncodeClient(command);
        var decoded = RealtimeProtobufCodec.DecodeClient(LastCommand);
        if (decoded.Type != type || (replay is null && decoded.RequestId != command.RequestId) || decoded.RoomId != _room.RoomId || decoded.MatchId != MatchId)
            throw new InvalidOperationException("Typed command context changed.");
        var responses = await _router.RouteAsync(PlayerProfile.Create(_owner, "ContinuityFormal", _clock.GetUtcNow()), decoded, "continuity-native", CancellationToken.None);
        if (responses.Count == 0 || responses.Any(e => e.Type.StartsWith("error.", StringComparison.Ordinal) || e.Type == "room.command_cancelled"))
            throw new InvalidOperationException("Natural legal intent rejected: " + JsonSerializer.Serialize(responses));
        LastResponses = responses.Select(RealtimeProtobufCodec.EncodeServer).ToArray();
        foreach (var bytes in LastResponses) { _ = RealtimeProtobufCodec.DecodeServer(bytes); _trace.AppendData(bytes); }
        _trace.AppendData(LastCommand); RequestCount++; RequestBytes += LastCommand.Length;
        ResponseCount += LastResponses.Length; ResponseBytes += LastResponses.Sum(b => (long)b.Length);
        RequestTypes[type] = RequestTypes.GetValueOrDefault(type) + 1;
    }
    public async Task ExpectForeignCandidateRejected(Guid candidate)
    {
        var payload = new MonsterCardChooseCommandPayload(candidate, true, null);
        await RejectionProbe(Guid.NewGuid(), new ClientCommand("monster.choose", $"foreign:{_seed}:{RequestCount}", _room.Revision, payload, _room.RoomId, MatchId));
    }
    public async Task ExpectConflictRejected(byte[] original, Guid candidate, bool accept, Guid? replacement)
    {
        var previous = RealtimeProtobufCodec.DecodeClient(original);
        await RejectionProbe(_owner, new ClientCommand("monster.choose", previous.RequestId, previous.ExpectedRevision,
            new MonsterCardChooseCommandPayload(candidate, accept, replacement), _room.RoomId, MatchId));
    }
    private async Task RejectionProbe(Guid requester, ClientCommand command)
    {
        var wire = RealtimeProtobufCodec.EncodeClient(command);
        LastRejectedCommand = wire.ToArray();
        var responses = await _router.RouteAsync(PlayerProfile.Create(requester, "ChoiceProbe", _clock.GetUtcNow()),
            RealtimeProtobufCodec.DecodeClient(wire), "contract-negative", CancellationToken.None);
        LastRejectedResponses = responses.Select(RealtimeProtobufCodec.EncodeServer).ToArray();
        if (!responses.Any(e => e.Type.StartsWith("error.", StringComparison.Ordinal) || e.Type == "room.command_cancelled"))
            throw new InvalidOperationException("Invalid monster choice was accepted.");
    }
    public string TraceSha256() => Convert.ToHexString(_trace.GetCurrentHash()).ToLowerInvariant();
    public async ValueTask DisposeAsync() { _trace.Dispose(); await _registry.DisposeAsync(); }
}
