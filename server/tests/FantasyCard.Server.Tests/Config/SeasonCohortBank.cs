using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Explicit simulation bank. Typed domain prices/wishes, real observed loot, no claim of new PG execution.</summary>
internal sealed class SeasonCohortBank
{
    public SeasonCohortBank() { }
    internal sealed record Owned(ExplorationItem Item,string Source,bool Learned=false,int Version=1);
    internal sealed record Recipe(string Quality,string Slot,string Element,string? Effect,string Secondary,string SampleId);
    internal sealed record Wish(string Quality,string Slot,string Element,string Effect,int Failures);
    private static readonly string[] Slots=["Head","Chest","Hands","Legs","Feet"];
    public string Id{get;set;}="";
    public string Hero{get;set;}="";
    public string Cohort{get;set;}="";
    public int Attempts{get;set;}=1;
    public int Deaths{get;set;}
    public long Gold{get;set;}
    public long Fragments{get;set;}
    public long Blueprints{get;set;}
    public long OrangeBlueprints{get;set;}
    public long GoldEarned{get;set;}
    public long FragmentsEarned{get;set;}
    public long FragmentsSpent{get;set;}
    public long BlueprintsSpent{get;set;}
    public long OrangeBlueprintsSpent{get;set;}
    public double CombatSeconds{get;set;}
    public int CraftCounter{get;set;}
    public int? FirstQualityAttempt{get;set;}
    public int? FirstReadyAttempt{get;set;}
    public int? FirstTargetAttempt{get;set;}
    public string? StopReason{get;set;}
    public List<Owned> Items{get;set;}=[];
    public List<Owned> Overflow{get;set;}=[];
    public List<Owned> Recycled{get;set;}=[];
    public string SelectionPolicy{get;set;}="legacy";
    public List<Recipe> Recipes{get;set;}=[];
    public List<Wish> Wishes{get;set;}=[];
    public HashSet<string> SeenIds{get;set;}=new(StringComparer.Ordinal);
    public HashSet<string> LostIds{get;set;}=new(StringComparer.Ordinal);
    public string OriginSha256{get;set;}="";

    public static SeasonCohortBank Import(JsonElement row,string sha)
    {
        var scenario=row.GetProperty("scenario");var snapshot=JsonSerializer.Deserialize<BattleRoomSnapshot>(row.GetProperty("snapshot").GetRawText())!;var player=Assert.Single(snapshot.Players);
        var bank=new SeasonCohortBank{Id=scenario.GetProperty(nameof(Id)).GetString()!,Hero=scenario.GetProperty(nameof(Hero)).GetString()!,Cohort=scenario.GetProperty(nameof(Cohort)).GetString()!,OriginSha256=sha,CombatSeconds=row.GetProperty("seconds").GetDouble()};
        if(player.Phase==RoomPlayerPhase.Extracted)
        {
            foreach(var item in player.WornArmor!)bank.AddObserved(item,"InitialFixture");
            foreach(var item in player.Inventory!.Items)
            {
                if(item.Kind==ExplorationItemKind.Equipment)bank.AddObserved(item,"NaturalDrop");
                else if(item.Kind==ExplorationItemKind.Gold)bank.Gold+=item.Quantity;
                else if(item.Kind==ExplorationItemKind.EquipmentFragments)bank.Fragments+=item.Quantity;
            }
            bank.Blueprints=row.GetProperty("marks").GetProperty(nameof(Blueprints)).GetInt64();bank.OrangeBlueprints=row.GetProperty("marks").GetProperty(nameof(OrangeBlueprints)).GetInt64();bank.GoldEarned=bank.Gold;bank.FragmentsEarned=bank.Fragments;
        }
        else
        {
            Assert.Equal(RoomPlayerPhase.Dead,player.Phase);bank.Deaths=1;
            foreach(var item in snapshot.RelicPiles!.SelectMany(x=>x.Items).Where(x=>x.Kind==ExplorationItemKind.Equipment)){bank.SeenIds.Add(item.ItemId);bank.LostIds.Add(item.ItemId);}
        }
        bank.Check();return bank;
    }

    private void AddObserved(ExplorationItem item,string source)
    {
        Assert.True(SeenIds.Add(item.ItemId),"A generated/extracted physical item ID was repeated across matches.");
        Items.Add(new(item with {IsGenerated=false,IsSafe=false,SlotIndex=-1},source));
    }

