using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Rooms;

public sealed class AuthoritativeProcessorTests
{
    [Fact]
    public async Task AsyncAuthoritativeWorkBlocksLaterCommandsAndRefreshesTheOriginalSnapshotBeforeAck()
    {
        var entered=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);var handled=false;
        var room=new BattleRoom(Guid.NewGuid(),"processor",CombatCardCatalog.CreatePrototype(),73);
        await using var actor=new RoomActor(room,TimeProvider.System,startTicker:false,authoritativeProcessor:async value=>
        {
            if(handled || value.Elapsed==TimeSpan.Zero)return false;
            entered.SetResult();await release.Task;value.Advance(TimeSpan.FromMilliseconds(100));handled=true;return true;
        });
        var first=actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromMilliseconds(100)),cancellationToken:TestContext.Current.CancellationToken).AsTask();
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(10),TestContext.Current.CancellationToken);
        var later=actor.ExecuteAsync(new GetRoomSnapshotCommand(),cancellationToken:TestContext.Current.CancellationToken).AsTask();
        Assert.False(first.IsCompleted);Assert.False(later.IsCompleted);
        release.SetResult();
        Assert.Equal(TimeSpan.FromMilliseconds(200),(await first).Elapsed);
        Assert.Equal(TimeSpan.FromMilliseconds(200),(await later).Elapsed);
    }

    [Fact]
    public async Task AFailedPostMutationIsReportedAndTheNextCommandCanFinishItsAuthoritativeRecovery()
    {
        var failed=false;var recovered=false;
        var room=new BattleRoom(Guid.NewGuid(),"processor",CombatCardCatalog.CreatePrototype(),73);
        await using var actor=new RoomActor(room,TimeProvider.System,startTicker:false,authoritativeProcessor:value=>
        {
            if(value.Elapsed==TimeSpan.Zero)return Task.FromResult(false);
            if(!failed){failed=true;throw new IOException("isolated post-mutation fault");}
            if(!recovered){value.Advance(TimeSpan.FromMilliseconds(100));recovered=true;return Task.FromResult(true);}
            return Task.FromResult(false);
        });
        await Assert.ThrowsAsync<IOException>(()=>actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromMilliseconds(100)),cancellationToken:TestContext.Current.CancellationToken).AsTask());
        var restored=await actor.ExecuteAsync(new GetRoomSnapshotCommand(),cancellationToken:TestContext.Current.CancellationToken);
        Assert.True(recovered);Assert.Equal(TimeSpan.FromMilliseconds(200),restored.Elapsed);
    }
}
