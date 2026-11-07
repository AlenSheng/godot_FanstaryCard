using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Configuration;

namespace FantasyCard.Domain.Tests.Cards;

public sealed class PermanentCardCopyRulesTests
{
    [Theory]
    [InlineData("C01")]
    [InlineData("MAG-01")]
    [InlineData("PRI-10")]
    [InlineData("GUA-09")]
    public void Published_copy_costs_apply_to_owned_cards_only_in_the_new_policy(string id)
    {
        var card=CardEconomyRules.GetCard(id);
        Assert.Equal(card.CopyCost,CardEconomyRules.CraftCost(card,true,permanentCopies:true));
        Assert.Equal(card.InitiallyUnlocked?card.CopyCost:card.UnlockCost,CardEconomyRules.CraftCost(card,false,true));
        Assert.Equal(card.InitiallyUnlocked?card.CopyCost:card.UnlockCost,CardEconomyRules.CraftCost(card,true));
    }

    [Theory]
    [InlineData(0,false)]
    [InlineData(1,false)]
    [InlineData(2,false)]
    [InlineData(3,true)]
    [InlineData(4,true)]
    public void One_extra_copy_is_required_only_for_the_last_two_levels(int level,bool requiresCopy)
    {
        foreach(var card in GameConfigCatalog.Current.Cards.Where(card=>card.IsCodex&&card.Enabled))
        {
            Assert.Equal(requiresCopy,CardEconomyRules.UpgradeBlockedReason(card.CardId,true,1,level,1,true) is not null);
            Assert.Null(CardEconomyRules.UpgradeBlockedReason(card.CardId,true,2,level,1,true));
            // Old policies retain their original single-activation behavior.
            Assert.Null(CardEconomyRules.UpgradeBlockedReason(card.CardId,true,1,level,1));
        }
    }

    [Fact]
    public void Copy_materials_never_raise_the_permanent_level_cap_or_unlock_an_unowned_card()
    {
        Assert.NotNull(CardEconomyRules.UpgradeBlockedReason("C01",true,100,5,0,true));
        Assert.NotNull(CardEconomyRules.UpgradeBlockedReason("C01",false,0,0,0,true));
        Assert.NotNull(CardEconomyRules.UpgradeBlockedReason("C01",true,2,3,2,true));
    }
}
