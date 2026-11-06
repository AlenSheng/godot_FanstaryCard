using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Only the explicitly approved affected-mechanism supplement; never invokes the original B05 campaign.</summary>
public sealed class SeasonMageApprovedSupplementTests
{
    public static bool Enabled => Environment.GetEnvironmentVariable("FANTASYCARD_RUN_B05_SUPPLEMENT") == "1";
    private static readonly string[] Slots = ["Head", "Hands", "Chest", "Legs", "Feet"];
    private static readonly TimeSpan Step = TimeSpan.FromMilliseconds(100);
    private sealed record Case(string Id, string Hero, int Difficulty, int HpPercent, string Kind, int Seed);
    private sealed record Command(Guid Battle, string Target, Guid[] Cards, long Revision, string ActionId);

    private static Case[] Plan()
    {
        using var json = JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_B05_SUPPLEMENT_PLAN")
            ?? throw new InvalidOperationException("Frozen approved supplement required.")));
        Assert.Equal(300, json.RootElement.GetProperty("original_used").GetInt32());
        var prior = json.RootElement.GetProperty("supplemental_prior_used").GetInt32();
        var rows = json.RootElement.GetProperty("cases").EnumerateArray().Select(x => new Case(x.GetProperty("id").GetString()!,
            x.GetProperty("hero").GetString()!, x.GetProperty("difficulty").GetInt32(), x.GetProperty("hp_percent").GetInt32(),
            x.GetProperty("kind").GetString()!, x.GetProperty("seed").GetInt32())).ToArray();
        Assert.InRange(prior, 0, 29); Assert.InRange(rows.Length, 1, 30 - prior);
        Assert.Equal(rows.Length, rows.Select(x => x.Id).Distinct(StringComparer.Ordinal).Count());
        foreach (var row in rows)
        {
            Assert.True(Enum.TryParse<HeroClass>(row.Hero, out var hero) && Enum.IsDefined(hero));
            Assert.InRange(row.Difficulty, 0, 5); Assert.True(row.HpPercent is 25 or 100);
            Assert.True(row.Kind is "growth" or "low-hp" or "recovery" or "compat" or "active-set");
        }
        return rows;
    }

    [Fact(Skip = "Approved supplement input preflight; no encounters.", SkipUnless = nameof(Enabled))]
    public void ApprovedInputsKeepThePublishedBaselineAndFitTheThirtyCaseAllowance()
    {
        var rows = Plan(); var candidate = SeasonMageCardCandidate.Current;
        foreach (var row in rows)
        {
            var config = row.Kind == "compat" ? GameConfigCatalog.Current : candidate;
            var hero = Enum.Parse<HeroClass>(row.Hero);
            var deck = SeasonClassEfficiencyPilotTests.Deck(hero, "flow-loop");
            Assert.Equal(20, deck.Distinct(StringComparer.Ordinal).Count());
            DeckRules.Validate(hero,deck,config.Cards.Where(x=>x.IsCodex).ToDictionary(x=>x.CardId,x=>new OwnedCard(x.CardId,x.HeroClass,(CardRarity)x.Rarity,1,false)));
            var armor = Armor(row.Difficulty,row.Kind=="active-set");
            SeasonLootRules.RequireEntry(Context(config, row.Difficulty), armor.Select(x => x.Equipment!), config);
            if(row.Kind=="active-set")
            {
                Assert.Equal(1,row.Difficulty);
                var profile=EquipmentCombatRules.Calculate(armor.Select(x=>new CombatEquipmentItem(Guid.Parse(x.ItemId),x.Equipment!.Slot,
                    x.Equipment.Quality,x.Equipment.Level,Enum.Parse<CardElement>(x.Equipment.Element),x.Equipment.EffectAffix,x.Equipment.SecondaryTrait)).ToArray(),config,"season-equipment-v1");
                Assert.True(profile.PiercingBonus>0);
            }
        }
        Assert.False(NumericalRules.SeasonV1.SeasonMageSustainBudget);
        Assert.Equal(1, GameConfigCatalog.Current.Cards.Single(x => x.CardId == "MAG-10").Effect.ImmediateDraw);
        Assert.Equal(0, candidate.Cards.Single(x => x.CardId == "MAG-10").Effect.ImmediateDraw);
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_B05_SUPPLEMENT_PREFLIGHT_OUTPUT") ?? throw new InvalidOperationException("Proof path required.");
        File.WriteAllText(output, JsonSerializer.Serialize(new { cases = rows.Length, original_used = 300, maximum_supplement = 30, new_encounters = 0 }));
    }

    [Fact(Skip = "Explicit affected-mechanism supplemental campaign, at most thirty new fixtures.", SkipUnless = nameof(Enabled))]
    public void ApprovedLiveFixturesReconcileCardsCreditReplayAndCheckpointRecovery()
    {
        var rows = Plan();
        var root = Environment.GetEnvironmentVariable("FANTASYCARD_B05_SUPPLEMENT_OUTPUT") ?? throw new InvalidOperationException("Owned output required.");
        Assert.False(Directory.Exists(root)); Directory.CreateDirectory(root);
        using var attempts = new StreamWriter(Path.Combine(root, "attempts.original.jsonl"));
        using var trace = new StreamWriter(Path.Combine(root, "events.original.jsonl"));
        using var results = new StreamWriter(Path.Combine(root, "cases.original.jsonl"));
        foreach (var row in rows)
        {
            attempts.WriteLine(JsonSerializer.Serialize(row)); attempts.Flush();
            Run(row, trace, results); trace.Flush(); results.Flush();
        }
    }

    private static SeasonContext Context(GameConfigCatalog config, int difficulty) => new("b05-approved-supplement", difficulty,
        "season-v1", config.Version, "season-equipment-v1");

    private static ExplorationItem[] Armor(int difficulty,bool activateLowerTier=false) => Slots.Select((slot, i) => new ExplorationItem(Guid.NewGuid().ToString("D"),
        ExplorationItemKind.Equipment, Equipment: new(slot, difficulty == 0 ? "Blue" : difficulty == 1 ? "Purple" : i == 0 ? "Orange" : "Purple",
            i < 3 ? "Water" : "Fire", difficulty == 0 ? null : i < (activateLowerTier?3:2) ? "Piercing" : "Vitality", "DrawInterval", 3,
            StatsVersion: "season-equipment-v1"), IsGenerated: false)).ToArray();

    private static void Run(Case row, StreamWriter trace, StreamWriter results)
    {
        var config = row.Kind == "compat" ? GameConfigCatalog.Current : SeasonMageCardCandidate.Current;
        var catalog = CombatCardCatalog.Create(config); var hero = Enum.Parse<HeroClass>(row.Hero);
        var deck = SeasonClassEfficiencyPilotTests.Deck(hero, "flow-loop");
        var numerics = row.Kind == "compat" ? NumericalRules.SeasonV1 : NumericalRules.SeasonV1 with
            { SeasonMageSustainBudget = true, SeasonMageReturnRateBasisPoints = 500 };
        var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, row.Seed, numerics, Context(config, row.Difficulty));
        var id = Guid.NewGuid();
        var player = room.AddPlayer(new(id, hero, deck, null, WeaponLevel: row.Difficulty, WornArmor: Armor(row.Difficulty,row.Kind=="active-set"),
            CardLevels: Enumerable.Repeat(row.Difficulty, 20).ToArray()));
        var map = ChaosMapGenerator.Generate(row.Seed, 1, config.SeasonThemes).Capture(); var boss = map.Cells.Single(x => x.IsBoss);
        room.InitializeMap(ChaosMapState.Restore(map with { SpawnPositions = [boss.Position] }));
        if (row.HpPercent != 100) player.Combat.Restore(player.Combat.Capture() with { Hp = player.Combat.MaximumHp * row.HpPercent / 100 });
        var target = Assert.Single(player.Pve!.Monsters); var initial = player.Combat.Deck.Hand.Count;
        long natural = 0, effect = 0, spent = 0; var kills = 0; var actions = 0; var recovered = false; var replayed = false; var gateRejected = false;
        double passiveUnits = 0, creditEarned = 0; var lastAt = TimeSpan.FromMilliseconds(-500); Command? last = null;
        CombatCardInstance[] All() => player.Combat.Deck.Hand.Concat(player.Combat.Deck.Library).Concat(player.Combat.Deck.Discard).ToArray();
        void Check()
        {
            var all = All(); Assert.Equal(20 + kills, all.Length); Assert.Equal(all.Length, all.Select(x => x.InstanceId).Distinct().Count());
            Assert.InRange(player.Combat.Deck.Hand.Count, 0, 5); Assert.Equal(initial + natural + effect - spent, player.Combat.Deck.Hand.Count);
            Assert.InRange(player.Combat.Hp, 0, player.Combat.EffectiveMaximumHp); Assert.InRange(player.Combat.Shield, 0, player.Combat.MaximumHp / 2);
            Assert.InRange(player.Combat.Deck.DrawCharge, 0, Math.BitDecrement(1d));
            if (row.Kind != "compat")
            {
                Assert.InRange(player.Combat.FenxianReturnCredit!.Value, 0, 2);
                Assert.Equal(500, player.Combat.FenxianReturnRateBasisPoints);
                Assert.True(passiveUnits + player.Combat.FenxianReturnCredit.Value <= creditEarned + 1e-8);
            }
        }
        void Tick()
        {
            var hand = player.Combat.Deck.Hand.Count; var credit = player.Combat.FenxianReturnCredit;
            room.Advance(Step, DateTimeOffset.UnixEpoch + room.Elapsed + Step);
            var added = player.Combat.Deck.Hand.Count - hand; Assert.True(added >= 0); natural += added;
            if (credit is not null)
            {
                var earned = player.Combat.FenxianReturnCredit!.Value - credit.Value;
                Assert.InRange(earned, -1e-10, Step.TotalSeconds / player.Combat.NaturalDrawIntervalSeconds * .05 + 1e-10);
                creditEarned += Math.Max(0, earned);
            }
            Check();
        }
        trace.WriteLine(JsonSerializer.Serialize(new { kind = "start", row, config.Version, config.ContentHash, numerics,
            initial, deck, worn = player.WornArmor, player = room.CapturePlayer(id), controlled_boss_spawn = true, route_or_settlement_claimed = false }));
        while (room.Elapsed.TotalSeconds < 600 && player.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Choice))
        {
            Check();
            if (row.Kind == "recovery" && !recovered && actions >= 2)
            {
                var saved = JsonSerializer.Serialize(room.Capture());
                room = BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(saved)!, catalog, row.Seed);
                Assert.Equal(saved, JsonSerializer.Serialize(room.Capture())); player = room.GetPlayer(id); target = Assert.Single(player.Pve!.Monsters);
                var before = JsonSerializer.Serialize(room.Capture()); var command = last!;
                var replay = room.PlayCards(id, command.Battle, command.Target, command.Cards, command.Revision,
                    DateTimeOffset.UnixEpoch + room.Elapsed, command.ActionId);
                Assert.True(replay.ActionReplayed); Assert.Equal(before, JsonSerializer.Serialize(room.Capture())); recovered = true;
                trace.WriteLine(JsonSerializer.Serialize(new { kind = "recovered", row.Id, room.Elapsed, snapshot = room.Capture(), replay }));
            }
            if (player.Combat.StunRemaining <= TimeSpan.Zero && room.GetCombatActionStatus(id).RemainingMs == 0 && player.Combat.Deck.Hand.Count > 0)
            {
                var chosen = SeasonClassEfficiencyPilotTests.Choose(room, player, target, catalog, deck, out _, out _, valueSustainIntents: true);
                if (chosen.Length > 0)
                {
                    var definitions = chosen.Select(x => catalog.Get(x.CardId, x.Level, x.ElementOverride)).ToArray();
                    var draft = CombatResolver.Resolve(definitions, player.Combat, target.ElementalResistance);
                    var hand = player.Combat.Deck.Hand.Count; var credit = player.Combat.FenxianReturnCredit;
                    var command = new Command(player.Pve!.BattleId, target.MonsterId, chosen.Select(x => x.InstanceId).ToArray(), room.Revision, room.NewCombatActionId(id));
                    var resolution = room.PlayCards(id, command.Battle, command.Target, command.Cards, command.Revision, DateTimeOffset.UnixEpoch + room.Elapsed, command.ActionId);
                    var extraDraw = resolution.ImmediateDraw - draft.ImmediateDraw; var extraCharge = resolution.DrawCharge - draft.DrawCharge;
                    Assert.InRange(extraDraw, 0, hero == HeroClass.Mage && draft.CoreCount >= 2 ? chosen.Length - 1 : 0);
                    Assert.InRange(extraCharge, -1e-10, hero == HeroClass.Mage ? .500000001 : 0);
                    if (credit is not null) Assert.Equal(credit.Value - extraDraw - extraCharge, player.Combat.FenxianReturnCredit!.Value, 8);
                    passiveUnits += extraDraw + extraCharge; actions++; spent += chosen.Length; effect += player.Combat.Deck.Hand.Count - hand + chosen.Length;
                    if (resolution.TargetDefeated) kills++;
                    Assert.True(room.Elapsed - lastAt >= TimeSpan.FromMilliseconds(500)); lastAt = room.Elapsed; last = command;
                    var saved = JsonSerializer.Serialize(room.Capture());
                    if (!replayed)
                    {
                        var replay = room.PlayCards(id, command.Battle, command.Target, command.Cards, command.Revision, DateTimeOffset.UnixEpoch + room.Elapsed, command.ActionId);
                        Assert.True(replay.ActionReplayed); Assert.Equal(saved, JsonSerializer.Serialize(room.Capture())); replayed = true;
                    }
                    if (!gateRejected && player.Phase == RoomPlayerPhase.Pve && player.Combat.Deck.Hand.Count > 0)
                    {
                        var next = player.Combat.Deck.Hand[0].InstanceId; var nextId = room.NewCombatActionId(id);
                        Assert.Throws<DomainValidationException>(() => room.PlayCards(id, command.Battle, command.Target, [next], room.Revision,
                            DateTimeOffset.UnixEpoch + room.Elapsed, nextId));
                        Assert.Equal(saved, JsonSerializer.Serialize(room.Capture())); gateRejected = true;
                    }
                    Check();
                    trace.WriteLine(JsonSerializer.Serialize(new { kind = "cast", row.Id, seconds = room.Elapsed.TotalSeconds, selected = chosen,
                        printedDraw = draft.ImmediateDraw, printedCharge = draft.DrawCharge, extraDraw, extraCharge, resolution,
                        handBefore = hand, handAfter = player.Combat.Deck.Hand.Count, natural, effect, spent, kills, passiveUnits, creditEarned,
                        creditBefore = credit, creditAfter = player.Combat.FenxianReturnCredit, allAfter = All() }));
                }
            }
            Tick();
        }
        Check(); Assert.True(replayed); Assert.True(gateRejected);
        if (row.Kind == "recovery") Assert.True(recovered);
        var result = new { row, outcome = player.Phase == RoomPlayerPhase.Choice ? "Win" : player.Phase == RoomPlayerPhase.Dead ? "Dead" : "Timeout",
            seconds = room.Elapsed.TotalSeconds, actions, kills, initial, natural, effect, spent, finalHand = player.Combat.Deck.Hand.Count,
            passiveUnits, creditEarned, finalCredit = player.Combat.FenxianReturnCredit, replayed, gateRejected, recovered,
            pendingRed = player.PendingRedEvaluation is not null, red_quota_or_settlement_claimed = false, snapshot = room.Capture() };
        results.WriteLine(JsonSerializer.Serialize(result)); trace.WriteLine(JsonSerializer.Serialize(new { kind = "end", result }));
    }
}
