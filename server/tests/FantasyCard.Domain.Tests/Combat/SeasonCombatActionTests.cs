using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class SeasonCombatActionTests
{
    [Fact]
    public void SuccessfulPlaysRequire500RoomMillisecondsAndCannotUseWallClockToBypassIt()
    {
        var room = Room(out var player);
        Play(room, player, "C01");
        var id = room.NewCombatActionId(player.PlayerId);
        SeasonFenxianTests.SetHand(player, "C02");
        var ids = player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray();
        Assert.Throws<DomainValidationException>(() => room.PlayCards(player.PlayerId, player.Pve!.BattleId, "action-target", ids, room.Revision, DateTimeOffset.MaxValue, id));
        room.Advance(TimeSpan.FromMilliseconds(499));
        Assert.Equal(1, room.GetCombatActionStatus(player.PlayerId).RemainingMs);
        Assert.Throws<DomainValidationException>(() => room.PlayCards(player.PlayerId, player.Pve!.BattleId, "action-target", ids, room.Revision, DateTimeOffset.MaxValue, id));
        room.Advance(TimeSpan.FromMilliseconds(1));
        room.PlayCards(player.PlayerId, player.Pve!.BattleId, "action-target", ids, room.Revision, DateTimeOffset.MinValue, id);
        Assert.Equal(3, room.GetCombatActionStatus(player.PlayerId).NextSequence);
        Assert.Equal(500, room.GetCombatActionStatus(player.PlayerId).RemainingMs);
    }

    [Fact]
    public void RejectionsDoNotConsumeTheActionSequenceOrChangeState()
    {
        var room = Room(out var player); SeasonFenxianTests.SetHand(player, "C01");
        var before = room.Capture(); var id = room.NewCombatActionId(player.PlayerId);
        var ids = player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray();
        Assert.Throws<DomainValidationException>(() => room.PlayCards(player.PlayerId, player.Pve!.BattleId, "wrong-target", ids, room.Revision, DateTimeOffset.UnixEpoch, id));
        Assert.Throws<DomainValidationException>(() => room.PlayCards(player.PlayerId, player.Pve!.BattleId, "action-target", ids, room.Revision + 100, DateTimeOffset.UnixEpoch, id));
        Assert.Equivalent(before, room.Capture(), strict: true);
        room.PlayCards(player.PlayerId, player.Pve!.BattleId, "action-target", ids, room.Revision, DateTimeOffset.UnixEpoch, id);
        Assert.Equal(2, room.GetCombatActionStatus(player.PlayerId).NextSequence);
    }

    [Fact]
    public void PreviewDuringCooldownIsPureAndDoesNotConsumeTheNextId()
    {
        var room = Room(out var player); Play(room, player, "C01");
        SeasonFenxianTests.SetHand(player, "C02"); var before = room.Capture();
        for (var i = 0; i < 3; i++)
            room.PreviewCards(player.PlayerId, player.Pve!.BattleId, "action-target", player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray(), room.Revision, DateTimeOffset.UnixEpoch);
        Assert.Equivalent(before, room.Capture(), strict: true);
        Assert.Equal(2, room.GetCombatActionStatus(player.PlayerId).NextSequence);
    }

    [Fact]
    public void ReplayReturnsTheOriginalOutcomeAndRejectsChangedPayloadOrNonce()
    {
        var room = Room(out var player); SeasonFenxianTests.SetHand(player, "C01");
        var battle = player.Pve!.BattleId; var ids = player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray();
        var id = room.NewCombatActionId(player.PlayerId);
        var original = room.PlayCards(player.PlayerId, battle, "action-target", ids, room.Revision, DateTimeOffset.UnixEpoch, id);
        var before = room.Capture();
        var replay = room.PlayCards(player.PlayerId, battle, "action-target", ids, long.MaxValue, DateTimeOffset.MaxValue, id);
        Assert.Equivalent(original with { ActionReplayed = true }, replay, strict: true);
        Assert.Equivalent(before, room.Capture(), strict: true);
        Assert.Throws<DomainValidationException>(() => room.PlayCards(player.PlayerId, battle, "other", ids, room.Revision, DateTimeOffset.UnixEpoch, id));
        Assert.Throws<DomainValidationException>(() => room.PlayCards(player.PlayerId, battle, "action-target", ids, room.Revision, DateTimeOffset.UnixEpoch, "1:" + Guid.NewGuid().ToString("N")));
    }

    [Fact]
    public void JsonRecoveryKeepsBothCooldownAndReplayLedger()
    {
        var room = Room(out var player); var original = Play(room, player, "C01");
        var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, Converters = { new JsonStringEnumConverter() } };
        var snapshot = JsonSerializer.Deserialize<BattleRoomSnapshot>(JsonSerializer.Serialize(room.Capture(), options), options)!;
        var restored = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), 999);
        Assert.Equal(500, restored.GetCombatActionStatus(player.PlayerId).RemainingMs);
        var receipt = Assert.Single(snapshot.Players[0].CombatActions!);
        var replay = restored.ReplayCombatAction(player.PlayerId, receipt.ActionId, original.BattleId, original.TargetId,
            player.Combat.Deck.Capture().Discard.Where(c => c.CardId == "C01").Select(c => c.InstanceId).ToArray());
        Assert.True(replay.ActionReplayed);
        var corrupted = snapshot with { Players = snapshot.Players.Select(p => p with { LastSuccessfulCombatAt = TimeSpan.FromSeconds(1) }).ToArray() };
        Assert.Throws<DomainValidationException>(() => BattleRoom.Restore(corrupted, CombatCardCatalog.CreatePrototype(), 73));
    }

    [Fact]
    public void ResultEvictionDoesNotAllowAnyOldIdToExecuteAgain()
    {
        var room = Room(out var player);
        CombatResolution? first = null; Guid[] firstIds = [];
        for (var i = 0; i < 65; i++)
        {
            SeasonFenxianTests.SetHand(player, "C01");
            if (i == 0) firstIds = player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray();
            var result = Play(room, player, "C01");
            first ??= result;
            if (i < 64) room.Advance(TimeSpan.FromMilliseconds(500));
        }
        var before = room.Capture();
        Assert.Equal(64, before.Players[0].CombatActions!.Count);
        Assert.Throws<CombatActionAlreadyAppliedException>(() => room.PlayCards(player.PlayerId, first!.BattleId,
            "action-target", firstIds, room.Revision, DateTimeOffset.UnixEpoch, first.CombatActionId));
        Assert.Equivalent(before, room.Capture(), strict: true);
        Assert.Equal(66, room.GetCombatActionStatus(player.PlayerId).NextSequence);
    }

    [Fact]
    public void DuelTransitionsAndTerminalStateDoNotResetAnAcceptedAction()
    {
        var room = Room(out var player); var result = Play(room, player, "C01");
        var receipt = Assert.Single(room.Capture().Players[0].CombatActions!);
        var ids = player.Combat.Deck.Capture().Discard.Where(c => c.CardId == "C01").Select(c => c.InstanceId).ToArray();
        var other = room.AddPlayer(new(Guid.NewGuid(), HeroClass.Priest, SeasonFenxianTests.Starter(HeroClass.Priest), null));
        var duel = room.StartDuel(player.PlayerId, other.PlayerId, DateTimeOffset.UnixEpoch);
        Assert.Equal(500, room.GetCombatActionStatus(player.PlayerId).RemainingMs);
        room.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave);
        room.AbandonBattle(player.PlayerId);
        Assert.True(room.ReplayCombatAction(player.PlayerId, receipt.ActionId, result.BattleId, result.TargetId, ids).ActionReplayed);
    }

    [Fact]
    public void LegacyRoomStillAcceptsOriginalCommandsWithoutActionIds()
    {
        var room = Room(out var player, false);
        Play(room, player, "C01"); Play(room, player, "C02");
        Assert.Equal(0, room.Capture().Players[0].LastCombatActionSequence);
    }

    internal static CombatResolution Play(BattleRoom room, RoomPlayerState player, string card)
    {
        SeasonFenxianTests.SetHand(player, card);
        return room.PlayCards(player.PlayerId, player.Pve!.BattleId, "action-target",
            player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray(), room.Revision, DateTimeOffset.UnixEpoch,
            room.Season is null ? null : room.NewCombatActionId(player.PlayerId));
    }
    internal static BattleRoom Room(out RoomPlayerState player, bool seasonal = true)
    {
        var context = seasonal ? new SeasonContext("season", 0, "season-v1", GameConfigCatalog.Current.Version, "stats") : null;
        var room = new BattleRoom(Guid.NewGuid(), context?.ConfigVersion ?? "legacy", CombatCardCatalog.CreatePrototype(), 73, season: context);
        player = room.AddPlayer(new(Guid.NewGuid(), HeroClass.Mage, SeasonFenxianTests.Starter(HeroClass.Mage),
            new PveBattleState(Guid.NewGuid(), "action-target", [new MonsterCombatState("action-target", 100000, 100000, 0,
                TimeSpan.FromDays(1), [new(MonsterIntentKind.Attack, 2, CardElement.Fire)])])));
        return room;
    }
}
