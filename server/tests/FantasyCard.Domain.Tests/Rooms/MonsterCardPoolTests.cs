using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class MonsterCardPoolTests
{
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();

    [Fact]
    public void Accept_adds_only_to_discard_and_replay_does_not_add_cards()
    {
        var deck = Deck();
        var pool = new MonsterCardPool();
        var card = Monster();
        pool.Offer("kill-a", card);
        pool.Offer("kill-a", Monster());
        Assert.Single(pool.Pending);
        var hand = deck.Hand.ToArray();
        pool.Decide(deck, 5, "choose-a", card.InstanceId, true, null);
        pool.Decide(deck, 5, "choose-a", card.InstanceId, true, null);
        Assert.Equal(21, Count(deck));
        Assert.Contains(card, deck.Discard);
        Assert.Equal(hand, deck.Hand);
        Assert.Single(pool.Active);
        Assert.Empty(pool.Pending);
        Assert.Throws<DomainValidationException>(() => pool.Decide(deck, 5, "choose-a", card.InstanceId, false, null));
    }

    [Fact]
    public void Full_pool_requires_monster_replacement_and_never_removes_base_card()
    {
        var deck = Deck(); var pool = new MonsterCardPool();
        var first = Monster(); var second = Monster();
        pool.Offer("a", first); pool.Decide(deck, 1, "a", first.InstanceId, true, null);
        pool.Offer("b", second);
        var before = deck.Capture();
        Assert.Throws<DomainValidationException>(() => pool.Decide(deck, 1, "full", second.InstanceId, true, null));
        Assert.Throws<DomainValidationException>(() => pool.Decide(deck, 1, "base", second.InstanceId, true, deck.Hand[0].InstanceId));
        Assert.Equivalent(before, deck.Capture(), strict: true);
        pool.Decide(deck, 1, "replace", second.InstanceId, true, first.InstanceId);
        Assert.Equal(21, Count(deck));
        Assert.DoesNotContain(first, deck.Hand.Concat(deck.Library).Concat(deck.Discard));
        Assert.Contains(second, deck.Discard);
    }

    [Fact]
    public void Replacement_from_hand_does_not_draw_a_compensation_card()
    {
        var deck = Deck(); var pool = new MonsterCardPool(); var first = Monster();
        pool.Offer("a", first); pool.Decide(deck, 1, "a", first.InstanceId, true, null);
        var snapshot = deck.Capture();
        deck.Restore(snapshot with { Hand = snapshot.Hand.Append(first).ToArray(), Discard = [] });
        var second = Monster(); pool.Offer("b", second);
        var beforeCount = deck.Hand.Count;
        pool.Decide(deck, 1, "b", second.InstanceId, true, first.InstanceId);
        Assert.Equal(beforeCount - 1, deck.Hand.Count);
        Assert.Equal(21, Count(deck));
    }

    [Fact]
    public void Skip_gives_no_resource_and_snapshot_roundtrips_receipts_and_provenance()
    {
        var deck = Deck(); var pool = new MonsterCardPool(); var card = Monster();
        pool.Offer("kill", card); pool.Decide(deck, 5, "skip", card.InstanceId, false, null);
        Assert.Equal(20, Count(deck));
        var restored = new MonsterCardPool(); restored.Restore(pool.Capture(), deck, 5);
        restored.Offer("kill", Monster());
        Assert.Empty(restored.Pending);
        Assert.True(restored.IsReplay("skip", card.InstanceId, false, null));
    }

    [Fact]
    public void Current_room_still_grants_monster_cards_automatically()
    {
        var room = Room(NumericalRules.Legacy); var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        Kill(room, player);
        Assert.Equal(21, Count(player.Combat.Deck));
        Assert.Empty(player.MonsterPool.Pending);
    }

    [Fact]
    public void Candidate_kill_offer_survives_room_restore_and_only_owner_can_accept_after_combat()
    {
        var room = Room(new(OptionalMonsterPool: true)); var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        Kill(room, player);
        var offer = Assert.Single(player.MonsterPool.Pending);
        Assert.Equal(20, Count(player.Combat.Deck));
        Assert.Equal(RoomPlayerPhase.Choice, player.Phase);
        var restored = BattleRoom.Restore(room.Capture(), Catalog, 1);
        Assert.True(restored.Numerics.OptionalMonsterPool);
        Assert.Throws<DomainValidationException>(() => restored.DecideMonsterCard(Guid.NewGuid(), offer.InstanceId, true, null, "bad", restored.Revision));
        var revision = restored.DecideMonsterCard(player.PlayerId, offer.InstanceId, true, null, "ok", restored.Revision);
        Assert.Equal(revision, restored.DecideMonsterCard(player.PlayerId, offer.InstanceId, true, null, "ok", 0));
        Assert.Equal(21, Count(restored.GetPlayer(player.PlayerId).Combat.Deck));
    }

    [Fact]
    public void Candidate_cannot_be_accepted_during_combat_or_after_leaving_the_cell()
    {
        var room = Room(new(OptionalMonsterPool: true)); var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        var card = Monster(); player.MonsterPool.Offer("test-offer", card);
        Assert.Throws<DomainValidationException>(() => room.DecideMonsterCard(player.PlayerId, card.InstanceId, true, null, "battle", room.Revision));
        player.MonsterPool.DiscardPending();
        Assert.Throws<DomainValidationException>(() => player.MonsterPool.Decide(player.Combat.Deck, 5, "expired", card.InstanceId, true, null));
    }

    [Fact]
    public void Run_end_removes_only_active_monsters()
    {
        var deck = Deck(); var pool = new MonsterCardPool(); var card = Monster();
        pool.Offer("kill", card); pool.Decide(deck, 5, "ok", card.InstanceId, true, null);
        pool.EndRun(deck);
        Assert.Equal(20, Count(deck)); Assert.Empty(pool.Active); Assert.Empty(pool.Pending);
    }

    private static CombatDeck Deck() => CombatDeck.Create(Enumerable.Repeat("common-01", 20).ToArray(), new Random(31));
    private static CombatCardInstance Monster() => new(Guid.NewGuid(), "M-FIREBAT");
    private static int Count(CombatDeck deck) => deck.Hand.Count + deck.Library.Count + deck.Discard.Count;
    private static BattleRoom Room(NumericalRules rules)
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", Catalog, 31, rules);
        room.AddPlayer(new(Guid.NewGuid(), HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(31, 1));
        return room;
    }
    private static void Kill(BattleRoom room, RoomPlayerState player)
    {
        var target = player.Pve!.Monsters[0];
        target.TakeDamage(target.Hp + target.Shield - 1);
        foreach (var other in player.Pve.Monsters.Skip(1)) other.TakeDamage(other.Hp + other.Shield);
        room.PlayCards(player.PlayerId, player.Pve.BattleId, target.MonsterId,
            [player.Combat.Deck.Hand[0].InstanceId], room.Revision, DateTimeOffset.UnixEpoch);
    }
}
