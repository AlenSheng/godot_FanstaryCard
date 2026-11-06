using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Mechanical primary actions on the real actor; normal bots and all resolver rules remain active.</summary>
internal sealed class SeasonFirstFortnightMechanicalPlayer(SeasonFirstFortnightInputsTests.Actor actor, Guid playerId, int actualSeed, bool seekDuelDiagnostic = false)
{
    private readonly Random _choiceRandom = new(actualSeed ^ 0x43484F49);
    private readonly TimeSpan _reaction = TimeSpan.FromSeconds(actor.Cohort == "novice" ? 1 : actor.Cohort == "returning" ? .7 : .5);
    private TimeSpan _lastCombatAction = TimeSpan.FromSeconds(-1);
    private bool _potionUsed;

    internal sealed record ActionResult(string Kind, bool Mutated, TimeSpan Elapsed, object? Detail = null);
    internal IRoomCommand<ActionResult> Decide(DateTimeOffset now) => new Decision(this, now);

    private sealed class Decision(SeasonFirstFortnightMechanicalPlayer controller, DateTimeOffset now) : IRoomCommand<ActionResult>
    {
        private bool _mutated;
        public bool NotifyObservers => _mutated;
        public ActionResult Execute(BattleRoom room)
        {
            var result = controller.Act(room, now);
            _mutated = result.Mutated;
            return result;
        }
    }

