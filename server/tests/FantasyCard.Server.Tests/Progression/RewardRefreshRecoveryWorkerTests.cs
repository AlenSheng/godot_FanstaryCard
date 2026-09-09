using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Progression;

namespace FantasyCard.Server.Tests.Progression;

public sealed class RewardRefreshRecoveryWorkerTests
{
    [Fact]
    public void FindReceipt_UsesPlayerAndRequestIdentity()
    {
        var catalog = new CombatCardCatalog([new("test-hit", new CombatCardEffect(DirectDamage: 10000))]);
        var room = new BattleRoom(Guid.NewGuid(), "test", catalog, 73);
        var playerId = Guid.NewGuid();
        room.AddPlayer(new(playerId, HeroClass.Mage, Enumerable.Repeat("test-hit", 20).ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(73, 1));
        var player = room.GetPlayer(playerId);
        foreach (var monster in player.Pve!.Monsters.ToArray())
        {
            if (player.Combat.Deck.Hand.Count == 0) player.Combat.DrawImmediate(1);
            room.PlayCards(playerId, player.Pve.BattleId, monster.MonsterId,
                [player.Combat.Deck.Hand[0].InstanceId], room.Revision, DateTimeOffset.UnixEpoch);
        }
        var receipt = room.RefreshRewardChoice(playerId, room.Revision, 60, "refresh-recovery-01");
        var snapshot = room.Capture();

        Assert.Equivalent(receipt,
            RewardRefreshRecoveryWorker.FindReceipt(snapshot, playerId, "refresh-recovery-01"), strict: true);
        Assert.Null(RewardRefreshRecoveryWorker.FindReceipt(snapshot, playerId, "another-request"));
        Assert.Null(RewardRefreshRecoveryWorker.FindReceipt(snapshot, Guid.NewGuid(), "refresh-recovery-01"));
        Assert.Null(RewardRefreshRecoveryWorker.FindReceipt(null, playerId, "refresh-recovery-01"));
    }
}
