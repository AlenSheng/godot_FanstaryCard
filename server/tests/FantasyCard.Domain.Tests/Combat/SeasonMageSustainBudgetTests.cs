using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class SeasonMageSustainBudgetTests
{
    private static PlayerCombatState State(FenxianImmediateDrawPolicy policy = FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm) =>
        new(HeroClass.Mage, SeasonFenxianTests.Starter(HeroClass.Mage), new Random(73), 5, fenxianImmediateDrawPolicy: policy);

    [Fact]
    public void PublishedDefaultsRemainV1AndDoNotSerializeTheExperimentalSwitchOrCredit()
    {
        Assert.False(NumericalRules.SeasonV1.SeasonMageSustainBudget);
        Assert.Equal(FenxianImmediateDrawPolicy.SeasonBoundedRhythm, NumericalRules.SeasonV1.FenxianPolicy);
        Assert.DoesNotContain("SeasonMageSustainBudget", JsonSerializer.Serialize(NumericalRules.SeasonV1));
        var old = State(FenxianImmediateDrawPolicy.SeasonBoundedRhythm);
        Assert.Null(old.FenxianReturnCredit);
        Assert.DoesNotContain("FenxianReturnCredit", JsonSerializer.Serialize(old.Capture()));
        var restored = State(); restored.Restore(old.Capture());
        Assert.Equal(JsonSerializer.Serialize(old.Capture()), JsonSerializer.Serialize(restored.Capture()));
    }

    [Fact]
    public void CreditAccruesOnlyFromActiveUnblockedNaturalTimeAndCapsAtTwo()
    {
        var state = State();
        state.Restore(state.Capture() with { StunRemaining = TimeSpan.FromSeconds(2), DrawBlockRemaining = TimeSpan.FromSeconds(1),
            DrawSpeedModifier = -.5, DrawSpeedRemaining = TimeSpan.FromSeconds(8), DrawBlockSpeedRemaining = TimeSpan.FromSeconds(8) });
        state.Advance(TimeSpan.FromSeconds(4), true);
        Assert.Equal(.05, state.FenxianReturnCredit!.Value, 10);
        state.Advance(TimeSpan.FromSeconds(10), false);
        Assert.Equal(.05, state.FenxianReturnCredit!.Value, 10);
        state.Advance(TimeSpan.FromSeconds(1000), true);
        Assert.Equal(2, state.FenxianReturnCredit);
    }

    [Fact]
    public void PassiveInstantReturnsSpendSavedCreditWithoutNewTimeOrRandomDraws()
    {
        var state = State(); state.Advance(TimeSpan.FromSeconds(80), true);
        var random = state.Capture().RandomState;
        state.SetFenxian(CardElement.Water, 4, 4);
        Assert.Equal((0d, 1), state.UpdateFenxian(CardElement.Water, 2, 2));
        Assert.Equal((0d, 1), state.UpdateFenxian(CardElement.Water, 2, 2));
        Assert.Equal((0d, 0), state.UpdateFenxian(CardElement.Water, 2, 2));
        Assert.Equal(0, state.FenxianReturnCredit);
        Assert.Equal(random, state.Capture().RandomState);
    }

    [Fact]
    public void SingleCoreChargeCannotSpendMoreCreditThanElapsedTimeEarned()
    {
        var state = State(); state.Advance(TimeSpan.FromSeconds(4), true);
        Assert.Equal((.1, 0), state.UpdateFenxian(CardElement.Fire, 1, 1));
        Assert.Equal((0d, 0), state.UpdateFenxian(CardElement.Fire, 1, 1));
        Assert.Equal(0, state.FenxianReturnCredit);
    }

    [Fact]
    public void RestoringCreditReplaysExactlyAndInvalidCreditRejectsBeforeMutation()
    {
        var state = State(); state.Advance(TimeSpan.FromSeconds(32), true);
        var snapshot = state.Capture(); var copy = State(); copy.Restore(snapshot);
        state.Advance(TimeSpan.FromSeconds(8), true); copy.Advance(TimeSpan.FromSeconds(8), true);
        Assert.Equal(state.UpdateFenxian(CardElement.Fire, 2, 2), copy.UpdateFenxian(CardElement.Fire, 2, 2));
        Assert.Equal(JsonSerializer.Serialize(state.Capture()), JsonSerializer.Serialize(copy.Capture()));
        var before = JsonSerializer.Serialize(copy.Capture());
        foreach (var invalid in new double?[] { null, -1, 3, double.NaN, double.PositiveInfinity })
        {
            Assert.Throws<DomainValidationException>(() => copy.Restore(snapshot with { FenxianReturnCredit = invalid }));
            Assert.Equal(before, JsonSerializer.Serialize(copy.Capture()));
        }
    }

    [Fact]
    public void NewBattleResetsCreditButRepeatedOpeningOrRestoreCannotGrantIt()
    {
        var state = State(); state.Advance(TimeSpan.FromSeconds(40), true);
        var battle = Guid.NewGuid(); Assert.True(state.BeginBattle(battle)); Assert.Equal(0, state.FenxianReturnCredit);
        state.Advance(TimeSpan.FromSeconds(20), true); var credit = state.FenxianReturnCredit;
        Assert.False(state.BeginBattle(battle)); Assert.Equal(credit, state.FenxianReturnCredit);
        var copy = State(); copy.Restore(state.Capture()); Assert.False(copy.BeginBattle(battle)); Assert.Equal(credit, copy.FenxianReturnCredit);
    }

    [Fact]
    public void ExplicitRateIsSavedAndRestoredRatherThanReplacedByTheNewDefault()
    {
        var state = new PlayerCombatState(HeroClass.Mage, SeasonFenxianTests.Starter(HeroClass.Mage), new Random(73), weaponLevel: 5,
            fenxianImmediateDrawPolicy: FenxianImmediateDrawPolicy.SeasonRateBudgetedRhythm, fenxianReturnRateBasisPoints: 500);
        state.Advance(TimeSpan.FromSeconds(4), true);
        Assert.Equal(.05, state.FenxianReturnCredit!.Value, 10);
        var copy = State(); copy.Restore(state.Capture());
        Assert.Equal(500, copy.FenxianReturnRateBasisPoints);
        state.Advance(TimeSpan.FromSeconds(4), true); copy.Advance(TimeSpan.FromSeconds(4), true);
        Assert.Equal(JsonSerializer.Serialize(state.Capture()), JsonSerializer.Serialize(copy.Capture()));
        Assert.Equal(.1, copy.FenxianReturnCredit!.Value, 10);
    }

    [Fact]
    public void InvalidOrNonSeasonalRatesRejectWithoutChangingState()
    {
        var state = State(); var before = JsonSerializer.Serialize(state.Capture());
        foreach (var rate in new[] { -1, 0, 1001 })
        {
            Assert.Throws<DomainValidationException>(() => state.Restore(state.Capture() with { FenxianReturnRateBasisPoints = rate }));
            Assert.Equal(before, JsonSerializer.Serialize(state.Capture()));
            Assert.Throws<DomainValidationException>(() => (NumericalRules.SeasonV1 with { SeasonMageSustainBudget = true, SeasonMageReturnRateBasisPoints = rate }).Validate());
        }
        Assert.Throws<DomainValidationException>(() => (NumericalRules.SeasonV1 with { SeasonMageReturnRateBasisPoints = 500 }).Validate());
    }

    [Fact]
    public void WholeRoomSnapshotPreservesItsExplicitRateAndCredit()
    {
        var room = CandidateRoom();
        var before = JsonSerializer.Serialize(room.Capture());
        var saved = JsonSerializer.Deserialize<BattleRoomSnapshot>(before)!;
        var restored = BattleRoom.Restore(saved, CombatCardCatalog.Create(GameConfigCatalog.Current), 73);
        Assert.Equal(before, JsonSerializer.Serialize(restored.Capture()));
        Assert.Equal(500, restored.Numerics.SeasonMageReturnRateBasisPoints);
        Assert.Equal(500, Assert.Single(restored.Capture().Players).Combat.FenxianReturnRateBasisPoints);
    }

    [Fact]
    public void WholeRoomRejectsAPlayerRateThatDisagreesWithTheSavedRoomPolicy()
    {
        var snapshot = CandidateRoom().Capture();
        var wrong = snapshot with { Players = snapshot.Players.Select(p => p with
            { Combat = p.Combat with { FenxianReturnRateBasisPoints = 1000 } }).ToArray() };
        Assert.Throws<DomainValidationException>(() => BattleRoom.Restore(wrong, CombatCardCatalog.Create(GameConfigCatalog.Current), 73));
        var wrongRoom = snapshot with { Numerics = NumericalRules.SeasonV1 };
        Assert.Throws<DomainValidationException>(() => BattleRoom.Restore(wrongRoom, CombatCardCatalog.Create(GameConfigCatalog.Current), 73));
    }

    private static BattleRoom CandidateRoom()
    {
        var config = GameConfigCatalog.Current;
        var room = new BattleRoom(Guid.NewGuid(), config.Version, CombatCardCatalog.Create(config), 73,
            NumericalRules.SeasonV1 with { SeasonMageSustainBudget = true, SeasonMageReturnRateBasisPoints = 500 },
            new SeasonContext("sustain-restore", 5, "season-v1", config.Version, "season-equipment-v1"));
        room.AddPlayer(new(Guid.NewGuid(), HeroClass.Mage, SeasonFenxianTests.Starter(HeroClass.Mage), null, WeaponLevel: 5));
        return room;
    }
}