    public void Lobby(GameConfigCatalog config,StreamWriter trace)
    {
        Learn(trace);ReforgeTargets(config,trace);
        // Reserve orange marks for the first orange body instead of spending them backwards on purple.
        if(!Items.Any(x=>x.Item.Equipment!.Slot=="Head"&&IsExactTarget(x.Item.Equipment))&&OrangeBlueprints>=config.SeasonCrafting!.Offer("Orange").MarkCost)Craft(config,"Orange","Head",trace);
        if(StopReason is not null)return;
        foreach(var slot in Slots)
        {
            if(slot=="Head"&&Items.Any(x=>x.Item.Equipment!.Quality=="Orange"))continue;
            if(Items.Any(x=>x.Item.Equipment!.Slot==slot&&IsExactTarget(x.Item.Equipment)))continue;
            var offer=config.SeasonCrafting!.Offer("Purple");
            if(Blueprints>=offer.MarkCost||Items.Any(x=>x.Item.Equipment!.Quality=="Orange")&&Blueprints+OrangeBlueprints>=offer.MarkCost)Craft(config,"Purple",slot,trace);
            if(StopReason is not null)return;
        }
        Learn(trace);ReforgeTargets(config,trace);
        var preferred=Select(config,2);var qualitySet=IsQualitySet(preferred);var season=SeasonDefinition.FromCalendarDays("d03-cohorts",new(2026,11,1),config.Version,"season-equipment-v1",highestOpenDifficulty:5);
        foreach(var selected in preferred)
        {
            var index=Items.FindIndex(x=>x.Item.ItemId==selected.ItemId);var item=Items[index];var limit=qualitySet?3:SeasonLootConfig.Rank(item.Item.Equipment!.Quality)>=1?1:0;
            while(item.Item.Equipment!.Level<limit)
            {
                var next=item.Item.Equipment.Level+1;var cost=SeasonEnhancementRules.ArmorCost(config,season,item.Item.Equipment.Quality,next);if(Fragments<cost)break;
                var before=item;Fragments-=cost;FragmentsSpent+=cost;item=item with {Item=item.Item with {Equipment=item.Item.Equipment with {Level=next}},Version=item.Version+1};Items[index]=item;
                Emit(trace,"enhance",new {before,after=item,cost,wallet=Fragments});
            }
        }
        Evaluate(config);Check();
    }

    private void Learn(StreamWriter trace)
    {
        for(var i=0;i<Items.Count;i++)
        {
            var item=Items[i];var e=item.Item.Equipment!;
            if(e.Quality is not ("Purple" or "Orange")||item.Learned||item.Source is not ("NaturalDrop" or "MarkCraft"))continue;
            if(Recipes.Any(r=>r.Quality==e.Quality&&r.Slot==e.Slot&&r.Element==e.Element&&r.Effect==e.EffectAffix))continue;
            var recipe=new Recipe(e.Quality,e.Slot,e.Element,e.EffectAffix,e.SecondaryTrait!,item.Item.ItemId);Recipes.Add(recipe);Items[i]=item with {Learned=true,Version=item.Version+1};Emit(trace,"learn",recipe);
        }
    }

