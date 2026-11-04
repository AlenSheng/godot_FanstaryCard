using System.Security.Cryptography;
using System.Text;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Configuration;

public sealed record SeasonShopOffer(string ProductId,string Kind,int Amount,long PriceGold,int DailyLimit,
    string QuotaGroup,string? HeroClass=null,string? CardId=null);

public sealed record SeasonShopConfig(string RuleId,string TimeZoneId,int ResetHour,int PackCards,
    int WhiteWeight,int GreenWeight,int BlueWeight,int PurpleWeight,int ClassSoulDailyLimit,int PaidBagCap,
    IReadOnlyList<SeasonShopOffer> Products)
{
    public const string Version="season-gold-shop-v1";

    public void Validate(IReadOnlyList<CardConfigDefinition> cards,IReadOnlyList<CardLevelConfig> levels,
        EconomyConfig economy,IReadOnlyList<BackpackConfig> bags,IReadOnlyList<ShopCardPriceConfig> prices)
    {
        SeasonShopOffer[] expected=[new("card_pack","Cards",3,250,5,"card_pack"),
            new("warrior_soul","WarriorSoul",20,180,3,"warrior_soul"),
            new("equipment_fragments","EquipmentFragments",20,120,3,"equipment_fragments"),
            new("priest_soul","ClassSoul",12,400,1,"class_soul","Priest"),
            new("mage_soul","ClassSoul",12,400,1,"class_soul","Mage"),
            new("guardian_soul","ClassSoul",12,400,1,"class_soul","Guardian"),
            new("health_potion","HealthPotion",1,100,4,"health_potion"),
            new("advanced_bag","AdvancedBag",1,800,0,"advanced_bag"),
            new("top_bag","TopBag",1,2200,0,"top_bag")];
        if(RuleId!=Version || TimeZoneId!="Asia/Shanghai" || ResetHour!=4 || PackCards!=3 ||
            (WhiteWeight,GreenWeight,BlueWeight,PurpleWeight)!=(50,30,15,5) || ClassSoulDailyLimit!=1 || PaidBagCap!=3 ||
            !Products.OrderBy(p=>p.ProductId,StringComparer.Ordinal).SequenceEqual(expected.OrderBy(p=>p.ProductId,StringComparer.Ordinal)) ||
            economy.HealthPotionPrice!=100 || economy.DailyCardSlots!=3 || economy.DailyShopRefreshLimit!=3 ||
            bags.Single(b=>b.Id=="Advanced").PriceGold!=800 || bags.Single(b=>b.Id=="Top").PriceGold!=2200 ||
            prices.Count!=4 || !prices.OrderBy(p=>p.Quality,StringComparer.Ordinal).SequenceEqual(
                new ShopCardPriceConfig[]{new("White",80,1),new("Green",150,1),new("Blue",280,1),new("Purple",500,1)}.OrderBy(p=>p.Quality,StringComparer.Ordinal)) ||
            levels.Any(l=>l.RequiresCopy!=(l.Level>=4)))
            throw new InvalidDataException("Season shop prices, limits, copies or reset terms differ from the authorized baseline.");
        foreach(var quality in new[]{"White","Green","Blue","Purple"})
            if(!cards.Any(card=>PackEligible(card)&&card.Quality==quality))
                throw new InvalidDataException("Every weighted card-pack quality must have an eligible published card.");
    }

    public static bool PackEligible(CardConfigDefinition card)=>card.Enabled&&card.IsCodex&&
        card.Quality is "White" or "Green" or "Blue" or "Purple"&&!(card.Quality=="Purple"&&card.HeroClass is not null);

    public CardConfigDefinition Draw(IReadOnlyList<CardConfigDefinition> cards,Func<int,int> random)
    {
        var roll=random(100);
        if(roll is <0 or >=100)throw new DomainValidationException("The card-pack random roll is invalid.");
        var quality=roll<WhiteWeight?"White":roll<WhiteWeight+GreenWeight?"Green":
            roll<WhiteWeight+GreenWeight+BlueWeight?"Blue":"Purple";
        var pool=cards.Where(c=>PackEligible(c)&&c.Quality==quality).OrderBy(c=>c.CardId,StringComparer.Ordinal).ToArray();
        if(pool.Length==0)throw new DomainValidationException("The published card-pack quality pool is unavailable.");
        var index=random(pool.Length);
        if(index<0||index>=pool.Length)throw new DomainValidationException("The card-pack card index is invalid.");
        return pool[index];
    }

    public IReadOnlyList<SeasonShopOffer> Offers(GameConfigCatalog catalog,string seed)
    {
        var prices=catalog.ShopCardPrices.ToDictionary(p=>p.Quality,StringComparer.Ordinal);
        var cards=catalog.Cards.Where(c=>c.Enabled&&c.IsCodex&&c.Quality is not null&&prices.ContainsKey(c.Quality))
            .OrderBy(c=>Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes($"{catalog.Version}:{seed}:{c.CardId}"))),StringComparer.Ordinal)
            .ThenBy(c=>c.CardId,StringComparer.Ordinal).Take(catalog.Economy.DailyCardSlots).ToArray();
        if(cards.Length!=3)throw new DomainValidationException("The daily shop card rotation cannot be filled.");
        return Products.Concat(cards.Select((c,i)=>new SeasonShopOffer($"daily_card_{i+1}","Cards",1,
            prices[c.Quality!].PriceGold,1,$"daily_card_{i+1}",CardId:c.CardId))).ToArray();
    }

    // Stored offers are business snapshots, never an alternative config loader.
    public void ValidateOffers(GameConfigCatalog catalog,IReadOnlyList<SeasonShopOffer> offers)
    {
        if(offers.Count!=12 || offers.Select(o=>o.ProductId).Distinct(StringComparer.Ordinal).Count()!=12 ||
            !offers.Where(o=>o.CardId is null).OrderBy(o=>o.ProductId,StringComparer.Ordinal)
                .SequenceEqual(Products.OrderBy(o=>o.ProductId,StringComparer.Ordinal)))
            throw new DomainValidationException("The frozen shop offers differ from their published policy.");
        var seen=new HashSet<string>(StringComparer.Ordinal);
        for(var index=1;index<=3;index++)
        {
            var id=$"daily_card_{index}";var offer=offers.SingleOrDefault(o=>o.ProductId==id);
            var card=catalog.Cards.SingleOrDefault(c=>c.CardId==offer?.CardId&&c.Enabled&&c.IsCodex);
            var price=catalog.ShopCardPrices.SingleOrDefault(p=>p.Quality==card?.Quality);
            if(offer is null || card is null || price is null || !seen.Add(card.CardId) ||
                offer!=new SeasonShopOffer(id,"Cards",1,price.PriceGold,1,id,CardId:card.CardId))
                throw new DomainValidationException("The frozen daily card offer is invalid.");
        }
    }
}
