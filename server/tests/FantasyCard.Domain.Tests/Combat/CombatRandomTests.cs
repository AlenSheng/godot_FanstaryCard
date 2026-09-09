using FantasyCard.Domain.Combat;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class CombatRandomTests
{
    [Fact]
    public void Restored_state_replays_the_same_random_sequence()
    {
        var random = new CombatRandom(9173);
        _ = random.Next();
        var snapshot = random.State;
        var expected = Enumerable.Range(0, 16).Select(_ => random.Next(1000)).ToArray();

        random.Restore(snapshot);
        var replay = Enumerable.Range(0, 16).Select(_ => random.Next(1000)).ToArray();

        Assert.Equal(expected, replay);
        Assert.InRange(random.Next(int.MinValue, int.MaxValue), int.MinValue, int.MaxValue - 1);
    }
}
