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

if (args.SequenceEqual(new[] { "--help" }))
{
    Console.WriteLine("--output DIRECTORY --source SHA --hero Mage|Priest|Guardian --seed-start 484001 --seeds 128 [--development-smoke]");
    return;
}
if (!OperatingSystem.IsLinux()) throw new InvalidOperationException("Tencent Linux execution required.");
var smoke = args.Contains("--development-smoke");
var named = args.Where(x => x != "--development-smoke").ToArray();
Check(named.Length == 10, "Five named arguments required.");
var options = Enumerable.Range(0, 5).ToDictionary(i => named[2 * i], i => named[2 * i + 1]);
var hero = Enum.Parse<HeroClass>(options["--hero"]);
Check(hero is HeroClass.Mage or HeroClass.Priest or HeroClass.Guardian, "Unknown hero.");
var source = options["--source"]; Check(source.Length == 40 && source.All(Uri.IsHexDigit), "Exact source SHA required.");
var start = int.Parse(options["--seed-start"]); var count = int.Parse(options["--seeds"]);
Check(start == 484001 && (smoke ? count is >= 1 and <= 16 : count == 128), "Fixed paired seed grid required.");
var directory = Path.GetFullPath(options["--output"]); Directory.CreateDirectory(directory);
Check(!File.Exists(Path.Combine(directory, "events.jsonl")), "Preserve existing attempt.");
var config = GameConfigCatalog.Current; Check(!config.Numerics.OptionalMonsterPool, "Official default must remain off.");
var catalog = CombatCardCatalog.CreatePrototype();
var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", _ => "GUA" };
var deck = Enumerable.Range(1, 13).Select(i => $"C{i:D2}").Concat(Enumerable.Range(1, 7).Select(i => $"{prefix}-{i:D2}")).ToArray();
var owned = config.Cards.Where(c => c.Enabled && c.IsCodex && c.MonsterType is null).ToDictionary(c => c.CardId, c => new OwnedCard(c.CardId, c.HeroClass, (CardRarity)c.Rarity, 1, false));
DeckRules.Validate(hero, deck, owned);
var json = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
using var events = new StreamWriter(Path.Combine(directory, "events.jsonl"), false, new UTF8Encoding(false));
var rows = new List<object>();
foreach (var seed in Enumerable.Range(start, count))
foreach (var capacity in new[] { 0, 3, 5, 8 })
{
    var room = new BattleRoom(Id($"room:{hero}:{seed}"), config.Version, catalog, seed, capacity == 0 ? config.Numerics : config.Numerics with { OptionalMonsterPool = true, MonsterCapacity = capacity });
    var players = new[] { Id($"A:{hero}:{seed}"), Id($"B:{hero}:{seed}") };
    foreach (var id in players) room.AddPlayer(new BattleRoomPlayerSetup(id, hero, deck, null, IsBot: false));
    room.InitializeMap(ChaosMapGenerator.Generate(seed, players.Length));
    var originals = players.ToDictionary(id => id, id => Cards(room.GetPlayer(id)).Select(c => c.InstanceId).ToHashSet());
    var spawns = players.Select(id => room.GetMapProjection(id).Self).ToArray();
    var rendezvous = room.GetMapProjection(players[0]).Cells.OrderBy(c => spawns.Max(p => p.ManhattanDistance(c.Position))).ThenBy(c => spawns.Sum(p => p.ManhattanDistance(c.Position))).ThenBy(c => c.Layer).ThenBy(c => c.Position.Row).ThenBy(c => c.Position.Column).First().Position;
    var session = new Session(room, players, Id($"match:{hero}:{seed}:{capacity}"));
    var knownForeign = 0; var choices = 0; var pvp = 0; var restoredPvp = 0; var returnedPvp = 0; var terminalClean = 0; var audits = 0;
    var firstChoiceDone = capacity == 0; var terminalLogged = new HashSet<Guid>();
    var reason = "";
    try
    {
        for (var step = 0; step < 18000 && room.Elapsed.TotalSeconds < 1800; step++)
        {
            if (!firstChoiceDone && players.All(id => room.GetPlayer(id).Phase == RoomPlayerPhase.Choice && room.GetPlayer(id).MonsterPool.Pending.Count > 0))
            {
                foreach (var owner in players)
                {
                    var requester = players.Single(id => id != owner);
                    var candidate = room.GetPlayer(owner).MonsterPool.Pending[0];
                    var before = room.Capture(); var beforeBytes = JsonSerializer.Serialize(before, json);
                    var response = await session.Send(requester, "monster.choose", new MonsterCardChooseCommandPayload(candidate.InstanceId, true), allowRejected: true);
                    var rejection = response.Events.Single();
                    Check(rejection.Type == "error.command_rejected" && rejection.Payload is CommandRejectedEventPayload { Code: "COMMAND_REJECTED", Detail: "The monster candidate no longer exists." }, "Known eligible player rejection was not specifically candidate ownership.");
                    Check(JsonSerializer.Serialize(room.Capture(), json) == beforeBytes, "Foreign candidate changed the room.");
                    Emit("known-foreign-candidate", new { owner, requester, candidate, before, after = room.Capture(), response.Command, response.Responses, requesterOwnPending = room.GetPlayer(requester).MonsterPool.Pending.ToArray(), ownerSources = room.GetPlayer(owner).MonsterPool.Capture().GrantedSources });
                    knownForeign++;
                }
                firstChoiceDone = true;
            }
            foreach (var id in players)
            {
                var player = room.GetPlayer(id);
                if (player.Phase == RoomPlayerPhase.Pve && player.Pve is { } battle && step % 4 == 0 && player.Combat.StunRemaining == TimeSpan.Zero)
                {
                    var hand = player.Combat.Deck.Hand.ToArray();
                    if (hand.Length >= 3 || player.Combat.Hp <= player.Combat.MaximumHp / 4 && hand.Length > 0)
                    {
                        var target = battle.Monsters.FirstOrDefault(m => !m.IsDead);
                        if (target is not null)
                        {
                            var alive = battle.Monsters.Where(m => !m.IsDead).Select(m => m.MonsterId).ToHashSet();
                            await session.Send(id, "battle.play_cards", new BattlePlayCardsCommandPayload(battle.BattleId, target.MonsterId, hand.Select(c => c.InstanceId).ToArray()));
                            foreach (var monster in battle.Monsters.Where(m => m.IsDead && alive.Contains(m.MonsterId))) Emit("native-kill", new { owner = id, battleId = battle.BattleId, monster.MonsterId });
                        }
                    }
                }
                else if (player.Phase == RoomPlayerPhase.Choice && player.RewardChoice is { } reward && firstChoiceDone)
                {
                    foreach (var candidate in player.MonsterPool.Pending.ToArray())
                    {
                        var accept = player.MonsterPool.Active.Count < capacity;
                        var before = room.CapturePlayer(id);
                        var response = await session.Send(id, "monster.choose", new MonsterCardChooseCommandPayload(candidate.InstanceId, accept));
                        var after = room.CapturePlayer(id);
                        Check(player.Combat.Deck.Hand.SequenceEqual(before.Combat.Deck.Hand), "Choice created a compensating draw.");
                        if (accept) Check(player.Combat.Deck.Discard.Count(c => c.InstanceId == candidate.InstanceId) == 1, "Candidate did not enter discard exactly once.");
                        Emit("own-candidate-choice", new { owner = id, candidate, accept, before, after, response.Command, response.Responses }); choices++;
                    }
                    var healing = reward.Options.FirstOrDefault(o => o.Kind == RewardChoiceKind.ImmediateHeal);
                    await session.Send(id, "reward.choice.claim", new RewardChoiceClaimCommandPayload((healing ?? reward.Options[0]).OptionId));
                }
                else if (player.Phase == RoomPlayerPhase.ActionBar && firstChoiceDone)
                {
                    var map = room.GetMapProjection(id);
                    if (returnedPvp > 0)
                    {
                        if (map.CurrentCell.HasEvacuation)
                        { if (room.CapturePlayer(id).ExtractionRemaining is null) await session.Send(id, "action.extract", new ActionExtractCommandPayload()); }
                        else
                        {
                            var next = Hop(map, p => map.Cells.Any(c => c.Position == p && c.IsBoss));
                            if (next is not null)
                            {
                                var response = await session.Send(id, "room.move", new RoomMoveCommandPayload(next.Value.Row, next.Value.Column));
                                if (room.GetPlayer(id).Phase == RoomPlayerPhase.Pvp) { await HandleDuel(response); break; }
                            }
                        }
                    }
                    else if (map.Self != rendezvous)
                    {
                        var next = Hop(map, p => p == rendezvous);
                        if (next is null) { reason = "NoPublicPathToRendezvous"; break; }
                        var response = await session.Send(id, "room.move", new RoomMoveCommandPayload(next.Value.Row, next.Value.Column));
                        if (room.GetPlayer(id).Phase == RoomPlayerPhase.Pvp) { await HandleDuel(response); break; }
                    }
                }
            }
            foreach (var id in players)
            {
                var player = room.GetPlayer(id); var all = Cards(player);
                Check(all.Select(c => c.InstanceId).Distinct().Count() == all.Length && originals[id].IsSubsetOf(all.Select(c => c.InstanceId).ToHashSet()), "Base card or unique instance invariant failed.");
                if (capacity > 0) Check(all.Length == 20 + player.MonsterPool.Active.Count, "Pool and card total diverged.");
                if (player.Phase is RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted)
                { Check(player.MonsterPool.Active.Count == 0 && player.MonsterPool.Pending.Count == 0 && (capacity == 0 || all.Length == 20), "Terminal pool was not cleared."); if (terminalLogged.Add(id)) { terminalClean++; Emit("terminal-pool-cleared", new { owner = id, originalBaseInstances = originals[id], snapshot = room.CapturePlayer(id) }); } }
                audits++;
            }
            if (players.Any(id => room.GetPlayer(id).Phase == RoomPlayerPhase.Dead) && returnedPvp == 0) { reason = "NaturalDeathBeforePvp"; break; }
            if (players.All(id => room.GetPlayer(id).Phase is RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted)) { reason = "BothTerminal"; break; }
            if (reason.Length > 0) break;
            room.Advance(TimeSpan.FromMilliseconds(100), DateTimeOffset.UnixEpoch + room.Elapsed);
        }
        if (reason.Length == 0) reason = returnedPvp > 0 ? "PvpCompleteTerminalBudgetCensored" : "NaturalCombatOrRendezvousBudgetCensored";
        var row = new { hero = hero.ToString(), seed, capacity, source, players, rendezvous, simulatedSeconds = room.Elapsed.TotalSeconds, knownForeignProbes = knownForeign, ownChoices = choices, naturalPvpEntries = pvp, checkpointRestores = restoredPvp, mutualLeaveReturns = returnedPvp, terminalInvariantChecks = terminalClean, instanceAudits = audits, outcome = reason, finalPhases = players.Select(id => room.GetPlayer(id).Phase.ToString()).ToArray() };
        rows.Add(row); Console.WriteLine(JsonSerializer.Serialize(row, json));
    }
    finally { await session.DisposeAsync(); }
    async Task HandleDuel(Delivery response)
    {

                            var checkpoint = room.Capture(); var duel = checkpoint.Duels.Single();
                            Check(players.All(p => room.GetPlayer(p).Phase == RoomPlayerPhase.Pvp && room.GetPlayer(p).Position == room.GetPlayer(players[0]).Position), "Legal move did not pair the two natural players.");
                            Check(players.All(p => room.GetPlayer(p).MonsterPool.Active.Count > 0) || capacity == 0, "PVP entered without natural active pool.");
                            Emit("natural-pvp-entry", new { rendezvous, entryPosition = room.GetPlayer(players[0]).Position, response.Command, response.Responses, checkpoint }); pvp++;
                            var checkpointBytes = JsonSerializer.SerializeToUtf8Bytes(checkpoint, json);
                            var restored = BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(checkpointBytes, json)!, catalog, seed);
                            foreach (var p in players)
                            {
                                Check(JsonSerializer.Serialize(restored.GetPlayer(p).MonsterPool.Capture(), json) == JsonSerializer.Serialize(room.GetPlayer(p).MonsterPool.Capture(), json), "Checkpoint changed the pool.");
                                Check(JsonSerializer.Serialize(restored.GetPlayer(p).Combat.Deck.Capture(), json) == JsonSerializer.Serialize(room.GetPlayer(p).Combat.Deck.Capture(), json), "Checkpoint changed duel card instances.");
                            }
                            var nextNumber = session.NextNumber;
                            await session.DisposeAsync(); room = restored; session = new Session(room, players, session.MatchId, nextNumber); restoredPvp++;
                            Emit("actual-pvp-checkpoint-restored", new { checkpointSha256 = Convert.ToHexStringLower(SHA256.HashData(checkpointBytes)), before = checkpoint, after = room.Capture() });
                            await session.Send(duel.FirstPlayerId, "duel.leave", new DuelLeaveCommandPayload(duel.DuelId));
                            var leave = await session.Send(duel.LatePlayerId, "duel.leave", new DuelLeaveCommandPayload(duel.DuelId));
                            Check(room.Capture().Duels.Count == 0, "Mutual leave did not end the actual duel.");
                            foreach (var p in players)
                            {
                                var frozen = (p == duel.FirstPlayerId ? duel.FirstFrozen : duel.LateFrozen) ?? throw new InvalidOperationException("Missing frozen duel participant.");
                                Check(room.GetPlayer(p).Phase == frozen.Phase && JsonSerializer.Serialize(room.GetPlayer(p).Combat.Capture(), json) == JsonSerializer.Serialize(frozen.Combat, json), "Return changed the frozen PVE combat state.");
                                Check(JsonSerializer.Serialize(room.GetPlayer(p).MonsterPool.Capture(), json) == JsonSerializer.Serialize(checkpoint.Players.Single(x => x.PlayerId == p).MonsterPool, json), "Return changed active pool.");
                            }
                            Emit("pvp-mutual-leave-return", new { before = checkpoint, after = room.Capture(), leave.Command, leave.Responses }); returnedPvp++;
                            
    }
    void Emit(string kind, object data) { events.WriteLine(JsonSerializer.Serialize(new { hero = hero.ToString(), seed, capacity, source, kind, data }, json)); events.Flush(); }
}
File.WriteAllText(Path.Combine(directory, "routes.jsonl"), string.Join('\n', rows.Select(r => JsonSerializer.Serialize(r, json))) + "\n");
File.WriteAllText(Path.Combine(directory, "result.json"), JsonSerializer.Serialize(new { ok = true, hero = hero.ToString(), source, routes = rows.Count, naturalCombat = true, typedRouterIntents = true, directActorDuelControls = false, productionChanged = false, missingBranchesNotAccepted = true, developmentSmoke = smoke }, json) + "\n");

