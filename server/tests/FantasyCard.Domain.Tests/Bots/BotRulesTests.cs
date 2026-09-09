using FantasyCard.Domain.Bots;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Bots;

public sealed class BotRulesTests
{
    [Theory]
    [InlineData(1, 3)]
    [InlineData(2, 2)]
    [InlineData(3, 1)]
    [InlineData(4, 0)]
    public void Bot_slots_fill_to_four(int realCount, int expectedBots)
    {
        Assert.Equal(expectedBots, BotRules.BotSlots(realCount));
    }

    [Fact]
    public void Match_opens_at_four_reals_or_after_thirty_seconds()
    {
        Assert.False(BotRules.ShouldOpenNow(1, 29));
        Assert.True(BotRules.ShouldOpenNow(1, 30));
        Assert.True(BotRules.ShouldOpenNow(4, 0));
        Assert.False(BotRules.ShouldOpenNow(0, 60));
    }

    [Fact]
    public void Gear_mirrors_party_average_within_one_step()
    {
        var party = new PartyWearSnapshot(
            [
                new WearPiece(ItemQuality.Blue, 2),
                new WearPiece(ItemQuality.Blue, 2),
                new WearPiece(ItemQuality.Green, 1),
                new WearPiece(ItemQuality.Green, 1),
                new WearPiece(ItemQuality.White, 0)
            ],
            [3]);
        var loadout = BotRules.CreateLoadout(party, [HeroClass.Mage], [], seed: 7);

        Assert.Equal(5, loadout.Armor.Count);
        Assert.All(loadout.Armor, piece => Assert.InRange((int)piece.Quality, 1, 5));
        Assert.All(loadout.Armor, piece => Assert.InRange(piece.EnhanceLevel, 0, 5));
        Assert.Equal(3, loadout.WeaponEnhance);
        Assert.Equal(1, loadout.PotionCount);
        Assert.False(string.IsNullOrWhiteSpace(loadout.DisplayName));
        Assert.Contains(loadout.Class, Enum.GetValues<HeroClass>());
    }

    [Fact]
    public void Bot_class_picks_underrepresented_role()
    {
        Assert.Equal(
            HeroClass.Priest,
            BotRules.PickClass([HeroClass.Mage, HeroClass.Guardian], seed: 1));
    }

    [Fact]
    public void Pve_sim_then_percent_hp_loss_never_kills()
    {
        Assert.Equal(65, BotRules.PveSimSeconds(CellLayer.Elite));
        Assert.Equal(40, BotRules.PveHpLossPercent(CellLayer.Elite));
        Assert.Equal(60, BotRules.ApplyHpLoss(100, 100, 40));
        Assert.Equal(1, BotRules.ApplyHpLoss(1, 100, 55));
    }

    [Fact]
    public void Three_choice_prefers_heal_when_hurt_else_gear()
    {
        Assert.Equal(ChoiceSlot.Heal, BotRules.PickChoice(50, 100, bagFull: false, hasFragmentStack: false));
        Assert.Equal(ChoiceSlot.Gear, BotRules.PickChoice(80, 100, bagFull: false, hasFragmentStack: false));
        Assert.Equal(ChoiceSlot.Fragments, BotRules.PickChoice(90, 100, bagFull: true, hasFragmentStack: true));
    }

    [Fact]
    public void Low_hp_triggers_out_of_combat_heal()
    {
        Assert.True(BotRules.ShouldHealOutOfCombat(50, 100, springAvailable: false, hasPotion: true));
        Assert.False(BotRules.ShouldHealOutOfCombat(80, 100, springAvailable: true, hasPotion: true));
        Assert.True(BotRules.PreferSpring(springAvailable: true));
        Assert.False(BotRules.PreferSpring(springAvailable: false));
    }

    [Fact]
    public void Extract_chance_rises_when_hurt()
    {
        Assert.Equal(25, BotRules.ExtractChancePercent(CellLayer.Mid, 100));
        Assert.Equal(35, BotRules.ExtractChancePercent(CellLayer.Mid, 50));
        Assert.Equal(50, BotRules.ExtractChancePercent(CellLayer.Mid, 30));
    }

    [Fact]
    public void Legal_neighbors_never_step_outward()
    {
        var from = new GridCell(4, 2);
        var legal = BotRules.LegalNeighbors(from);

        Assert.All(legal, cell => Assert.True(BotRules.LayerDistance(cell) >= BotRules.LayerDistance(from)));
        Assert.DoesNotContain(legal, cell => cell == new GridCell(5, 2));
        Assert.Contains(legal, cell => cell == new GridCell(3, 2));
    }

    [Fact]
    public void Late_raid_picks_inward_when_inward_exists()
    {
        var from = new GridCell(4, 0);
        var next = BotRules.PickNextCell(from, 500, BotRules.LegalNeighbors(from), new Random(99));
        Assert.Equal(new GridCell(4, 1), next);
    }

    [Fact]
    public void Medium_duel_ai_heals_when_critical()
    {
        var heal = new BotCard("water", IsDamage: false, IsHeal: true, IsStun: false, 18);
        var fire = new BotCard("fire", IsDamage: true, IsHeal: false, IsStun: false, 12);
        var picks = BotRules.SelectDuelCards([heal, fire], 30);
        Assert.Contains(0, picks);
    }

    [Fact]
    public void Medium_duel_ai_combos_same_element_when_healthy()
    {
        var a = new BotCard("fire", IsDamage: true, IsHeal: false, IsStun: false, 8);
        var b = new BotCard("fire", IsDamage: true, IsHeal: false, IsStun: false, 8);
        var c = new BotCard("water", IsDamage: true, IsHeal: false, IsStun: false, 20);
        var picks = BotRules.SelectDuelCards([a, b, c], 90);
        Assert.Equal(2, picks.Length);
        Assert.Contains(0, picks);
        Assert.Contains(1, picks);
    }

    [Fact]
    public void Bot_versus_bot_skips_full_card_resolution()
    {
        Assert.True(BotRules.ShouldSimulateBotVersusBot(true, true));
        Assert.False(BotRules.ShouldSimulateBotVersusBot(true, false));
        var (leftHp, rightHp, leftWon) = BotRules.ResolveBotVersusBot(100, 100, 80, 100);
        Assert.True(leftWon);
        Assert.Equal(85, leftHp);
        Assert.Equal(45, rightHp);
    }

    [Fact]
    public void Room_ends_when_no_real_players_remain()
    {
        Assert.True(BotRules.ShouldEndRoom(0));
        Assert.False(BotRules.ShouldEndRoom(1));
    }
}
