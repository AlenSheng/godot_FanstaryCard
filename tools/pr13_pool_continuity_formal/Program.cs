using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

// Formal natural route matrix, with actual typed codec/router/RoomActor intents.
// Real PVE, no artificial HP/map/offer/pile changes; default rule stays off.
if (args.SequenceEqual(new[] { "--help" }))
{
    Console.WriteLine("--output DIRECTORY --source SHA --hero Mage|Priest|Guardian --seed-start N --seeds 1000 [--development-smoke]");
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
if (smoke ? seedCount is < 1 or > 16 : seedCount != 1000 || !new[] { 479001, 480001, 481001 }.Contains(seedStart))
    throw new ArgumentException("Formal budget is exactly 1000 paired seeds in one frozen block.");
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
                var effect = catalog.Get(candidate.CardId, candidate.Level, candidate.ElementOverride).Effect;
                var accept = effect.Element == focus && effect.ElementalDamage > 0;
                Guid? replacement = null;
                if (accept && player.MonsterPool.Active.Count >= capacity)
                {
                    var weakest = player.MonsterPool.Active.OrderBy(c => catalog.Get(c.CardId, c.Level, c.ElementOverride).Effect.ElementalDamage).First();
                    if (effect.ElementalDamage > catalog.Get(weakest.CardId, weakest.Level, weakest.ElementOverride).Effect.ElementalDamage) replacement = weakest.InstanceId;
                    else accept = false;
                }
                var poolBefore = player.MonsterPool.Capture();
                var handBefore = player.Combat.Deck.Hand.ToArray();
                var choiceWatch = Stopwatch.StartNew();
                var captureVector = seed == seedStart && row.MonsterChoices < 3;
                var beforeChoice = captureVector ? await session.SnapshotFrame() : [];
                await session.Route("monster.choose", new MonsterCardChooseCommandPayload(candidate.InstanceId, accept, replacement));
                row.ChoiceCommandWallSeconds += choiceWatch.Elapsed.TotalSeconds;
                row.NativeCommandCalls++;
                row.MonsterChoices++;
                if (accept) row.Accepted++; else row.Skipped++;
                if (replacement is not null) row.Replaced++;
                // Natural offers must carry a real native kill source. Never Offer().
                Require(poolBefore.GrantedSources.Count > 0, "Candidate lacks native provenance.");
                Require(player.Combat.Deck.Hand.SequenceEqual(handBefore.Where(c => c.InstanceId != replacement)), "Choice created a compensating draw.");
                Emit("monster-choice", new { candidate, accept, replacement, grantedSources = poolBefore.GrantedSources,
                    controlledWaitSeconds = 2, measuredDecisionWallSeconds = choiceWatch.Elapsed.TotalSeconds });
                if (captureVector)
                {
                    var vector = new { source, hero = hero.ToString(), seed, capacity, ownerId = player.PlayerId, roomId = room.RoomId,
                        matchId = session.MatchId, candidateId = candidate.InstanceId, accept, replacement, beforeWire = Convert.ToBase64String(beforeChoice),
                        commandWire = Convert.ToBase64String(session.LastCommand), afterWires = session.LastResponses.Select(Convert.ToBase64String).ToArray() };
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
            var selectedReward = player.Combat.Hp <= player.Combat.MaximumHp / 2 || player.Inventory.FreeSlots == 0 ? heal : fragments;
            await session.Route("reward.choice.claim", new RewardChoiceClaimCommandPayload((selectedReward ?? heal ?? choice.Options[0]).OptionId));
            row.NativeCommandCalls++;
            Audit();
        }
        else if (player.Phase == RoomPlayerPhase.ActionBar && !extractionRequested)
        {
            var map = room.GetMapProjection(player.PlayerId); // Public cells and legal moves only.
            if (map.CurrentCell.HasEvacuation && (visited.Count >= 3 || player.Combat.Hp <= player.Combat.MaximumHp / 2))
            {
                await session.Route("action.extract", new ActionExtractCommandPayload());
                extractionRequested = true;
                row.NativeCommandCalls++;
            }
            else if (map.LegalMoves.Count > 0)
            {
                var boss = map.Cells.Single(c => c.IsBoss).Position;
                var next = map.LegalMoves.OrderBy(p => visited.Contains(p))
                    .ThenBy(p => p.ManhattanDistance(boss)).ThenBy(p => p.Row).ThenBy(p => p.Column).First();
                await session.Route("room.move", new RoomMoveCommandPayload(next.Row, next.Column));
                visited.Add(next);
                row.NativeCommandCalls++;
            }
        }
        if (room.Elapsed.TotalSeconds < 1800) room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch + room.Elapsed);
        Audit();
    }
    row.Outcome = player.Phase is RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted ? player.Phase.ToString() : "ObservationBudgetCensored";
    row.SimulatedSeconds = room.Elapsed.TotalSeconds;
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
    statisticalDecisionPending = true, wholeTaskAccepted = false }, json) + "\n");

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
    public async Task Route(string type, object payload)
    {
        var command = new ClientCommand(type, $"continuity:{_seed}:{_capacity}:{RequestCount}", _room.Revision, payload, _room.RoomId, MatchId);
        LastCommand = RealtimeProtobufCodec.EncodeClient(command);
        var decoded = RealtimeProtobufCodec.DecodeClient(LastCommand);
        if (decoded.Type != type || decoded.RequestId != command.RequestId || decoded.RoomId != _room.RoomId || decoded.MatchId != MatchId)
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
    public string TraceSha256() => Convert.ToHexString(_trace.GetCurrentHash()).ToLowerInvariant();
    public async ValueTask DisposeAsync() { _trace.Dispose(); await _registry.DisposeAsync(); }
}
