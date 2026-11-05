using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Published seasonal PVP boundary ticks, supplementing recovered multi-class scenarios.</summary>
public sealed class SeasonPublishedPvpGateTests
{
    public static bool Enabled=>Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D02_GATE_BOUNDARIES")=="1";
    private static readonly HeroClass[] Heroes=[HeroClass.Mage,HeroClass.Priest,HeroClass.Guardian];
    private static readonly DateTimeOffset Epoch=new(2026,11,20,0,0,0,TimeSpan.Zero);

    [Fact(Skip="Explicit three-match D02 boundary budget only.",SkipUnless=nameof(Enabled))]
    public void PublishedLateJoinAndCooldownRespectTheLastBlockedAndFirstAllowedTicks()
    {
        var prior=int.Parse(Environment.GetEnvironmentVariable("FANTASYCARD_D02_GATE_PRIOR")??throw new InvalidOperationException("Actual prior budget required."),System.Globalization.CultureInfo.InvariantCulture);Assert.InRange(prior,0,297);
        var root=Environment.GetEnvironmentVariable("FANTASYCARD_D02_GATE_OUTPUT")??throw new InvalidOperationException("Owned output required.");Assert.False(Directory.Exists(root));Directory.CreateDirectory(root);
        using var attempts=new StreamWriter(Path.Combine(root,"attempts.original.jsonl"));using var results=new StreamWriter(Path.Combine(root,"cases.original.jsonl"));
        foreach(var hero in Heroes)
        {
            attempts.WriteLine(JsonSerializer.Serialize(new {hero,prior_used=prior,scenario="published-last-blocked-first-allowed-PVP-ticks"}));attempts.Flush();
            var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);var firstId=Guid.NewGuid();var lateId=Guid.NewGuid();
            var prefix=hero==HeroClass.Mage?"MAG":hero==HeroClass.Priest?"PRI":"GUA";var cards=Enumerable.Range(1,13).Select(i=>$"C{i:D2}").Concat(Enumerable.Range(1,7).Select(i=>$"{prefix}-{i:D2}")).ToArray();
            DeckRules.Validate(hero,cards,config.Cards.Where(x=>x.IsCodex).ToDictionary(x=>x.CardId,x=>new OwnedCard(x.CardId,x.HeroClass,(CardRarity)x.Rarity,1,false)));
            var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,940000+(int)hero,season:new("d02-pvp-gates",0,"season-v1",config.Version,"season-equipment-v1"));
            room.AddPlayer(new(firstId,hero,cards,null));room.AddPlayer(new(lateId,hero,cards,null));var before=room.Capture();var duel=room.StartDuel(firstId,lateId,Epoch);
            CombatResolution Play()=>room.PlayCards(lateId,duel.DuelId,firstId.ToString("D"),[room.GetPlayer(lateId).Combat.Deck.Hand[0].InstanceId],room.Revision,Epoch+room.Elapsed,room.NewCombatActionId(lateId));
            void Step(int count){for(var i=0;i<count;i++)room.Advance(TimeSpan.FromMilliseconds(100),Epoch+room.Elapsed+TimeSpan.FromMilliseconds(100));}
            void Reject(string message)
            {
                var snapshot=JsonSerializer.Serialize(room.Capture());var error=Assert.Throws<DomainValidationException>(()=>Play());Assert.Equal(message,error.Message);Assert.Equal(snapshot,JsonSerializer.Serialize(room.Capture()));
            }
            Reject("The late joiner is still locked.");Step(7);Reject("The late joiner is still locked.");var blocked700=room.Capture();
            Step(1);Assert.Equal(TimeSpan.FromMilliseconds(800),room.Elapsed);var accepted800=Play();Assert.False(accepted800.ActionReplayed);Assert.Equal(500,room.GetCombatActionStatus(lateId).RemainingMs);
            Step(4);Assert.Equal(100,room.GetCombatActionStatus(lateId).RemainingMs);Reject("Successful combat actions must be at least 500ms apart.");var blocked400=room.Capture();
            Step(1);Assert.Equal(TimeSpan.FromMilliseconds(1300),room.Elapsed);Assert.Equal(0,room.GetCombatActionStatus(lateId).RemainingMs);var accepted500=Play();Assert.False(accepted500.ActionReplayed);Assert.Equal(3,room.GetCombatActionStatus(lateId).NextSequence);
            Assert.False(room.RequestDuelLeave(duel.DuelId,firstId,Epoch+room.Elapsed));Assert.True(room.RequestDuelLeave(duel.DuelId,lateId,Epoch+room.Elapsed));
            foreach(var original in before.Players)Assert.Equal(JsonSerializer.Serialize(original.Combat),JsonSerializer.Serialize(room.CapturePlayer(original.PlayerId).Combat));
            results.WriteLine(JsonSerializer.Serialize(new {hero,config.Version,config.ContentHash,blocked700,accepted800,blocked400,accepted500,final=room.Capture(),late_gate_700_rejected_800_allowed=true,cooldown_400_rejected_500_allowed=true,rejections_preserve_full_state=true}));results.Flush();
        }
    }
}
