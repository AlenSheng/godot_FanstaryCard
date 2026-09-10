using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class CombatPreviewAndFeedbackTests
{
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();
    private static readonly DateTimeOffset Now = DateTimeOffset.UnixEpoch.AddSeconds(10);

    [Fact]
    public void Preview_is_pure_and_matches_actual_health_shield_draw_and_leveled_card_resolution()
    {
        var room = CreateRoom();
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        player.Combat.TakeDamage(30);
        SetHand(player, new("C01", 3), new("common-11", 0), new("common-15", 0));
        var selected = player.Combat.Deck.Hand.Select(card => card.InstanceId).ToArray();
        var before = room.Capture();
        var battle = player.Pve!;

        var preview = room.PreviewCards(player.PlayerId, battle.BattleId, "test-monster", selected, room.Revision, Now);
        var again = room.PreviewCards(player.PlayerId, battle.BattleId, "test-monster", selected, room.Revision, Now);

        Assert.Equivalent(before, room.Capture(), strict: true);
        Assert.Equivalent(preview, again, strict: true);
        Assert.Empty(room.DrainCombatFeedback());
        var actual = room.PlayCards(player.PlayerId, battle.BattleId, "test-monster", selected, room.Revision, Now);
        Assert.Equivalent(preview with { RoomRevision = actual.RoomRevision }, actual, strict: true);
        Assert.Equal(actual.HpDamage + actual.ShieldDamage, actual.DamageSegments!.Sum(segment => segment.Amount));
        Assert.Equal(player.PlayerId.ToString("D"), Assert.Single(room.DrainCombatFeedback()).SourceId);
        Assert.Empty(room.DrainCombatFeedback());
    }

    [Fact]
    public void Lethal_preview_does_not_roll_live_rewards_or_grant_monster_cards()
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", Catalog, 77);
        var playerId = Guid.NewGuid();
        room.AddPlayer(new(playerId, HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(77, 1));
        var player = room.GetPlayer(playerId);
        var monster = player.Pve!.Monsters[0];
        monster.TakeDamage(monster.Hp + monster.Shield - 1);
        foreach (var other in player.Pve.Monsters.Skip(1)) other.TakeDamage(other.Hp + other.Shield);
        SetHand(player, new CardSetup("common-01", 0));
        var before = room.Capture();
        var selected = new[] { player.Combat.Deck.Hand[0].InstanceId };

        var preview = room.PreviewCards(playerId, player.Pve.BattleId, monster.MonsterId, selected, room.Revision, Now);

        Assert.True(preview.BattleEnded);
        Assert.Equivalent(before, room.Capture(), strict: true);
        Assert.Empty(room.DrainCombatFeedback());
        var control = BattleRoom.Restore(before, Catalog, 900);
        room.PlayCards(playerId, player.Pve.BattleId, monster.MonsterId, selected, room.Revision, Now);
        control.PlayCards(playerId, control.GetPlayer(playerId).Pve!.BattleId, monster.MonsterId, selected, control.Revision, Now);
        Assert.Equal(control.Capture().RandomStreams, room.Capture().RandomStreams);
        Assert.Equal(control.GetPlayer(playerId).RewardChoice!.Capture().Options.Select(option => option.Kind),
            player.RewardChoice!.Capture().Options.Select(option => option.Kind));
        Assert.Single(player.Combat.Deck.Discard, card => card.CardId.StartsWith("M-", StringComparison.Ordinal));
    }

    [Fact]
    public void Preview_enforces_revision_and_current_target_legality_without_mutation()
    {
        var room = CreateRoom();
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        var selected = new[] { player.Combat.Deck.Hand[0].InstanceId };
        var before = room.Capture();

        Assert.Throws<DomainValidationException>(() => room.PreviewCards(player.PlayerId, player.Pve!.BattleId,
            "test-monster", selected, room.Revision - 1, Now));
        Assert.Throws<DomainValidationException>(() => room.PreviewCards(player.PlayerId, player.Pve!.BattleId,
            "missing", selected, room.Revision, Now));
        Assert.Equivalent(before, room.Capture(), strict: true);
    }

    [Fact]
    public void Played_cards_leave_full_hand_before_immediate_and_fenxian_draws()
    {
        var room = CreateRoom();
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        SetHand(player, new("common-22", 0), new("common-01", 0), new("common-02", 0), new("common-03", 0), new("common-04", 0));
        var drawCard = player.Combat.Deck.Hand[0];

        room.PlayCards(player.PlayerId, player.Pve!.BattleId, "test-monster", [drawCard.InstanceId], room.Revision, Now);

        Assert.Equal(5, player.Combat.Deck.Hand.Count);
        Assert.DoesNotContain(drawCard, player.Combat.Deck.Hand);
        Assert.Contains(drawCard, player.Combat.Deck.Discard);
        var fireCards = player.Combat.Deck.Hand.Take(3).Select(card => card.InstanceId).ToArray();
        var result = room.PlayCards(player.PlayerId, player.Pve.BattleId, "test-monster", fireCards, room.Revision, Now);
        Assert.Equal(3, player.Combat.Deck.Hand.Count);
        Assert.Equal(1, result.ImmediateDraw);
        Assert.Equal(1, player.Combat.FenxianCombo);
    }

    [Fact]
    public void Ordinary_damage_does_not_reset_monster_charge_and_stun_preview_uses_diminishing_window()
    {
        var room = CreateRoom();
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        var monster = player.Pve!.Monsters[0];
        monster.SetRuntimeState(0, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(.4), true, 2,
            TimeSpan.Zero, new Dictionary<string, TimeSpan>());
        SetHand(player, new CardSetup("common-11", 0));
        room.PlayCards(player.PlayerId, player.Pve.BattleId, monster.MonsterId,
            [player.Combat.Deck.Hand[0].InstanceId], room.Revision, Now);
        Assert.True(monster.IsCharging);
        Assert.Equal(TimeSpan.FromSeconds(.4), monster.WindupRemaining);
        room.DrainCombatFeedback();

        foreach (var duration in new[] { .8, .4, 0 })
        {
            SetHand(player, new CardSetup("common-19", 0));
            var selected = new[] { player.Combat.Deck.Hand[0].InstanceId };
            var preview = room.PreviewCards(player.PlayerId, player.Pve.BattleId, monster.MonsterId, selected, room.Revision, Now);
            var actual = room.PlayCards(player.PlayerId, player.Pve.BattleId, monster.MonsterId, selected, room.Revision, Now);
            Assert.Equal(duration, actual.StunSeconds, 6);
            Assert.Equal(preview.StunSeconds, actual.StunSeconds);
        }
    }

    [Fact]
    public void Pure_draw_speed_card_has_an_authoritative_nonempty_preview_without_mutating_the_buff()
    {
        var room = CreateRoom();
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        SetHand(player, new CardSetup("common-18", 0));
        var selected = new[] { player.Combat.Deck.Hand[0].InstanceId };
        var before = room.Capture();
        var preview = room.PreviewCards(player.PlayerId, player.Pve!.BattleId, "test-monster", selected, room.Revision, Now);
        Assert.Equal(8, preview.DrawSpeedSeconds);
        Assert.Equal(-.15, preview.DrawSpeedModifier);
        Assert.Equal(0, preview.DrawBlockSpeedSeconds);
        Assert.Equal(0, preview.Damage);
        Assert.Equivalent(before, room.Capture(), strict: true);
        var actual = room.PlayCards(player.PlayerId, player.Pve.BattleId, "test-monster", selected, room.Revision, Now);
        Assert.Equivalent(preview with { RoomRevision = actual.RoomRevision }, actual, strict: true);
        Assert.Equal(8, player.Combat.DrawSpeedRemaining.TotalSeconds);
        Assert.Equal(3.4, player.Combat.DrawIntervalSeconds, 6);
    }

    [Fact]
    public void Priest_block_converts_to_self_timed_speed_in_pve_and_blocks_opponent_in_pvp()
    {
        var room = CreateRoom(HeroClass.Priest);
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        player.Combat.TakeDamage(40);
        SetHand(player, new CardSetup("common-20", 0));
        var preview = room.PreviewCards(player.PlayerId, player.Pve!.BattleId, "test-monster",
            [player.Combat.Deck.Hand[0].InstanceId], room.Revision, Now);
        Assert.Equal(1.908, preview.DrawBlockSpeedSeconds, 6);
        Assert.Equal(0, preview.DrawSpeedSeconds);
        Assert.Equal(TimeSpan.Zero, player.Combat.DrawBlockSpeedRemaining);
        var pve = room.PlayCards(player.PlayerId, player.Pve!.BattleId, "test-monster",
            [player.Combat.Deck.Hand[0].InstanceId], room.Revision, Now);
        Assert.Equal(0, pve.DrawBlockSeconds);
        Assert.Equal(1.908, pve.DrawBlockSpeedSeconds, 6);
        Assert.Equal(1.908, player.Combat.DrawBlockSpeedRemaining.TotalSeconds, 6);
        var frozenSpeed = player.Combat.DrawBlockSpeedRemaining;

        var opponentId = Guid.NewGuid();
        room.AddPlayer(new(opponentId, HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null));
        var duel = room.StartDuel(player.PlayerId, opponentId, Now);
        Assert.Equal(TimeSpan.Zero, player.Combat.DrawBlockSpeedRemaining);
        SetHand(player, new CardSetup("common-20", 0));
        var pvp = room.PlayCards(player.PlayerId, duel.DuelId, opponentId.ToString("D"),
            [player.Combat.Deck.Hand[0].InstanceId], room.Revision, Now.AddSeconds(1));
        Assert.Equal(3.816, pvp.DrawBlockSeconds, 6);
        Assert.Equal(0, pvp.DrawBlockSpeedSeconds);
        Assert.Equal(3.816, room.GetPlayer(opponentId).Combat.DrawBlockRemaining.TotalSeconds, 6);
        room.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave);
        Assert.Equal(frozenSpeed, player.Combat.DrawBlockSpeedRemaining);
    }

    [Fact]
    public void Every_monster_kill_adds_exactly_one_card_to_discard_and_dead_target_cannot_be_farmed()
    {
        var room = CreateRoom(monsters: [Monster("fire-bat-a", 1), Monster("fire-bat-b", 100)]);
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        SetHand(player, new("common-11", 0), new("common-12", 0));
        room.PlayCards(player.PlayerId, player.Pve!.BattleId, "fire-bat-a", [player.Combat.Deck.Hand[0].InstanceId], room.Revision, Now);

        var card = Assert.Single(player.Combat.Deck.Discard, card => card.CardId == "M-FIREBAT");
        Assert.DoesNotContain(card, player.Combat.Deck.Hand);
        var before = room.Capture();
        Assert.Throws<DomainValidationException>(() => room.PlayCards(player.PlayerId, player.Pve.BattleId, "fire-bat-a",
            [player.Combat.Deck.Hand[0].InstanceId], room.Revision, Now));
        Assert.Equivalent(before, room.Capture(), strict: true);
        Assert.Equivalent(before, BattleRoom.Restore(before, Catalog, 91).Capture(), strict: true);
    }

    [Fact]
    public void Monster_feedback_reports_actual_type_shield_hp_and_is_drained_once()
    {
        var monster = new MonsterCombatState("fire-herald", 100, 100, 0, TimeSpan.FromSeconds(4),
            [new(MonsterIntentKind.Attack, 5, CardElement.Fire)], .20);
        var room = CreateRoom(monsters: [monster]);
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        player.Combat.GainShield(2);
        room.Advance(TimeSpan.FromSeconds(4), Now);
        Assert.Empty(room.DrainCombatFeedback());
        room.Advance(TimeSpan.FromSeconds(.6), Now);

        var feedback = Assert.Single(room.DrainCombatFeedback());
        Assert.Equal("fire-herald", feedback.SourceId);
        Assert.Equal(player.PlayerId.ToString("D"), feedback.Resolution.TargetId);
        Assert.Equal(2, feedback.Resolution.ShieldDamage);
        Assert.Equal(4, feedback.Resolution.HpDamage);
        Assert.Equal(new CombatDamageSegment("Fire", 6), Assert.Single(feedback.Resolution.DamageSegments!));
        Assert.Equal(room.Revision, feedback.Resolution.RoomRevision);
        Assert.Empty(room.DrainCombatFeedback());
        Assert.Empty(BattleRoom.Restore(room.Capture(), Catalog, 13).DrainCombatFeedback());
    }

    [Fact]
    public void Combat_info_exposes_only_current_opponent_with_live_passive_and_escape_probability()
    {
        var room = CreateRoom(HeroClass.Priest);
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        player.Combat.TakeDamage(40);
        var alone = room.GetCombatInfo(player.PlayerId);
        Assert.Null(alone.Opponent);
        Assert.Null(alone.EscapeProbability);
        Assert.Equal(.40, alone.Self.Passive.HealBonus, 6);
        var opponentId = Guid.NewGuid();
        room.AddPlayer(new(opponentId, HeroClass.Guardian, Enumerable.Repeat("common-01", 20).ToArray(), null, DisplayName: "Opponent"));
        room.AddPlayer(new(Guid.NewGuid(), HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null, DisplayName: "Unrelated"));
        var duel = room.StartDuel(player.PlayerId, opponentId, Now);

        var info = room.GetCombatInfo(player.PlayerId);
        Assert.Equal(opponentId, info.Opponent!.PlayerId);
        Assert.Equal("Opponent", info.Opponent.DisplayName);
        Assert.Equal(room.RequestDuelEscape(duel.DuelId, player.PlayerId).Probability, info.EscapeProbability);
    }

    private static BattleRoom CreateRoom(HeroClass heroClass = HeroClass.Mage, IReadOnlyList<MonsterCombatState>? monsters = null)
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", Catalog, 77);
        room.AddPlayer(new(Guid.NewGuid(), heroClass, Enumerable.Repeat("common-01", 20).ToArray(),
            new(Guid.NewGuid(), null, monsters ?? [Monster("test-monster", 500)]), DisplayName: "Player"));
        return room;
    }

    private static MonsterCombatState Monster(string id, int hp) => new(id, hp, hp, 0, TimeSpan.FromSeconds(4),
        [new(MonsterIntentKind.Attack, 3, CardElement.Wood)]);

    private static void SetHand(RoomPlayerState player, params CardSetup[] cards)
    {
        player.Combat.Deck.Restore(new(cards.Select(card => new CombatCardInstance(Guid.NewGuid(), card.Id, card.Level)).ToArray(),
            Enumerable.Range(0, 20).Select(_ => new CombatCardInstance(Guid.NewGuid(), "common-01")).ToArray(), [], 0));
    }

    private sealed record CardSetup(string Id, int Level);
}
