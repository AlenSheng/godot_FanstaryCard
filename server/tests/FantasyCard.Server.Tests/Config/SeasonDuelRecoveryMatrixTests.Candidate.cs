using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

public sealed partial class SeasonDuelRecoveryMatrixTests
{
    public static bool CandidateEnabled => Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D02_CARD_CANDIDATE") == "1";
    private sealed record CandidateCase(string Id, HeroClass First, HeroClass Late, int Difficulty, string Outcome, string DisconnectRole, int Seed);

    private static CandidateCase[] CandidatePlan()
    {
        using var json = JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D02_CANDIDATE_PLAN")
            ?? throw new InvalidOperationException("Frozen candidate PVP plan required.")));
        var prior = json.RootElement.GetProperty("prior_used").GetInt32();
        var rows = json.RootElement.GetProperty("cases").EnumerateArray().Select(x => new CandidateCase(x.GetProperty("id").GetString()!,
            Enum.Parse<HeroClass>(x.GetProperty("first").GetString()!), Enum.Parse<HeroClass>(x.GetProperty("late").GetString()!),
            x.GetProperty("difficulty").GetInt32(), x.GetProperty("outcome").GetString()!, x.GetProperty("disconnect_role").GetString()!, x.GetProperty("seed").GetInt32())).ToArray();
        Assert.InRange(prior, 0, 299); Assert.InRange(rows.Length, 1, 300 - prior);
        Assert.Equal(rows.Length, rows.Select(x => x.Id).Distinct(StringComparer.Ordinal).Count());
        foreach (var row in rows)
        {
            Assert.True(Enum.IsDefined(row.First) && Enum.IsDefined(row.Late));
            Assert.True(row.First == HeroClass.Mage || row.Late == HeroClass.Mage);
            Assert.True(row.Difficulty is 0 or 5); Assert.True(row.Outcome is "Reconnect" or "Expire");
            Assert.True(row.DisconnectRole is "First" or "Late");
        }
        return rows;
    }

    [Fact(Skip = "Explicit candidate PVP input preflight, no timed duels.", SkipUnless = nameof(CandidateEnabled))]
    public void CardCandidatePvpInputsKeepLegalDecksAndOriginalPublishedDefaults()
    {
        var config = SeasonMageCardCandidate.Current; var rows = CandidatePlan();
        foreach (var row in rows)
        foreach (var hero in new[] { row.First, row.Late })
        {
            DeckRules.Validate(hero, Deck(hero), config.Cards.Where(x => x.IsCodex).ToDictionary(x => x.CardId,
                x => new OwnedCard(x.CardId, x.HeroClass, (CardRarity)x.Rarity, 1, false)));
            SeasonLootRules.RequireEntry(new("d02-card-candidate", row.Difficulty, "season-v1", config.Version, "season-equipment-v1"),
                CandidateArmor(row.Difficulty).Select(x => x.Equipment!), config);
        }
        Assert.Equal(0, config.Cards.Single(x => x.CardId == "MAG-10").Effect.ImmediateDraw);
        Assert.Equal(1, GameConfigCatalog.Current.Cards.Single(x => x.CardId == "MAG-10").Effect.ImmediateDraw);
        Assert.False(NumericalRules.SeasonV1.SeasonMageSustainBudget);
        File.WriteAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D02_CANDIDATE_PREFLIGHT_OUTPUT")
            ?? throw new InvalidOperationException("Proof output required."), JsonSerializer.Serialize(new { cases = rows.Length, new_duels = 0, config.Version, config.ContentHash }));
    }

    [Fact(Skip = "Budgeted affected card/passive PVP boundaries; no old matrix replay.", SkipUnless = nameof(CandidateEnabled))]
    public void CardCandidatePvpKeepsChangedCardGatesAndFrozenBudgetAcrossRecovery()
    {
        var rows = CandidatePlan(); var root = Environment.GetEnvironmentVariable("FANTASYCARD_D02_CANDIDATE_OUTPUT")
            ?? throw new InvalidOperationException("Owned output required.");
        Assert.False(Directory.Exists(root)); Directory.CreateDirectory(root);
        using var attempts = new StreamWriter(Path.Combine(root, "attempts.original.jsonl"));
        using var trace = new StreamWriter(Path.Combine(root, "events.original.jsonl"));
        using var results = new StreamWriter(Path.Combine(root, "cases.original.jsonl"));
        foreach (var row in rows)
        {
            attempts.WriteLine(JsonSerializer.Serialize(row)); attempts.Flush();
            RunCandidate(row, trace, results); trace.Flush(); results.Flush();
        }
    }

    private static ExplorationItem[] CandidateArmor(int difficulty) => Slots.Select((slot, i) => new ExplorationItem(Guid.NewGuid().ToString("D"),
        ExplorationItemKind.Equipment, Equipment: new(slot, difficulty == 0 ? "Blue" : i == 0 ? "Orange" : "Purple",
            i < 3 ? "Water" : "Fire", difficulty == 0 ? null : i < 2 ? "Piercing" : "Vitality", "DrawInterval", 3,
            StatsVersion: "season-equipment-v1"), IsGenerated: false)).ToArray();

    private static void CandidateInitialHand(RoomPlayerState player)
    {
        var saved = player.Combat.Capture();
        var all = saved.Deck.Hand.Concat(saved.Deck.Library).Concat(saved.Deck.Discard).ToArray();
        Assert.Equal(20, all.Length);
        var names = player.HeroClass == HeroClass.Mage ? new[] { "GP18", "GP13", "MAG-10" } : new[] { "GP18", "GP13", "GP20" };
        var hand = names.Select(id => Assert.Single(all, x => x.CardId == id)).ToArray();
        var ids = hand.Select(x => x.InstanceId).ToHashSet();
        // Declared initial boundary state only: preserve every physical card and RNG, with no later hand/library edits.
        player.Combat.Restore(saved with { Deck = saved.Deck with { Hand = hand, Library = all.Where(x => !ids.Contains(x.InstanceId)).ToArray(), Discard = [] } });
        Assert.Equal(saved.RandomState, player.Combat.Capture().RandomState);
    }

    private static void RunCandidate(CandidateCase row, StreamWriter trace, StreamWriter results)
    {
        var config = SeasonMageCardCandidate.Current; var catalog = CombatCardCatalog.Create(config);
        var context = new SeasonContext("d02-card-candidate", row.Difficulty, "season-v1", config.Version, "season-equipment-v1");
        var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, row.Seed,
            NumericalRules.SeasonV1 with { SeasonMageSustainBudget = true, SeasonMageReturnRateBasisPoints = 500 }, context);
        var firstId = Guid.NewGuid(); var lateId = Guid.NewGuid();
        room.AddPlayer(new(firstId, row.First, Deck(row.First), null, WeaponLevel: row.Difficulty, WornArmor: CandidateArmor(row.Difficulty), CardLevels: Enumerable.Repeat(row.Difficulty, 20).ToArray()));
        room.AddPlayer(new(lateId, row.Late, Deck(row.Late), null, WeaponLevel: row.Difficulty, WornArmor: CandidateArmor(row.Difficulty), CardLevels: Enumerable.Repeat(row.Difficulty, 20).ToArray()));
        room.InitializeMap(ChaosMapGenerator.Generate(row.Seed, 2, config.SeasonThemes)); Step(room);
        foreach (var id in new[] { firstId, lateId })
        {
            var combat = room.GetPlayer(id).Combat;
            combat.Heal(combat.EffectiveMaximumHp - combat.Hp); combat.GainShield(5); combat.AddDrawCharge(.45);
        }
        var beforeDuel = room.Capture(); var firstBefore = room.CapturePlayer(firstId); var lateBefore = room.CapturePlayer(lateId);
        var duel = room.StartDuel(firstId, lateId, Epoch + room.Elapsed); var duelId = duel.DuelId;
        CandidateInitialHand(room.GetPlayer(firstId)); CandidateInitialHand(room.GetPlayer(lateId));
        trace.WriteLine(JsonSerializer.Serialize(new { kind = "start", row, config.Version, config.ContentHash, firstId, lateId, beforeDuel,
            snapshot = room.Capture(), controlled_initial_hand_once = true, random_pvp_winrate_claimed = false }));
        var changed = new List<(Guid Player, Guid[] Cards, CombatResolution Receipt)>();
        (CombatResolution Receipt, Guid[] Cards) Play(Guid actor, Guid target, string cardId)
        {
            var player = room.GetPlayer(actor); var card = Assert.Single(player.Combat.Deck.Hand, x => x.CardId == cardId);
            var ids = new[] { card.InstanceId }; var credit = player.Combat.FenxianReturnCredit!.Value;
            var result = room.PlayCards(actor, duelId, target.ToString("D"), ids, room.Revision, Epoch + room.Elapsed, room.NewCombatActionId(actor));
            Assert.False(result.BattleEnded); Assert.Equal(RoomPlayerPhase.Pvp, player.Phase);
            var printed = catalog.Get(card.CardId, card.Level, card.ElementOverride).Effect;
            Assert.Equal(credit - result.ImmediateDraw + printed.ImmediateDraw - result.DrawCharge + printed.DrawCharge, player.Combat.FenxianReturnCredit!.Value, 8);
            if (cardId == "MAG-10") { Assert.Equal(0, result.ImmediateDraw); changed.Add((actor, ids, result)); }
            trace.WriteLine(JsonSerializer.Serialize(new { kind = "cast", row.Id, seconds = room.Elapsed.TotalSeconds, actor, target, card,
                printed, result, creditBefore = credit, creditAfter = player.Combat.FenxianReturnCredit, snapshot = room.Capture() }));
            return (result, ids);
        }
        void Reject(Guid actor, Guid target, string cardId, string message)
        {
            var before = JsonSerializer.Serialize(room.Capture());
            var error = Assert.Throws<DomainValidationException>(() => Play(actor, target, cardId));
            Assert.Equal(message, error.Message); Assert.Equal(before, JsonSerializer.Serialize(room.Capture()));
        }
        Reject(lateId, firstId, row.Late == HeroClass.Mage ? "MAG-10" : "GP13", "The late joiner is still locked.");
        var first = Play(firstId, lateId, "GP18");
        for (var i = 0; i < 4; i++) Step(room);
        Reject(firstId, lateId, "GP13", "Successful combat actions must be at least 500ms apart."); Step(room);
        Play(firstId, lateId, "GP13"); Step(room); Step(room);
        Reject(lateId, firstId, row.Late == HeroClass.Mage ? "MAG-10" : "GP13", "The late joiner is still locked."); Step(room);
        var late = Play(lateId, firstId, row.Late == HeroClass.Mage ? "MAG-10" : "GP13");
        if (row.First == HeroClass.Mage)
        {
            while (room.GetPlayer(firstId).Combat.StunRemaining > TimeSpan.Zero || room.GetCombatActionStatus(firstId).RemainingMs > 0) Step(room);
            Play(firstId, lateId, "MAG-10");
        }
        Assert.Equal((row.First == HeroClass.Mage ? 1 : 0) + (row.Late == HeroClass.Mage ? 1 : 0), changed.Count);
        var disconnected = row.DisconnectRole == "First" ? firstId : lateId; room.MarkPlayerDisconnected(disconnected);
        var frozenFirst = JsonSerializer.Serialize(room.GetPlayer(firstId).Combat.Capture()); var frozenLate = JsonSerializer.Serialize(room.GetPlayer(lateId).Combat.Capture());
        for (var i = 0; i < 20; i++) Step(room);
        var saved = JsonSerializer.Serialize(room.Capture()); room = BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(saved)!, catalog, row.Seed);
        Assert.Equal(saved, JsonSerializer.Serialize(room.Capture()));
        foreach (var command in changed)
        {
            var target = command.Player == firstId ? lateId : firstId; var before = JsonSerializer.Serialize(room.Capture());
            Assert.True(room.ReplayCombatAction(command.Player, command.Receipt.CombatActionId, duelId, target.ToString("D"), command.Cards).ActionReplayed);
            Assert.Equal(before, JsonSerializer.Serialize(room.Capture()));
        }
        if (row.Outcome == "Reconnect")
        {
            Assert.Equal(frozenFirst, JsonSerializer.Serialize(room.GetPlayer(firstId).Combat.Capture())); Assert.Equal(frozenLate, JsonSerializer.Serialize(room.GetPlayer(lateId).Combat.Capture()));
            room.MarkPlayerConnected(disconnected); Step(room);
            Assert.False(room.RequestDuelLeave(duelId, firstId, Epoch + room.Elapsed)); Assert.True(room.RequestDuelLeave(duelId, lateId, Epoch + room.Elapsed));
            Assert.Equal(JsonSerializer.Serialize(firstBefore.Combat), JsonSerializer.Serialize(room.CapturePlayer(firstId).Combat));
            Assert.Equal(JsonSerializer.Serialize(lateBefore.Combat), JsonSerializer.Serialize(room.CapturePlayer(lateId).Combat));
            Assert.Equal(JsonSerializer.Serialize(firstBefore.Pve), JsonSerializer.Serialize(room.CapturePlayer(firstId).Pve));
            Assert.Equal(JsonSerializer.Serialize(lateBefore.Pve), JsonSerializer.Serialize(room.CapturePlayer(lateId).Pve));
        }
        else
        {
            for (var i = 0; i < 129; i++) Step(room);
            Assert.Equal(RoomPlayerPhase.Pvp, room.GetPlayer(disconnected).Phase);
            Assert.Equal(frozenFirst, JsonSerializer.Serialize(room.GetPlayer(firstId).Combat.Capture())); Assert.Equal(frozenLate, JsonSerializer.Serialize(room.GetPlayer(lateId).Combat.Capture()));
            Step(room); var winner = disconnected == firstId ? lateId : firstId;
            var control = BattleRoom.Restore(beforeDuel, catalog, row.Seed); Step(control);
            Assert.Equal(RoomPlayerPhase.Dead, room.GetPlayer(disconnected).Phase);
            Assert.Equal(JsonSerializer.Serialize(control.CapturePlayer(winner).Combat), JsonSerializer.Serialize(room.CapturePlayer(winner).Combat));
            Assert.Equal(JsonSerializer.Serialize(control.CapturePlayer(winner).Pve), JsonSerializer.Serialize(room.CapturePlayer(winner).Pve));
            var original = disconnected == firstId ? firstBefore : lateBefore;
            var pile = Assert.Single(room.Capture().RelicPiles!, x => x.VictimId == disconnected.ToString("D"));
            foreach (var item in original.WornArmor!) Assert.Contains(pile.Items, x => x.ItemId == item.ItemId && x.Equipment == item.Equipment);
        }
        Assert.Empty(room.Capture().Duels);
        var result = new { row, seconds = room.Elapsed.TotalSeconds, changed_card_casts = changed.Count, firstCast = first.Receipt,
            lateCast = late.Receipt, late700_rejected800_allowed = true, cooldown400_rejected500_allowed = true,
            frozen_credit_preserved = true, changed_action_replay_preserved = true, snapshot = room.Capture(),
            random_pvp_balance_or_winrate_claimed = false, full_process_restart_claimed = false };
        results.WriteLine(JsonSerializer.Serialize(result)); trace.WriteLine(JsonSerializer.Serialize(new { kind = "end", result }));
    }
}
