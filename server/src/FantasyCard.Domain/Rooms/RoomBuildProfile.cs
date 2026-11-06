using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Rooms;

public sealed record ObservedBuildCard(string CardId,int Level,CardElement? ElementOverride,int Count);
public sealed record ObservedBuildArmor(string Slot,string Quality,int Level,string Element,string? EffectAffix,string? SecondaryTrait,string? UniqueAffix,bool CombatProjection,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] string? UniqueElement=null);
public sealed record RoomBuildProfile(int SchemaVersion,string ProfileId,string? BuildType,string? GrowthStage,int WeaponLevel,
    double NaturalDrawIntervalSeconds,IReadOnlyList<ObservedBuildCard> Cards,IReadOnlyList<ObservedBuildArmor> Armor,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] string? BorrowedTemplateId=null)
{
    public void RequireValid()
    {
        if(SchemaVersion!=1||ProfileId is null||ProfileId.Length!=64||Cards is null||Armor is null||Cards.Count>128||Armor.Count>5||WeaponLevel is <0 or >5||
            !double.IsFinite(NaturalDrawIntervalSeconds)||NaturalDrawIntervalSeconds<=0||
            Cards.Any(c=>string.IsNullOrEmpty(c.CardId)||c.CardId.Length>80||c.Level is <0 or >5||c.Count<=0||c.Count>1000||c.ElementOverride is { } element&&!Enum.IsDefined(element))||
            Cards.Sum(c=>(long)c.Count)>1000||Cards.Select(c=>(c.CardId,c.Level,c.ElementOverride)).Distinct().Count()!=Cards.Count||
            Armor.Any(a=>a.Slot is not("Head" or "Chest" or "Hands" or "Legs" or "Feet")||a.Quality is not("White" or "Green" or "Blue" or "Purple" or "Orange" or "Red")||a.Level is <0 or >5||
                a.Element is not("Fire" or "Wood" or "Earth" or "Metal" or "Water")||a.EffectAffix is not(null or "Piercing" or "Bulwark" or "Vitality")||
                a.SecondaryTrait is not(null or "DrawInterval" or "ForcedEscape")||a.UniqueAffix is not(null or "Inferno" or "RapidDraw" or "ChainDraw" or "Scavenge" or "GoldenCicada")||
                a.UniqueElement is not(null or "Fire" or "Wood" or "Earth" or "Metal" or "Water"))||
            Armor.Select(a=>a.Slot).Distinct(StringComparer.Ordinal).Count()!=Armor.Count||
            BuildType?.Length>80||GrowthStage?.Length>80||BorrowedTemplateId?.Length>80||ProfileId!=Fingerprint(this))
            throw new DomainValidationException("Saved build observation has invalid bounded facts or fingerprint.");
    }

    internal static string Fingerprint(RoomBuildProfile value)=>Convert.ToHexStringLower(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(value with{ProfileId=""})));
}

public static class RoomBuildProfiles
{
    /// <summary>Effective combat composition, never account age, permanent levels or a P0-P5 diagnostic claim.</summary>
    public static RoomBuildProfile? Capture(RoomPlayerState player,CombatCardCatalog catalog)
    {
        var deck=player.Combat.Deck;var pool=deck.Hand.Concat(deck.Library).Concat(deck.Discard).ToArray();
        if(pool.Length>1000||player.WornArmor.Count>5||player.WornArmor.Any(item=>item.Equipment is null))return null;
        var cards=pool.GroupBy(c=>(c.CardId,c.Level,c.ElementOverride)).OrderBy(g=>g.Key.CardId,StringComparer.Ordinal).ThenBy(g=>g.Key.Level).ThenBy(g=>g.Key.ElementOverride)
            .Select(g=>new ObservedBuildCard(g.Key.CardId,g.Key.Level,g.Key.ElementOverride,g.Count())).ToArray();
        if(cards.Length>128)return null;
        var armor=player.WornArmor.OrderBy(item=>item.Equipment!.Slot,StringComparer.Ordinal).Select(item=>
        {
            var a=item.Equipment!;return new ObservedBuildArmor(a.Slot,a.Quality,a.Level,a.Element,a.EffectAffix,a.SecondaryTrait,a.UniqueAffix,item.IsCombatProjection,a.UniqueElement);
        }).ToArray();
        var elements=new HashSet<CardElement>();var direct=false;var known=true;
        foreach(var card in cards)
        {
            if(!catalog.Contains(card.CardId)){known=false;continue;}
            // Level scaling does not change damage element; base catalog also
            // supports legacy prototype IDs without inventing permanent levels.
            var effect=catalog.Get(card.CardId,elementOverride:card.ElementOverride).Effect;
            if(effect.ElementalDamage>0&&effect.Element!=CardElement.None)elements.Add(effect.Element);
            if(effect.SecondaryElementalDamage>0&&effect.SecondaryElement!=CardElement.None)elements.Add(effect.SecondaryElement);
            direct|=effect.DirectDamage>0;
        }
        var elementBuild=elements.Count>1?"MixedElements":elements.Count==1?"Mono"+elements.Single():direct?"DirectOnly":"SupportOnly";
        var effective=player.Combat.Equipment;var sets=new List<string>();
        if(effective.PiercingBonus>0)sets.Add("Piercing");
        if(effective.BulwarkDamageReduction>0||effective.BulwarkShieldBonus>0)sets.Add("Bulwark");
        if(effective.VitalityHealBonus>0||effective.VitalityOvercapBonus>0)sets.Add("Vitality");
        var effectBuild=sets.Count==0?"NoActiveEffectSet":string.Join('+',sets);
        var baseCards=cards.Where(c=>!c.CardId.StartsWith("M-",StringComparison.Ordinal)).ToArray();
        var growth=baseCards.Length==0?null:"EffectiveBaseCardMaxL"+baseCards.Max(c=>c.Level).ToString(CultureInfo.InvariantCulture);
        var profile=new RoomBuildProfile(1,"",known?elementBuild+"/"+effectBuild:null,growth,player.Combat.WeaponLevel,
            player.Combat.NaturalDrawIntervalSeconds,cards,armor,player.BorrowedTemplateId);
        return profile with{ProfileId=RoomBuildProfile.Fingerprint(profile)};
    }
}
