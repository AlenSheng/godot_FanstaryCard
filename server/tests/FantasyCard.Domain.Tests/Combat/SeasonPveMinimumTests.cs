using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class SeasonPveMinimumTests
{
    [Theory]
    [InlineData(HeroClass.Mage, 70, 2)]
    [InlineData(HeroClass.Priest, 80, 2)]
    [InlineData(HeroClass.Guardian, 100, 3)]
    public void ActualIntentClockFloorsAfterResistanceAndGuardianReduction(HeroClass hero, int hp, int intentValue)
    {
        var room = Room(hero, true, new(MonsterIntentKind.Attack, intentValue, CardElement.Fire), out var player);
        room.Advance(TimeSpan.FromSeconds(.4));
        Assert.Equal(hp, player.Combat.Hp);
        room.Advance(TimeSpan.FromSeconds(.6));
        Assert.Equal(hp - 1, player.Combat.Hp);
        Assert.Equal(1, Assert.Single(room.DrainCombatFeedback()).Resolution.Damage);
        var legacy = Room(hero, false, new(MonsterIntentKind.Attack, intentValue, CardElement.Fire), out var oldPlayer);
        legacy.Advance(TimeSpan.FromSeconds(1)); legacy.Advance(TimeSpan.FromSeconds(.6));
        Assert.Equal(hp, oldPlayer.Combat.Hp);
    }

    [Fact]
    public void MinimumDirectIntentConsumesShieldBeforeHealth()
    {
        var room = Room(HeroClass.Guardian, true, new(MonsterIntentKind.Direct, 1, CardElement.None), out var player);
        player.Combat.GainShield(1);
        room.Advance(TimeSpan.FromSeconds(1)); room.Advance(TimeSpan.FromSeconds(.6));
        Assert.Equal(0, player.Combat.Shield); Assert.Equal(100, player.Combat.Hp);
        var result = Assert.Single(room.DrainCombatFeedback()).Resolution;
        Assert.Equal((1, 0), (result.ShieldDamage, result.HpDamage));
    }

    [Theory]
    [InlineData(MonsterIntentKind.Shield, 5)]
    [InlineData(MonsterIntentKind.Empower, 3)]
    [InlineData(MonsterIntentKind.Charge, 0)]
    [InlineData(MonsterIntentKind.Attack, 0)]
    public void UtilityOrZeroBaseIntentDoesNotCreateDamage(MonsterIntentKind kind, int value)
    {
        var room = Room(HeroClass.Guardian, true, new(kind, value, CardElement.Fire), out var player);
        room.Advance(TimeSpan.FromSeconds(1));
        room.Advance(TimeSpan.FromSeconds(kind is MonsterIntentKind.Empower or MonsterIntentKind.Charge ? 1.2 : .6));
        Assert.Equal(100, player.Combat.Hp);
        Assert.All(room.DrainCombatFeedback(), entry => Assert.Equal(0, entry.Resolution.Damage));
    }

    [Fact]
    public void CancelledWindupAndStunnedMonsterDoNotReceiveTheFloor()
    {
        var room = Room(HeroClass.Guardian, true, new(MonsterIntentKind.Attack, 2, CardElement.Fire), out var player);
        room.Advance(TimeSpan.FromSeconds(.4));
        player.Pve!.Monsters[0].ApplyStun(TimeSpan.FromSeconds(.2));
        room.Advance(TimeSpan.FromSeconds(.6));
        Assert.Equal(100, player.Combat.Hp); Assert.Empty(room.DrainCombatFeedback());
    }

    [Fact]
    public void MissImmuneAndDeadTargetHaveNoDamageAndInvalidNegativeInputIsRejected()
    {
        var state = new PlayerCombatState(HeroClass.Guardian, SeasonFenxianTests.Starter(HeroClass.Guardian), new Random(73));
        var intent = new MonsterIntentState(MonsterIntentKind.Attack, 2, CardElement.Fire);
        Assert.Equal(0, state.ResolvePveIntentDamage(0, intent, true, hit: false));
        Assert.Equal(0, state.ResolvePveIntentDamage(0, intent, true, immune: true));
        Assert.Throws<DomainValidationException>(() => state.ResolvePveIntentDamage(-1, intent, true));
        state.MarkDead(); Assert.Equal(0, state.ResolvePveIntentDamage(0, intent, true));
    }

    [Fact]
    public void SeasonalPvpStillAllowsDamageToFloorToZero()
    {
        var room = Room(HeroClass.Mage, true, new(MonsterIntentKind.Attack, 2, CardElement.Fire), out var attacker);
        var target = room.AddPlayer(new(Guid.NewGuid(), HeroClass.Guardian, SeasonFenxianTests.Starter(HeroClass.Guardian), null,
            Equipment: Equipment()));
        var now = DateTimeOffset.UnixEpoch;
        var duel = room.StartDuel(attacker.PlayerId, target.PlayerId, now);
        SeasonFenxianTests.SetHand(attacker, "C02");
        var result = room.PlayCards(attacker.PlayerId, duel.DuelId, target.PlayerId.ToString("D"),
            attacker.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray(), room.Revision, now, room.NewCombatActionId(attacker.PlayerId));
        Assert.Equal(0, result.Damage); Assert.Equal(100, target.Combat.Hp);
    }

    [Fact]
    public void APositiveEmpoweredBaseCountsAsOneHitEvenWhenThePrintedBaseIsZero()
    {
        var room = Room(HeroClass.Guardian, true, new(MonsterIntentKind.Attack, 0, CardElement.Fire), out var player);
        var monster = player.Pve!.Monsters[0];
        monster.SetRuntimeState(0, TimeSpan.Zero, TimeSpan.Zero, true, 1, TimeSpan.Zero, new Dictionary<string, TimeSpan>());
        room.Advance(TimeSpan.FromSeconds(1)); room.Advance(TimeSpan.FromSeconds(.6));
        Assert.Equal(99, player.Combat.Hp);
        Assert.False(monster.IsCharging); Assert.Equal(0, monster.EmpowerBonus);
        Assert.Equal(1, Assert.Single(room.DrainCombatFeedback()).Resolution.Damage);
    }

    [Fact]
    public void SavedSeasonPoliciesRemainEnabledAndLegacyMissingNumericsRemainLegacy()
    {
        var room = Room(HeroClass.Guardian, true, new(MonsterIntentKind.Attack, 3, CardElement.Fire), out var player);
        var restored = BattleRoom.Restore(room.Capture(), CombatCardCatalog.CreatePrototype(), 999);
        restored.Advance(TimeSpan.FromSeconds(1)); restored.Advance(TimeSpan.FromSeconds(.6));
        Assert.Equal(99, restored.GetPlayer(player.PlayerId).Combat.Hp);
        var legacy = Room(HeroClass.Guardian, false, new(MonsterIntentKind.Attack, 3, CardElement.Fire), out _);
        Assert.False(BattleRoom.Restore(legacy.Capture() with { Numerics = null }, CombatCardCatalog.CreatePrototype(), 73).Numerics.PvePositiveMinimum);
    }

    private static CombatEquipmentProfile Equipment() => new(new(FireResistance: .60), BulwarkDamageReduction: .35);
    private static BattleRoom Room(HeroClass hero, bool seasonal, MonsterIntentState intent, out RoomPlayerState player)
    {
        var context = seasonal ? new SeasonContext("season", 0, "season-v1", GameConfigCatalog.Current.Version, "stats") : null;
        var room = new BattleRoom(Guid.NewGuid(), context?.ConfigVersion ?? "legacy", CombatCardCatalog.CreatePrototype(), 73, season: context);
        var cards = SeasonFenxianTests.Starter(hero); SeasonFenxianTests.ValidateDeck(hero, cards);
        player = room.AddPlayer(new(Guid.NewGuid(), hero, cards,
            new PveBattleState(Guid.NewGuid(), "minimum-target", [new MonsterCombatState("minimum-target", 1000, 1000, 0,
                TimeSpan.FromSeconds(1), [intent], .10)]), Equipment: Equipment()));
        return room;
    }
}