    private void Craft(GameConfigCatalog config,string quality,string slot,StreamWriter trace)
    {
        if(Items.Count>=50){StopReason="warehouse_full";return;}
        var policy=config.SeasonCrafting!;var payment=policy.Payment(quality,Blueprints,OrangeBlueprints);var target=Target(slot);var old=Wishes.SingleOrDefault(x=>x.Quality==quality&&x.Slot==slot&&x.Element==target.Element&&x.Effect==target.Effect);
        var rng=new Random(unchecked(1700001+(int)Enum.Parse<HeroClass>(Hero)*10000+(Cohort=="novice"?1:Cohort=="returning"?2:3)*1000+CraftCounter++));
        var result=policy.Wish(quality,target.Effect!,old?.Failures??0,rng.Next(3));Blueprints-=payment.Blueprints;OrangeBlueprints-=payment.OrangeBlueprints;BlueprintsSpent+=payment.Blueprints;OrangeBlueprintsSpent+=payment.OrangeBlueprints;
        if(old is not null)Wishes.Remove(old);Wishes.Add(new(quality,slot,target.Element,target.Effect!,result.FailuresAfter));
        var secondary=slot=="Feet"&&rng.Next(2)==1?"ForcedEscape":"DrawInterval";var item=new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,Equipment:new(slot,quality,target.Element,result.EffectAffix,secondary,StatsVersion:"season-equipment-v1"),IsGenerated:false);
        Assert.True(EquipmentRewardRules.IsValid(item.Equipment!));AddObserved(item,"MarkCraft");Emit(trace,"craft",new {payment,result,item,Blueprints,OrangeBlueprints});
    }

    private void ReforgeTargets(GameConfigCatalog config,StreamWriter trace)
    {
        foreach(var slot in Slots)
        {
            var target=Target(slot);var quality=slot=="Head"?"Orange":"Purple";
            if(Items.Any(x=>Matches(x.Item.Equipment!,quality,slot,target.Element,target.Effect)))continue;
            var recipe=Recipes.FirstOrDefault(x=>x.Quality==quality&&x.Slot==slot&&x.Element==target.Element&&x.Effect==target.Effect);if(recipe is null)continue;
            var index=Items.FindIndex(x=>x.Item.Equipment!.Quality==quality&&!IsExactTarget(x.Item.Equipment));if(index<0)continue;
            var cost=config.SeasonCrafting!.Offer(quality).ReforgeFragmentCost;if(Fragments<cost)continue;
            var before=Items[index];var e=before.Item.Equipment!;var after=before with {Item=before.Item with {Equipment=e with {Slot=recipe.Slot,Element=recipe.Element,EffectAffix=recipe.Effect,SecondaryTrait=recipe.Secondary,Level=0}},Source="TemplateReforge",Learned=false,Version=before.Version+1};
            Fragments-=cost;FragmentsSpent+=cost;Items[index]=after;Emit(trace,"reforge",new {before,after,recipe,cost,wallet=Fragments});
        }
    }

    public int Difficulty(GameConfigCatalog config)
    {
        var d2=Select(config,2);if(d2.Length==5&&d2.All(x=>SeasonLootConfig.Rank(x.Equipment!.Quality)>=2)&&d2.Count(x=>SeasonLootConfig.Rank(x.Equipment!.Quality)>=3)>=(Cohort=="novice"?5:3)&&Fragments>=20)return 2;
        var d1=Select(config,1);return d1.Length>=3&&d1.Count(x=>SeasonLootConfig.Rank(x.Equipment!.Quality)>=2)>=3?1:0;
    }

    public ExplorationItem[] Select(GameConfigCatalog config,int difficulty)
    {
        if(SelectionPolicy==SeasonCohortMaintenance.Policy)return SeasonCohortMaintenance.Select(this,config,difficulty);
        var cap=config.SeasonDifficulty(difficulty).EntryQualityCap;var chosen=new List<ExplorationItem>();var usedHigh=false;
        foreach(var slot in Slots)
        {
            var target=Target(slot);var item=Items.Where(x=>x.Item.Equipment!.Slot==slot&&SeasonLootConfig.Rank(x.Item.Equipment.Quality)<=cap&&(!usedHigh||SeasonLootConfig.Rank(x.Item.Equipment.Quality)<4))
                .OrderByDescending(x=>SeasonLootConfig.Rank(x.Item.Equipment!.Quality)*100+x.Item.Equipment.Level*10+(x.Item.Equipment.EffectAffix==target.Effect?3:0)+(x.Item.Equipment.Element==target.Element?1:0)).ThenBy(x=>x.Item.ItemId,StringComparer.Ordinal).FirstOrDefault();
            if(item is null)continue;chosen.Add(item.Item);usedHigh|=SeasonLootConfig.Rank(item.Item.Equipment!.Quality)>=4;
        }
        return chosen.ToArray();
    }

    public void Settle(BattleRoomSnapshot snapshot,IReadOnlyList<Owned> deployed,GameConfigCatalog config,StreamWriter trace)
    {
        var player=Assert.Single(snapshot.Players);Attempts++;CombatSeconds+=snapshot.Elapsed.TotalSeconds;
        if(player.Phase==RoomPlayerPhase.Extracted)
        {
            var equipment=player.WornArmor!.Concat(player.Inventory!.Items.Where(x=>x.Kind==ExplorationItemKind.Equipment)).ToArray();
            var deployedIds=deployed.Select(x=>x.Item.ItemId).ToHashSet(StringComparer.Ordinal);
            foreach(var item in deployed){var actual=Assert.Single(equipment,x=>x.ItemId==item.Item.ItemId);Assert.Equal(item.Item.Equipment,actual.Equipment);Items.Add(item with {Item=actual with {IsGenerated=false,IsSafe=false,SlotIndex=-1}});}
            foreach(var item in equipment.Where(x=>!deployedIds.Contains(x.ItemId)))AddObserved(item,"NaturalDrop");
            foreach(var item in player.Inventory!.Items)
            {
                if(item.Kind==ExplorationItemKind.Gold){Gold+=item.Quantity;GoldEarned+=item.Quantity;}
                else if(item.Kind==ExplorationItemKind.EquipmentFragments){Fragments+=item.Quantity;FragmentsEarned+=item.Quantity;}
            }
            var cleared=snapshot.Map!.Cells.Where(x=>player.ClearedCells!.Contains(x.Position));var marks=config.SeasonCrafting!.Pending(snapshot.Season!.Difficulty,false,cleared);Blueprints+=marks.Blueprints;OrangeBlueprints+=marks.OrangeBlueprints;
        }
        else if(player.Phase==RoomPlayerPhase.Dead)
        {
            Deaths++;var lost=snapshot.RelicPiles!.Where(x=>x.VictimId==player.PlayerId.ToString("D")).SelectMany(x=>x.Items).Where(x=>x.Kind==ExplorationItemKind.Equipment).Select(x=>x.ItemId).ToHashSet(StringComparer.Ordinal);
            foreach(var item in deployed)Assert.Contains(item.Item.ItemId,lost);
            foreach(var id in lost){SeenIds.Add(id);Assert.True(LostIds.Add(id));}
        }
        else{StopReason="nonterminal_censored";foreach(var item in deployed)Overflow.Add(item);}
        if(Items.Count>50){Overflow.AddRange(Items.Skip(50));Items=Items.Take(50).ToList();StopReason="warehouse_full";}
        Evaluate(config);Check();Emit(trace,"settle",new {outcome=player.Phase,Attempts,Deaths,Gold,Fragments,Blueprints,OrangeBlueprints,warehouse=Items.Count,StopReason});
    }

    public List<Owned> Deploy(ExplorationItem[] selected)
    {
        var ids=selected.Select(x=>x.ItemId).ToHashSet(StringComparer.Ordinal);var result=Items.Where(x=>ids.Contains(x.Item.ItemId)).ToList();Assert.Equal(selected.Length,result.Count);Items.RemoveAll(x=>ids.Contains(x.Item.ItemId));return result;
    }
    private static bool IsQualitySet(ExplorationItem[] items)=>items.Length==5&&items.All(x=>SeasonLootConfig.Rank(x.Equipment!.Quality)>=3)&&items.Count(x=>x.Equipment!.Quality=="Orange")==1;
    private void Evaluate(GameConfigCatalog config)
    {
        var selected=Select(config,2);if(IsQualitySet(selected))FirstQualityAttempt??=Attempts;
        if(IsQualitySet(selected)&&selected.All(x=>x.Equipment!.Level>=3))
        {
            var profile=EquipmentCombatRules.Calculate(selected.Select(x=>new CombatEquipmentItem(Guid.Parse(x.ItemId),x.Equipment!.Slot,x.Equipment.Quality,x.Equipment.Level,Enum.Parse<CardElement>(x.Equipment.Element),x.Equipment.EffectAffix,x.Equipment.SecondaryTrait)).ToArray(),config,"season-equipment-v1");
            if(profile.PiercingBonus>0||profile.BulwarkDamageReduction>0||profile.BulwarkShieldBonus>0||profile.VitalityOvercapBonus>0)FirstReadyAttempt??=Attempts;
        }
        if(Slots.All(slot=>Items.Any(x=>IsExactTarget(x.Item.Equipment!)&&x.Item.Equipment!.Slot==slot&&x.Item.Equipment.Level>=3)))FirstTargetAttempt??=Attempts;
    }
    private static (string Element,string? Effect) Target(string slot)=>(slot is "Head" or "Chest" or "Hands"?"Water":"Fire",slot is "Head" or "Chest"?"Piercing":"Vitality");
    private static bool Matches(EquipmentRewardData e,string quality,string slot,string element,string? effect)=>e.Quality==quality&&e.Slot==slot&&e.Element==element&&e.EffectAffix==effect;
    private static bool IsExactTarget(EquipmentRewardData e){var t=Target(e.Slot);return Matches(e,e.Slot=="Head"?"Orange":"Purple",e.Slot,t.Element,t.Effect);}
    public void Check()
    {
        Assert.True(Gold>=0&&Fragments>=0&&Blueprints>=0&&OrangeBlueprints>=0);Assert.Equal(GoldEarned,Gold);Assert.Equal(FragmentsEarned-FragmentsSpent,Fragments);
        Assert.Equal(Items.Count,Items.Select(x=>x.Item.ItemId).Distinct(StringComparer.Ordinal).Count());Assert.DoesNotContain(Items,x=>LostIds.Contains(x.Item.ItemId));
        Assert.All(Items,x=>Assert.True(EquipmentRewardRules.IsValid(x.Item.Equipment!)));Assert.All(Items,x=>Assert.Contains(x.Item.ItemId,SeenIds));
        var activeIds=Items.Concat(Overflow).Select(x=>x.Item.ItemId).ToHashSet(StringComparer.Ordinal);
        Assert.Equal(Recycled.Count,Recycled.Select(x=>x.Item.ItemId).Distinct(StringComparer.Ordinal).Count());
        Assert.All(Recycled,x=>{Assert.Contains(x.Item.ItemId,SeenIds);Assert.DoesNotContain(x.Item.ItemId,activeIds);Assert.DoesNotContain(x.Item.ItemId,LostIds);});
    }
    private void Emit<T>(StreamWriter trace,string action,T payload)=>trace.WriteLine(JsonSerializer.Serialize(new {kind="bank",Id,action,Attempts,payload}));
}