static void Check(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
static Guid Id(string value) => new(SHA256.HashData(Encoding.UTF8.GetBytes(value)).AsSpan(0, 16));
static CombatCardInstance[] Cards(RoomPlayerState p) { var d = p.Combat.Deck.Capture(); return d.Hand.Concat(d.Library).Concat(d.Discard).ToArray(); }
static MapPosition? Hop(ChaosMapProjection map, Func<MapPosition, bool> target)
{
    var cells = map.Cells.ToDictionary(c => c.Position); var seen = new HashSet<MapPosition> { map.Self }; var queue = new Queue<(MapPosition Position, MapPosition First)>();
    foreach (var p in map.LegalMoves.OrderBy(p => p.Row).ThenBy(p => p.Column)) if (seen.Add(p)) queue.Enqueue((p, p));
    while (queue.TryDequeue(out var item))
    {
        if (target(item.Position)) return item.First;
        var p = item.Position;
        foreach (var n in new MapPosition[] { new(p.Row - 1, p.Column), new(p.Row + 1, p.Column), new(p.Row, p.Column - 1), new(p.Row, p.Column + 1) }.Where(cells.ContainsKey).Where(n => cells[n].Layer >= cells[p].Layer).OrderBy(n => n.Row).ThenBy(n => n.Column)) if (seen.Add(n)) queue.Enqueue((n, item.First));
    }
    return null;
}
sealed class Clock(BattleRoom room) : TimeProvider { public override DateTimeOffset GetUtcNow() => DateTimeOffset.UnixEpoch + room.Elapsed; }
sealed record Delivery(byte[] Command, byte[][] Responses, IReadOnlyList<ServerEvent> Events);
sealed class Session : IAsyncDisposable
{
    private readonly BattleRoom _room; private readonly HashSet<Guid> _players; private readonly RoomRegistry _registry; private readonly RealtimeCommandRouter _router; private readonly Clock _clock; private int _number;
    public Guid MatchId { get; }
    public int NextNumber => _number;
    public Session(BattleRoom room, IEnumerable<Guid> players, Guid matchId, int nextNumber = 0) { _room = room; _players = players.ToHashSet(); MatchId = matchId; _number = nextNumber; _clock = new(room); _registry = new(_clock); _registry.Register(room, MatchId, startTicker: false); _router = new(new RealtimeEventStore(_clock), _clock, _registry); }
    public async Task<Delivery> Send(Guid owner, string type, object payload, bool allowRejected = false)
    {
        if (!_players.Contains(owner)) throw new InvalidOperationException("Probe requester must be a known real player.");
        var command = RealtimeProtobufCodec.EncodeClient(new ClientCommand(type, $"dual:{owner:N}:{_number++}", _room.Revision, payload, _room.RoomId, MatchId));
        var events = await _router.RouteAsync(PlayerProfile.Create(owner, "DualBoundary", _clock.GetUtcNow()), RealtimeProtobufCodec.DecodeClient(command), "dual-native", CancellationToken.None);
        if (events.Count == 0 || !allowRejected && events.Any(e => e.Type.StartsWith("error.", StringComparison.Ordinal) || e.Type == "room.command_cancelled")) throw new InvalidOperationException("Legal dual intent rejected: " + JsonSerializer.Serialize(events));
        return new(command, events.Select(RealtimeProtobufCodec.EncodeServer).ToArray(), events);
    }
    public ValueTask DisposeAsync() => _registry.DisposeAsync();
}
