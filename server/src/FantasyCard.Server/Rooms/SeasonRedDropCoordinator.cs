using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Progression;

namespace FantasyCard.Server.Rooms;

public sealed class SeasonRedDropCoordinator(SeasonRedMintRepository repository,RoomSnapshotRepository snapshots)
{
    public async Task<bool> ProcessAsync(Guid matchId,BattleRoom room)
    {
        if(room.RedPolicy is null || !room.HasRedWork)return false;
        await snapshots.SaveIfDueAsync(room.Capture());
        var changed=false;
        foreach(var player in room.Capture().Players.Where(player=>player.PendingRedEvaluation is not null))
        {
            var result=await repository.ResolveBossAsync(matchId,player.PlayerId,room.Season!,player.PendingRedEvaluation!,CancellationToken.None);
            room.ApplyRedDrop(player.PlayerId,result);changed=true;
        }
        await snapshots.SaveIfDueAsync(room.Capture());room.MarkRedStatePersisted();return changed;
    }
}
