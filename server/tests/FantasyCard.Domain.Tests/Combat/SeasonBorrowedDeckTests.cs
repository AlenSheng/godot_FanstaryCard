using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class SeasonBorrowedDeckTests
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    [Theory]
    [InlineData(HeroClass.Mage)] [InlineData(HeroClass.Priest)] [InlineData(HeroClass.Guardian)]
    public void PublishedLegalTemplatesKeepTheSameEffectiveCardAndWeaponLevelsAcrossPvePvpAndRecovery(HeroClass hero)
    {
        for (var cap=0;cap<=5;cap++)
        {
            var configuration = GameConfigCatalog.Current;var template = configuration.BorrowedDeck(hero);
            SeasonFenxianTests.ValidateDeck(hero,template.CardIds.ToArray());
            var context = new SeasonContext("loan",cap,"season-v1",configuration.Version,"loan-stats");
            var catalog = CombatCardCatalog.Create(configuration);
            var room = new BattleRoom(Guid.NewGuid(),configuration.Version,catalog,73,season:context);
            var player = room.AddPlayer(new(Guid.NewGuid(),hero,template.CardIds,null,WeaponLevel:cap,
                CardLevels:Enumerable.Repeat(cap,20).ToArray(),BorrowedTemplateId:template.TemplateId));
            var opponent = room.AddPlayer(new(Guid.NewGuid(),HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null));
            var before = player.Combat.Capture();
            Assert.Equal(cap,before.WeaponLevel);Assert.All(All(before),card=>Assert.Equal(cap,card.Level));
            var duel = room.StartDuel(player.PlayerId,opponent.PlayerId,DateTimeOffset.UnixEpoch);
            Assert.Equal(cap,player.Combat.WeaponLevel);Assert.All(All(player.Combat.Capture()),card=>Assert.Equal(cap,card.Level));
            var text = JsonSerializer.Serialize(room.Capture(),Json);
            var restored = BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(text,Json)!,catalog,73);
            Assert.Equal(template.TemplateId,restored.GetPlayer(player.PlayerId).BorrowedTemplateId);
            restored.EndDuelSurvived(duel.DuelId,DuelEndReason.MutualLeave);
            Assert.Equivalent(before,restored.GetPlayer(player.PlayerId).Combat.Capture(),strict:true);
        }
    }

    [Fact]
    public void MonsterCardsCanAccumulateWithoutTurningBorrowedOriginalsIntoPermanentOrHigherLevelCopies()
    {
        var template = GameConfigCatalog.Current.BorrowedDeck(HeroClass.Mage);var catalog = CombatCardCatalog.Create(GameConfigCatalog.Current);
        var context = new SeasonContext("pool",3,"season-v1",GameConfigCatalog.Current.Version,"loan-stats");
        var room = new BattleRoom(Guid.NewGuid(),context.ConfigVersion,catalog,73,season:context);
        var player = room.AddPlayer(new(Guid.NewGuid(),HeroClass.Mage,template.CardIds,null,WeaponLevel:3,
            CardLevels:Enumerable.Repeat(3,20).ToArray(),BorrowedTemplateId:template.TemplateId));
        var monsterCard = GameConfigCatalog.Current.Cards.Single(card=>card.MonsterType=="FireBat").CardId;
        player.Combat.Deck.AddToDiscard(new(Guid.NewGuid(),monsterCard));
        var restored = BattleRoom.Restore(room.Capture(),catalog,73).GetPlayer(player.PlayerId);
        Assert.Equal(21,All(restored.Combat.Capture()).Count());
        Assert.Equal(0,All(restored.Combat.Capture()).Single(card=>card.CardId==monsterCard).Level);
        var snapshot = room.Capture();
        var bad = snapshot with {Players=snapshot.Players.Select(p=>p with {Combat=p.Combat with {WeaponLevel=4}}).ToArray()};
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(bad,catalog,73));
    }

    [Theory]
    [InlineData("template")] [InlineData("level")] [InlineData("cards")] [InlineData("legacy")]
    public void BorrowedSourceCannotChangeItsTemplateLevelsOrScope(string mutation)
    {
        var config = GameConfigCatalog.Current;var template = config.BorrowedDeck(HeroClass.Mage);
        var context = mutation=="legacy" ? null : new SeasonContext("guard",2,"season-v1",config.Version,"loan-stats");
        var room = new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),73,season:context);
        var ids = template.CardIds.ToArray();if(mutation=="cards")ids[0]="C14";
        Assert.Throws<DomainValidationException>(()=>room.AddPlayer(new(Guid.NewGuid(),HeroClass.Mage,ids,null,
            WeaponLevel:mutation=="level"?3:2,CardLevels:Enumerable.Repeat(2,20).ToArray(),
            BorrowedTemplateId:mutation=="template"?"other":template.TemplateId)));
    }

    private static IEnumerable<CombatCardInstance> All(PlayerCombatSnapshot snapshot)=>snapshot.Deck.Hand.Concat(snapshot.Deck.Library).Concat(snapshot.Deck.Discard);
}
