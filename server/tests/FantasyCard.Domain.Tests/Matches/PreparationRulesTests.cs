using FantasyCard.Domain.Matches;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Matches;

public sealed class PreparationRulesTests
{
    [Fact]
    public void Validate_AcceptsFreeBackpackWithoutSafeSlots()
    {
        PreparationRules.Validate(
            Enumerable.Repeat<Guid?>(null, 5).ToArray(),
            BackpackTier.Free,
            [],
            0);
    }

    [Fact]
    public void Validate_RejectsDuplicateEquipment()
    {
        var equipmentId = Guid.NewGuid();

        Assert.Throws<DomainValidationException>(() =>
            PreparationRules.Validate(
                [equipmentId, equipmentId, null, null, null],
                BackpackTier.Free,
                [],
                0));
    }

    [Fact]
    public void Validate_RequiresThreeSafeSlotsForTopBackpack()
    {
        Assert.Throws<DomainValidationException>(() =>
            PreparationRules.Validate(
                Enumerable.Repeat<Guid?>(null, 5).ToArray(),
                BackpackTier.Top,
                [0, 1],
                0));
    }
}