    private ActionResult Act(BattleRoom room, DateTimeOffset now)
    {
        var player = room.GetPlayer(playerId);
        ActionResult Wait(string reason) => new(reason, false, room.Elapsed);
        if (player.Phase is RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted) return Wait("terminal");
        if (room.Map is null) throw new InvalidOperationException("F01 mechanical actions require the actual launched map.");
        if (player.PendingRedEvaluation is not null)
            throw new InvalidOperationException("F01 requires actual red admission; no exhausted-quota substitution is permitted.");
        var config = GameConfigCatalog.Current;
        var catalog = CombatCardCatalog.Create(config);
        if (player.Phase == RoomPlayerPhase.Choice)
        {
            var choices = room.GetRewardChoice(playerId);
            var gear = choices.Options.Single(option => option.Kind == RewardChoiceKind.Equipment);
            var offered = gear.Item!.Equipment!;
            var current = player.WornArmor.SingleOrDefault(item => item.Equipment!.Slot == offered.Slot)?.Equipment;
            var better = current is null || SeasonLootConfig.Rank(offered.Quality) > SeasonLootConfig.Rank(current.Quality)
                || offered.Quality == current.Quality && offered.Level > current.Level;
            var wantGear = actor.Cohort == "novice" || actor.Cohort == "returning" && _choiceRandom.NextDouble() < .75
                || actor.Cohort == "skilled" && SeasonLootConfig.Rank(offered.Quality) >= 3;
            var selected = player.Combat.Hp <= player.Combat.EffectiveMaximumHp * .60
                ? choices.Options.Single(option => option.Kind == RewardChoiceKind.ImmediateHeal)
                : wantGear ? gear : choices.Options.Single(option => option.Kind == RewardChoiceKind.EquipmentFragments);
            var equip = selected.Kind == RewardChoiceKind.Equipment && better
                && (SeasonLootConfig.Rank(offered.Quality) < 4 || !player.WornArmor.Any(item => item.Equipment!.Slot != offered.Slot && SeasonLootConfig.Rank(item.Equipment.Quality) >= 4));
            var applied = room.ClaimReward(playerId, selected.OptionId, equip: equip);
            return new("reward", true, room.Elapsed, new { choices, selected, applied, equip });
        }
        if (player.Phase == RoomPlayerPhase.ActionBar)
        {
            var snapshot = room.CapturePlayer(playerId);
            if (snapshot.ExtractionRemaining is not null || snapshot.SpringDrink is not null) return Wait("reading");
            if (!_potionUsed && player.Combat.Hp < player.Combat.MaximumHp * .30
                && player.Inventory.Items.Any(item => item.Kind == ExplorationItemKind.HealthPotion))
            {
                var result = room.UsePotion(playerId);
                _potionUsed = true;
                return new("potion", true, room.Elapsed, result);
            }
            var position = player.Position ?? throw new InvalidOperationException("F01 launched player has no actual position.");
            var cell = room.Map.GetCell(position);
            if (cell.HasSpring && player.Combat.Hp < player.Combat.EffectiveMaximumHp * .85
                && snapshot.ConsumedSprings?.Contains(position) != true)
                return new("spring", true, room.Elapsed, new { remaining = room.RequestSpring(playerId) });
            if (seekDuelDiagnostic)
            {
                var opponent = room.Capture().Players.Where(value => value.IsBot
                        && value.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted or RoomPlayerPhase.Pvp)
                        && value.Position is not null && value.Position != position)
                    .OrderBy(value => value.Position!.Value.ManhattanDistance(position)).ThenBy(value => value.PlayerId).FirstOrDefault();
                if (opponent?.Position is { } opponentPosition)
                    return new("move-to-encounter", true, room.Elapsed,
                        room.MovePlayerAndPair(playerId, NextOnShortestPath(room.Map, position, opponentPosition), room.Revision, now));
            }
            var early = actor.Cohort == "novice" && room.Season!.Difficulty == 0 && player.WornArmor.Count < 3 && cell.HasEvacuation;
            if (position == room.Map.BossPosition || early)
                return new("extract-reading", true, room.Elapsed, new { remaining = room.RequestExtraction(playerId), now });
            var next = NextOnShortestPath(room.Map, position);
            return new("move", true, room.Elapsed, room.MovePlayerAndPair(playerId, next, room.Revision, now));
        }
        if (player.Phase is not (RoomPlayerPhase.Pve or RoomPlayerPhase.Pvp)
            || player.Combat.StunRemaining > TimeSpan.Zero || room.GetCombatActionStatus(playerId).RemainingMs != 0
            || room.Elapsed - _lastCombatAction < _reaction || player.Combat.Deck.Hand.Count == 0)
            return Wait("reaction-or-control");
        CombatCardInstance[] chosen;
        Guid battle;
        string target;
        int previews;
        int candidates;
        if (player.Phase == RoomPlayerPhase.Pve)
        {
            var enemy = player.Pve!.Monsters.Where(value => !value.IsDead).OrderBy(value => value.Hp + value.Shield).First();
            chosen = SeasonClassEfficiencyPilotTests.Choose(room, player, enemy, catalog, actor.Cards,
                out previews, out candidates, observedAtUtc: now);
            battle = player.Pve.BattleId;
            target = enemy.MonsterId;
        }
        else
        {
            battle = player.CurrentDuelId ?? throw new InvalidOperationException("F01 PVP has no actual duel identity.");
            var duel = room.Capture().Duels.Single(value => value.DuelId == battle);
            if (duel.LatePlayerId == playerId && now < duel.LatePlayerUnlockAt) return Wait("late-duel-lock");
            var opponent = room.GetPlayer(duel.FirstPlayerId == playerId ? duel.LatePlayerId : duel.FirstPlayerId);
            target = opponent.PlayerId.ToString("D");
            chosen = ChooseDuel(room, player, opponent, catalog, battle, target, now, out previews, out candidates);
        }
        if (chosen.Length == 0) return Wait("no-nonsuicidal-recipe");
        var phaseBefore = player.Phase;
        var action = room.NewCombatActionId(playerId);
        var resolution = room.PlayCards(playerId, battle, target, chosen.Select(card => card.InstanceId).ToArray(), room.Revision, now, action);
        _lastCombatAction = room.Elapsed;
        return new("cast", true, room.Elapsed, new { battle, target, cards = chosen.Select(card => new { card.InstanceId, card.CardId, card.Level }),
            previews, candidates, phaseBefore, resolution, action });
    }

    private static MapPosition NextOnShortestPath(ChaosMapState map, MapPosition start, MapPosition? target = null)
    {
        var queue = new Queue<MapPosition>();
        var previous = new Dictionary<MapPosition, MapPosition?> { [start] = null };
        queue.Enqueue(start);
        while (queue.TryDequeue(out var current))
        {
            if (current == (target ?? map.BossPosition))
            {
                var position = current;
                while (previous[position] is { } prior && prior != start) position = prior;
                return position;
            }
            foreach (var next in map.GetNeighbors(current).Where(next => map.CanMove(current, next)).OrderBy(next => next.Row).ThenBy(next => next.Column))
                if (previous.TryAdd(next, current)) queue.Enqueue(next);
        }
        throw new InvalidOperationException("F01 actual generated map has no legal boss path.");
    }

    private static CombatCardInstance[] ChooseDuel(BattleRoom room, RoomPlayerState player, RoomPlayerState opponent,
        CombatCardCatalog catalog, Guid battle, string target, DateTimeOffset now, out int previews, out int candidates)
    {
        var hand = player.Combat.Deck.Hand;
        var options = new List<(CombatCardInstance[] Cards, double Score)>();
        double Score(int damage, int heal, int shield, int draw, double charge, double stun, int cost, int spent) =>
            Math.Min(damage, opponent.Combat.Hp + opponent.Combat.Shield)
            + Math.Min(heal, Math.Max(0, player.Combat.EffectiveMaximumHp - player.Combat.Hp)) * 1.5
            + Math.Min(shield, Math.Max(0, player.Combat.MaximumHp / 2 - player.Combat.Shield))
            + draw * 6 + charge * 5 + stun * 2 - spent - cost * 2 - (cost >= player.Combat.Hp ? 10000 : 0);
        for (var mask = 1; mask < 1 << hand.Count; mask++)
        {
            var cards = hand.Where((_, index) => (mask & 1 << index) != 0).ToArray();
            var draft = CombatResolver.Resolve(cards.Select(card => catalog.Get(card.CardId, card.Level, card.ElementOverride)).ToArray(),
                player.Combat, opponent.Combat.ElementalResistance);
            options.Add((cards, Score(draft.Damage, draft.Heal, draft.Shield, draft.ImmediateDraw, draft.DrawCharge,
                draft.Stun.TotalSeconds, draft.HealthCost, cards.Length)));
        }
        candidates = options.Count;
        previews = 0;
        var best = Array.Empty<CombatCardInstance>();
        var bestScore = double.NegativeInfinity;
        foreach (var option in options.OrderByDescending(value => value.Score).Take(3))
        {
            var preview = room.PreviewCards(player.PlayerId, battle, target, option.Cards.Select(card => card.InstanceId).ToArray(), room.Revision, now);
            previews++;
            var score = Score(preview.HpDamage + preview.ShieldDamage, preview.Heal, preview.ShieldGain,
                preview.ImmediateDraw, preview.DrawCharge, preview.StunSeconds, preview.HealthCost, option.Cards.Length);
            if (score > bestScore) { best = option.Cards; bestScore = score; }
        }
        return bestScore < -1000 ? [] : best;
    }
}
