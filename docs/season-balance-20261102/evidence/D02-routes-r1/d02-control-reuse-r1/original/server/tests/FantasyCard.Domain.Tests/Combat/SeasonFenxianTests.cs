using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class SeasonFenxianTests
{
    [Fact]
    public void SingleCoreAlwaysClearsComboAndOnlyKeepsE1Charge()
    {
        var state = State();
        state.SetFenxian(CardElement.Fire, 4, 5);
        for (var i = 0; i < 6; i++)
        {
            var result = state.UpdateFenxian(CardElement.Fire, 1, 1);
            Assert.Equal(0, result.Draw);
            Assert.Equal(.18, result.Charge, 6);
            Assert.Equal(0, state.FenxianCombo);
            Assert.Null(state.LastFenxianCore);
            Assert.Equal(1, state.FenxianChargeLevel);
        }
        state.UpdateFenxian(CardElement.Fire, 2, 2);
        Assert.Equal(1, state.FenxianCombo);
        Assert.Equal(2, state.FenxianChargeLevel);
    }

    [Fact]
    public void MultiCoreKeepsLegacyRhythmButUsesActualConsumedCountAsTheDrawCap()
    {
        var state = State();
        var draws = Enumerable.Range(0, 5).Select(_ => state.UpdateFenxian(CardElement.Fire, 2, 2).Draw).ToArray();
        Assert.Equal([0, 1, 1, 1, 1], draws);
        Assert.Equal(5, state.FenxianChargeLevel);
        Assert.Equal(2, state.UpdateFenxian(CardElement.Fire, 2, 4).Draw);
        var changed = state.UpdateFenxian(CardElement.Water, 2, 4);
        Assert.Equal(0, changed.Draw);
        Assert.Equal(1, state.FenxianCombo);
        Assert.Equal(CardElement.Water, state.LastFenxianCore);
    }

    [Theory]
    [InlineData(2, 2, 0)]
    [InlineData(3, 3, 1)]
    [InlineData(4, 4, 1)]
    [InlineData(5, 5, 2)]
    public void FirstMultiCorePlayUsesItsOldTier(int core, int spent, int draw) =>
        Assert.Equal(draw, State().UpdateFenxian(CardElement.Fire, core, spent).Draw);

    [Fact]
    public void ActualSpentCountIsRequiredAndCannotBeSmallerThanCoreOrLargerThanTheHand()
    {
        var state = State();
        var before = state.Capture();
        Assert.Throws<DomainValidationException>(() => state.UpdateFenxian(CardElement.Fire, 2));
        Assert.Throws<DomainValidationException>(() => state.UpdateFenxian(CardElement.Fire, 2, 1));
        Assert.Throws<DomainValidationException>(() => state.UpdateFenxian(CardElement.Fire, 2, 6));
        Assert.Equivalent(before, state.Capture(), strict: true);
    }

    [Fact]
    public void ExplicitDrawCardStillDrawsAndNewCardsDoNotJoinTheCurrentResolution()
    {
        var explicitDraw = GameConfigCatalog.Current.Cards.First(card => card.IsCodex && card.Enabled &&
            (card.HeroClass is null || card.HeroClass == HeroClass.Mage) && card.Effect.ImmediateDraw > 0);
        var cards = Starter(HeroClass.Mage).Where(id => id != explicitDraw.CardId).Take(19).Append(explicitDraw.CardId).ToArray();
        ValidateDeck(HeroClass.Mage, cards);
        var room = Room(out var player, cards);
        SetHand(player, explicitDraw.CardId);
        var before = room.Capture();
        var selected = player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray();
        var preview = room.PreviewCards(player.PlayerId, player.Pve!.BattleId, "season-target", selected, room.Revision, DateTimeOffset.UnixEpoch);
        Assert.Equivalent(before, room.Capture(), strict: true);
        var result = room.PlayCards(player.PlayerId, player.Pve.BattleId, "season-target", selected, room.Revision, DateTimeOffset.UnixEpoch, room.NewCombatActionId(player.PlayerId));
        Assert.Equal(explicitDraw.Effect.ImmediateDraw, result.ImmediateDraw);
        Assert.Equal(explicitDraw.Effect.ImmediateDraw, player.Combat.Deck.Hand.Count);
        Assert.Equivalent(preview with { RoomRevision = result.RoomRevision, CombatActionId = result.CombatActionId }, result, strict: true);
        Assert.Equal(20, TotalCards(player));
    }

    [Fact]
    public void MixedActualPlayCapsByAllConsumedCardsRatherThanCoreCards()
    {
        var room = Room(out var player);
        var deck = Starter(HeroClass.Mage).ToHashSet();
        var others = GameConfigCatalog.Current.Cards.Where(card => deck.Contains(card.CardId) &&
            card.Effect.ElementalDamage == 0 && card.Effect.ImmediateDraw == 0 && card.Effect.DrawCharge == 0)
            .Take(2).Select(card => card.CardId).ToArray();
        Assert.Equal(2, others.Length);
        SetHand(player, ["C01", "C02", .. others]);
        player.Combat.SetFenxian(CardElement.Fire, 4, 5);
        var result = room.PlayCards(player.PlayerId, player.Pve!.BattleId, "season-target",
            player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray(), room.Revision, DateTimeOffset.UnixEpoch, room.NewCombatActionId(player.PlayerId));
        Assert.Equal(2, result.CoreCount);
        Assert.Equal(2, result.ImmediateDraw);
        Assert.Equal(20, TotalCards(player));
    }

    [Fact]
    public void RealSingleCardPlayResetsHighComboAndSurvivesRoomAndDuelRecovery()
    {
        var room = Room(out var player);
        player.Combat.SetFenxian(CardElement.Fire, 4, 5);
        SetHand(player, "C01");
        var result = room.PlayCards(player.PlayerId, player.Pve!.BattleId, "season-target",
            player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray(), room.Revision, DateTimeOffset.UnixEpoch, room.NewCombatActionId(player.PlayerId));
        Assert.Equal(0, result.ImmediateDraw);
        Assert.Equal(0, player.Combat.FenxianCombo);
        var other = Guid.NewGuid();
        room.AddPlayer(new(other, HeroClass.Priest, Starter(HeroClass.Priest), null));
        var before = player.Combat.Capture();
        var duel = room.StartDuel(player.PlayerId, other, DateTimeOffset.UnixEpoch);
        var restored = BattleRoom.Restore(room.Capture(), CombatCardCatalog.CreatePrototype(), 73);
        restored.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave);
        Assert.Equivalent(before, restored.GetPlayer(player.PlayerId).Combat.Capture(), strict: true);
        Assert.Equal(FenxianImmediateDrawPolicy.SeasonBoundedRhythm, restored.GetPlayer(player.PlayerId).Combat.FenxianDrawPolicy);
    }

    [Fact]
    public void LegacyRoomAndCandidatePolicyStayIndependentAndSeasonSnapshotsCannotDowngrade()
    {
        var legacy = new BattleRoom(Guid.NewGuid(), "legacy", CombatCardCatalog.CreatePrototype(), 73);
        Assert.False(legacy.Numerics.SeasonMageRhythm);
        var room = Room(out var player);
        var snapshot = room.Capture();
        Assert.Throws<DomainValidationException>(() => BattleRoom.Restore(snapshot with { Numerics = NumericalRules.Legacy }, CombatCardCatalog.CreatePrototype(), 73));
        Assert.Throws<DomainValidationException>(() => BattleRoom.Restore(snapshot with
        {
            Players = snapshot.Players.Select(p => p with { Combat = p.Combat with { FenxianPolicy = FenxianImmediateDrawPolicy.CurrentRhythm } }).ToArray()
        }, CombatCardCatalog.CreatePrototype(), 73));
        Assert.Equal(0, player.Combat.FenxianCombo);
    }

    private static PlayerCombatState State() => new(HeroClass.Mage, Starter(HeroClass.Mage), new Random(73),
        fenxianImmediateDrawPolicy: FenxianImmediateDrawPolicy.SeasonBoundedRhythm);
    internal static string[] Starter(HeroClass hero)
    {
        var prefix = hero switch { HeroClass.Mage => "MAG", HeroClass.Priest => "PRI", _ => "GUA" };
        return Enumerable.Range(1, 13).Select(i => $"C{i:D2}").Concat(Enumerable.Range(1, 7).Select(i => $"{prefix}-{i:D2}")).ToArray();
    }
    internal static void ValidateDeck(HeroClass hero, string[] cards) => DeckRules.Validate(hero, cards,
        GameConfigCatalog.Current.Cards.Where(c => c.IsCodex).ToDictionary(c => c.CardId,
            c => new OwnedCard(c.CardId, c.HeroClass, (CardRarity)c.Rarity, 1, false)));
    internal static void SetHand(RoomPlayerState player, params string[] ids)
    {
        var old = player.Combat.Deck.Capture();
        var all = old.Hand.Concat(old.Library).Concat(old.Discard).ToArray();
        var hand = ids.Select(id => all.Single(c => c.CardId == id)).ToArray();
        var selected = hand.Select(c => c.InstanceId).ToHashSet();
        player.Combat.Deck.Restore(new(hand, all.Where(c => !selected.Contains(c.InstanceId)).ToArray(), [], 0));
    }
    private static int TotalCards(RoomPlayerState player)
    {
        var snapshot = player.Combat.Deck.Capture();
        return snapshot.Hand.Count + snapshot.Library.Count + snapshot.Discard.Count;
    }
    private static BattleRoom Room(out RoomPlayerState player, string[]? cards = null)
    {
        cards ??= Starter(HeroClass.Mage);
        ValidateDeck(HeroClass.Mage, cards);
        var context = new SeasonContext("season", 0, "season-v1", GameConfigCatalog.Current.Version, "stats");
        var room = new BattleRoom(Guid.NewGuid(), context.ConfigVersion, CombatCardCatalog.CreatePrototype(), 73, season: context);
        player = room.AddPlayer(new(Guid.NewGuid(), HeroClass.Mage, cards,
            new PveBattleState(Guid.NewGuid(), "season-target", [new MonsterCombatState("season-target", 1000, 1000, 0,
                TimeSpan.FromSeconds(10), [new(MonsterIntentKind.Attack, 2, CardElement.Fire)])])));
        return room;
    }
}
