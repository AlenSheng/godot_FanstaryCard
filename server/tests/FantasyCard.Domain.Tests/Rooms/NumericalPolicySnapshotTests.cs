using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class NumericalPolicySnapshotTests
{
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();
    private static readonly DateTimeOffset Now = DateTimeOffset.UnixEpoch.AddSeconds(10);

    [Fact]
    public void Room_restore_keeps_both_saved_policies_instead_of_constructor_defaults()
    {
        var room = CreateRoom(HeroClass.Mage);
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        player.Combat.Restore(player.Combat.Capture() with
        {
            FenxianPolicy = FenxianImmediateDrawPolicy.CoreCardsSpent,
            GuardianPolicy = GuardianShieldBonusPolicy.FractionalRemainder
        });
        var snapshot = room.Capture();
        var restored = BattleRoom.Restore(snapshot, Catalog, 999);
        var combat = restored.GetPlayer(player.PlayerId).Combat;
        Assert.Equal(FenxianImmediateDrawPolicy.CoreCardsSpent, combat.FenxianDrawPolicy);
        Assert.Equal(GuardianShieldBonusPolicy.FractionalRemainder, combat.GuardianShieldPolicy);
        Assert.Equivalent(snapshot, restored.Capture(), strict: true);
    }

    [Fact]
    public void Candidate_mage_preview_and_play_agree_after_room_restore()
    {
        var room = CreateRoom(HeroClass.Mage);
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        player.Combat.Restore(player.Combat.Capture() with
        {
            FenxianPolicy = FenxianImmediateDrawPolicy.CoreCardsSpent,
            FenxianCombo = 4,
            LastFenxianCore = CardElement.Fire
        });
        SetHand(player, "common-01");
        var selected = new[] { player.Combat.Deck.Hand[0].InstanceId };
        var before = room.Capture();
        var preview = room.PreviewCards(player.PlayerId, player.Pve!.BattleId, "test-monster", selected, room.Revision, Now);
        Assert.Equivalent(before, room.Capture(), strict: true);
        var actual = room.PlayCards(player.PlayerId, player.Pve.BattleId, "test-monster", selected, room.Revision, Now);
        Assert.Equal(0, actual.ImmediateDraw);
        Assert.Equivalent(preview with { RoomRevision = actual.RoomRevision }, actual, strict: true);
    }

    [Fact]
    public void Guardian_room_preview_preserves_live_remainder_and_matches_committed_gain()
    {
        var room = CreateRoom(HeroClass.Guardian);
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        player.Combat.Restore(player.Combat.Capture() with
        {
            GuardianPolicy = GuardianShieldBonusPolicy.FractionalRemainder,
            GuardianShieldRemainderTenths = 8
        });
        SetHand(player, "common-17");
        var selected = new[] { player.Combat.Deck.Hand[0].InstanceId };
        var before = room.Capture();
        var preview = room.PreviewCards(player.PlayerId, player.Pve!.BattleId, "test-monster", selected, room.Revision, Now);
        Assert.Equivalent(before, room.Capture(), strict: true);
        var actual = room.PlayCards(player.PlayerId, player.Pve.BattleId, "test-monster", selected, room.Revision, Now);
        Assert.Equal(9, actual.ShieldGain); // floor(5 * 1.45) + floor((14 + 8) / 10)
        Assert.Equal(2, player.Combat.GuardianShieldRemainderTenths);
        Assert.Equivalent(preview with { RoomRevision = actual.RoomRevision }, actual, strict: true);
    }

    [Fact]
    public void Survived_duel_restores_pve_remainder_and_policy()
    {
        var room = CreateRoom(HeroClass.Guardian);
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        player.Combat.Restore(player.Combat.Capture() with
        {
            GuardianPolicy = GuardianShieldBonusPolicy.FractionalRemainder,
            GuardianShieldRemainderTenths = 4
        });
        var opponent = Guid.NewGuid();
        room.AddPlayer(new(opponent, HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null));
        var before = player.Combat.Capture();
        var duel = room.StartDuel(player.PlayerId, opponent, Now);
        player.Combat.CommitGuardianShieldRemainder(8);
        var restored = BattleRoom.Restore(room.Capture(), Catalog, 333);
        restored.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave);
        Assert.Equivalent(before, restored.GetPlayer(player.PlayerId).Combat.Capture(), strict: true);
    }

    [Fact]
    public void Json_roundtrip_keeps_policy_and_zero_missing_fields_resolve_to_legacy()
    {
        var state = new PlayerCombatState(HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), new Random(3),
            fenxianImmediateDrawPolicy: FenxianImmediateDrawPolicy.CoreCardsSpent);
        var snapshot = state.Capture();
        var roundtrip = JsonSerializer.Deserialize<PlayerCombatSnapshot>(JsonSerializer.Serialize(snapshot));
        Assert.NotNull(roundtrip);
        state.Restore(roundtrip!);
        Assert.Equal(FenxianImmediateDrawPolicy.CoreCardsSpent, state.FenxianDrawPolicy);
        state.Restore(snapshot with { FenxianPolicy = 0, GuardianPolicy = 0 });
        Assert.Equal(FenxianImmediateDrawPolicy.CurrentRhythm, state.FenxianDrawPolicy);
        Assert.Equal(GuardianShieldBonusPolicy.CurrentSteps, state.GuardianShieldPolicy);
    }

    [Fact]
    public void Invalid_policy_or_remainder_is_rejected_before_any_state_mutation()
    {
        var state = new PlayerCombatState(HeroClass.Guardian, Enumerable.Repeat("common-01", 20).ToArray(), new Random(3));
        var before = state.Capture();
        Assert.Throws<DomainValidationException>(() => state.Restore(before with { Hp = 1, GuardianShieldRemainderTenths = 10 }));
        Assert.Equivalent(before, state.Capture(), strict: true);
        Assert.Throws<DomainValidationException>(() => state.Restore(before with { Hp = 1, FenxianPolicy = (FenxianImmediateDrawPolicy)999 }));
        Assert.Equivalent(before, state.Capture(), strict: true);
    }

    [Fact]
    public void Exact_integer_fill_discards_fractional_overflow()
    {
        var state = new PlayerCombatState(HeroClass.Guardian, Enumerable.Repeat("common-01", 20).ToArray(), new Random(3),
            weaponLevel: 1, guardianShieldBonusPolicy: GuardianShieldBonusPolicy.FractionalRemainder);
        state.GainShield(48);
        var draft = state.PreviewShield(1);
        Assert.Equal(2, draft.Shield);
        Assert.Equal(0, draft.RemainderTenthsAfter);
    }

    [Fact]
    public void Repeated_preview_invalid_play_and_already_spent_cards_cannot_commit_remainder()
    {
        var room = CreateRoom(HeroClass.Guardian);
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        player.Combat.Restore(player.Combat.Capture() with
        {
            GuardianPolicy = GuardianShieldBonusPolicy.FractionalRemainder,
            GuardianShieldRemainderTenths = 8
        });
        SetHand(player, "common-17");
        var selected = new[] { player.Combat.Deck.Hand[0].InstanceId };
        var before = room.Capture();
        for (var index = 0; index < 10; index++)
            room.PreviewCards(player.PlayerId, player.Pve!.BattleId, "test-monster", selected, room.Revision, Now);
        Assert.Equivalent(before, room.Capture(), strict: true);
        Assert.Throws<DomainValidationException>(() => room.PlayCards(player.PlayerId, player.Pve!.BattleId,
            "missing-target", selected, room.Revision, Now));
        Assert.Throws<DomainValidationException>(() => room.PlayCards(player.PlayerId, player.Pve!.BattleId,
            "test-monster", selected, room.Revision + 1, Now));
        Assert.Equivalent(before, room.Capture(), strict: true);
        room.PlayCards(player.PlayerId, player.Pve!.BattleId, "test-monster", selected, room.Revision, Now);
        var committed = room.Capture();
        Assert.Equal(2, player.Combat.GuardianShieldRemainderTenths);
        Assert.Throws<DomainValidationException>(() => room.PlayCards(player.PlayerId, player.Pve!.BattleId,
            "test-monster", selected, room.Revision, Now));
        Assert.Equivalent(committed, room.Capture(), strict: true);
    }

    [Fact]
    public void Zero_printed_shield_preserves_existing_remainder_without_free_shield()
    {
        var state = new PlayerCombatState(HeroClass.Guardian, Enumerable.Repeat("common-01", 20).ToArray(), new Random(3),
            weaponLevel: 1, guardianShieldBonusPolicy: GuardianShieldBonusPolicy.FractionalRemainder);
        state.Restore(state.Capture() with { GuardianShieldRemainderTenths = 8 });
        foreach (var full in new[] { false, true })
        {
            if (full) state.GainShield(50);
            var before = state.Capture();
            var preview = state.PreviewShield(0);
            Assert.Equal(0, preview.Shield);
            Assert.Null(preview.RemainderTenthsAfter);
            state.GainShield(preview.Shield);
            state.CommitGuardianShieldRemainder(preview.RemainderTenthsAfter);
            Assert.Equivalent(before, state.Capture(), strict: true);
        }
    }

    private static BattleRoom CreateRoom(HeroClass heroClass)
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", Catalog, 77);
        var monster = new MonsterCombatState("test-monster", 500, 500, 0, TimeSpan.FromSeconds(4),
            [new(MonsterIntentKind.Attack, 3, CardElement.None)]);
        room.AddPlayer(new(Guid.NewGuid(), heroClass, Enumerable.Repeat("common-01", 20).ToArray(),
            new(Guid.NewGuid(), null, [monster]), WeaponLevel: 1));
        return room;
    }

    private static void SetHand(RoomPlayerState player, params string[] ids) =>
        player.Combat.Deck.Restore(new(
            ids.Select(id => new CombatCardInstance(Guid.NewGuid(), id)).ToArray(),
            Enumerable.Range(0, 20).Select(_ => new CombatCardInstance(Guid.NewGuid(), "common-01")).ToArray(), [], 0));
}
