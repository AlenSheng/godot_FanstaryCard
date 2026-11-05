using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Configuration;

public sealed class SeasonThemeRulesTests
{
    private static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web){Converters={new JsonStringEnumConverter()}};

    [Fact]
    public void ActualPublishedThemeGroupIsCompleteAndOriginalConfigElevenStillUsesLegacyEncounters()
    {
        var current=GameConfigCatalog.Current;
        var rules=Assert.IsType<SeasonThemeConfig>(current.SeasonThemes);rules.Validate(current.SeasonLootPreference!.DefaultElement);
        Assert.Equal("Fire",rules.SelectedThemeId);Assert.Equal(19,rules.Groups.Count);Assert.Equal(5,rules.Themes.Count);
        var folder=new DirectoryInfo(AppContext.BaseDirectory);string? path=null;
        while(folder is not null)
        {
            var candidate=Path.Combine(folder.FullName,"server/config/archive/season-v1-config-11/fantasycard.config.bytes");
            if(File.Exists(candidate)){path=candidate;break;}folder=folder.Parent;
        }
        Assert.NotNull(path);var old=GameConfigCatalog.Load(File.ReadAllBytes(path));Assert.Null(old.SeasonThemes);Assert.NotNull(old.SeasonJourney);
    }
    internal static SeasonThemeConfig Rules(string selected="Fire")=>new(SeasonThemeConfig.Version,selected,4000,1500,"member-mean-normalized",10000,"chaos-6x6",true,
        [new("Fire",CardElement.Fire,"season_theme_fire","ember-windows",CardElement.Fire,CardElement.Wood,CardElement.Metal,CardElement.Earth,0,0,10,8,"Charge",0),
         new("Wood",CardElement.Wood,"season_theme_wood","thorn-regrowth",CardElement.Wood,CardElement.Water,CardElement.Water,CardElement.Wood,500,200,0,0,"Charge",0),
         new("Earth",CardElement.Earth,"season_theme_earth","stone-cycle",CardElement.Earth,CardElement.Metal,CardElement.Metal,CardElement.Earth,0,0,12,10,"Charge",0),
         new("Metal",CardElement.Metal,"season_theme_metal","metal-telegraph",CardElement.Metal,CardElement.Fire,CardElement.Fire,CardElement.Metal,0,0,10,8,"Empower",2),
         new("Water",CardElement.Water,"season_theme_water","tide-shift",CardElement.Water,CardElement.Metal,CardElement.Wood,CardElement.Water,0,0,10,8,"Charge",0)],
        new[]{("O1","Fire"),("O2","Wood"),("O3","Water"),("O4","Earth"),("O5","Metal"),("O6","Fire|Fire"),("O7","Metal|Wood"),("O8","Water|Earth"),
            ("M1","Fire|Fire"),("M2","Water|Earth"),("M3","Metal|Wood"),("M4","Water|Water"),("M5","Fire|Earth"),
            ("E1","Metal"),("E2","Fire"),("E3","Water"),("E4","Earth"),("E5","Wood"),("E6","Metal|Fire")}
            .Select(row=>new SeasonThemeGroup(row.Item1,row.Item1[0]=='O'?"outer":row.Item1[0]=='M'?"middle":"elite",row.Item2,
                row.Item1[0]=='O'&&int.Parse(row.Item1[1..],System.Globalization.CultureInfo.InvariantCulture)<=5,100)).ToArray());

    [Theory]
    [InlineData("Wood")][InlineData("Fire")][InlineData("Earth")][InlineData("Metal")][InlineData("Water")]
    public void ExactWholeGroupWeightsCoverEveryBoundaryWithoutSplittingPairs(string selected)
    {
        var rules=Rules(selected);rules.Validate(selected);
        foreach(var tier in new[]{"outer","middle","elite"})
        {
            var pool=rules.Groups.Where(g=>g.Tier==tier).ToArray();var cursor=0;
            foreach(var group in pool)
            {
                var weight=rules.Weight(group);Assert.True(weight>0);
                Assert.Equal(group.GroupId,rules.Roll(tier,false,cursor));Assert.Equal(group.GroupId,rules.Roll(tier,false,cursor+weight-1));
                var cell=new ChaosMapCell(new(0,0),tier=="outer"?ChaosMapLayer.Outer:tier=="middle"?ChaosMapLayer.Middle:ChaosMapLayer.Core,false,false,false,group.GroupId);
                var actual=PveBattleFactory.Create(cell).Monsters.Select(m=>m.Intents.First(i=>i.Element!=CardElement.None).Element).ToArray();
                Assert.Equal(group.Elements,actual);cursor+=weight;
            }
            Assert.Throws<FantasyCard.Domain.Players.DomainValidationException>(()=>rules.Roll(tier,false,cursor));
        }
        var spawns=rules.Groups.Where(g=>g.SpawnAllowed).ToArray();Assert.Equal(5,spawns.Length);Assert.All(spawns,g=>Assert.Single(g.Elements));
        var spawnTotal=spawns.Sum(rules.Weight);Assert.Equal(spawns[^1].GroupId,rules.Roll("outer",true,spawnTotal-1));
    }

    [Fact]
    public void ThemeRollChangesOnlyGroupsAndPreservesOriginalLayoutAndTreasureStream()
    {
        foreach(var seed in new[]{7,73,2026})
        {
            var baseline=ChaosMapGenerator.Generate(seed,4).Capture();
            foreach(var element in SeasonThemeConfig.Elements)
            {
                var themed=ChaosMapGenerator.Generate(seed,4,Rules(element.ToString())).Capture();
                Assert.Equal(baseline.BossPosition,themed.BossPosition);Assert.Equal(baseline.SpawnPositions,themed.SpawnPositions);
                Assert.Equal(baseline.Cells.Select(c=>(c.Position,c.Layer,c.IsBoss,c.HasSpring,c.HasEvacuation,c.TreasureElement)),
                    themed.Cells.Select(c=>(c.Position,c.Layer,c.IsBoss,c.HasSpring,c.HasEvacuation,c.TreasureElement)));
                Assert.Equal(baseline.Cells.Where(c=>c.MonsterGroupId=="BOX"),themed.Cells.Where(c=>c.MonsterGroupId=="BOX"));
                Assert.Equal(36,themed.Cells.Count);
            }
        }
    }

    [Theory]
    [InlineData("Wood")][InlineData("Fire")][InlineData("Earth")][InlineData("Metal")][InlineData("Water")]
    public void ActualTwoPhaseBossKeepsBaseHealthAmplificationAndPublishedDifficulty(string selected)
    {
        var config=GameConfigCatalog.Current;var difficulty=config.SeasonDifficulty(5);var rules=Rules(selected);var cell=new ChaosMapCell(new(2,2),ChaosMapLayer.Core,true,false,false,"BOSS");
        var baseline=Assert.Single(PveBattleFactory.Create(cell,difficulty).Monsters);var boss=Assert.Single(PveBattleFactory.Create(cell,difficulty,rules.Selected).Monsters);
        Assert.Equal(baseline.MaximumHp,boss.MaximumHp);Assert.Equal(baseline.Shield,boss.Shield);Assert.Equal(baseline.ElementalAmplification,boss.ElementalAmplification);
        Assert.Equal(baseline.DifficultyProfile,boss.DifficultyProfile);Assert.Equal(6,boss.Intents.Count);
        Assert.Equal(.35,boss.ElementalResistance(rules.Selected.PhaseOnePrimary),8);Assert.Equal(.20,boss.ElementalResistance(rules.Selected.PhaseOneSecondary),8);
        boss.TakeDamage(boss.Shield+boss.Hp/2);boss.ResolveUtilityIntent(new(MonsterIntentKind.Shield,0,CardElement.None));
        Assert.Equal(2,boss.BossPhase);Assert.Equal(rules.Selected.Intents(2),boss.Intents);
        Assert.Equal(.35,boss.ElementalResistance(rules.Selected.PhaseTwoPrimary),8);Assert.Equal(.20,boss.ElementalResistance(rules.Selected.PhaseTwoSecondary),8);
        Assert.Equal(baseline.MaximumHp,boss.MaximumHp);
    }

    [Fact]
    public void FireStrategyHasExactlyTheLegacyAttackAndPhaseSchedules()
    {
        var config=GameConfigCatalog.Current;var cell=new ChaosMapCell(new(2,2),ChaosMapLayer.Core,true,false,false,"BOSS");
        var old=Assert.Single(PveBattleFactory.Create(cell,config.SeasonDifficulty(2)).Monsters);
        var fire=Assert.Single(PveBattleFactory.Create(cell,config.SeasonDifficulty(2),Rules().Selected).Monsters);
        Assert.Equal(old.Intents,fire.Intents);Assert.Equal(old.AttackInterval,fire.AttackInterval);
        foreach(var boss in new[]{old,fire}){boss.TakeDamage(boss.Shield+boss.Hp/2);boss.ResolveUtilityIntent(new(MonsterIntentKind.Shield,0,CardElement.None));}
        Assert.Equal(old.Intents,fire.Intents);Assert.Equal(old.AttackInterval,fire.AttackInterval);
    }

    [Fact]
    public void RealRegenerationTicksAreInterruptibleAndTheWholeFightNeverRecoversMoreThanFivePercent()
    {
        var boss=Boss("Wood");boss.TakeDamage(boss.Shield+boss.MaximumHp/3);
        for(var tick=0;tick<1200;tick++)
        {
            var intent=boss.Advance(TimeSpan.FromMilliseconds(100));if(intent is null)continue;
            if(intent.Kind is MonsterIntentKind.Attack or MonsterIntentKind.Direct)boss.ResolveIntentDamage(intent);
            else boss.ResolveUtilityIntent(intent);
        }
        var budget=boss.MaximumHp*5/100;Assert.Equal(budget,boss.ThemeRecoveredHp);
        var saved=boss.Capture();var restored=MonsterCombatState.Restore(JsonSerializer.Deserialize<MonsterCombatSnapshot>(JsonSerializer.Serialize(saved,Json),Json)!);
        Assert.Equal(budget,restored.ThemeRecoveredHp);Assert.Equivalent(saved,restored.Capture(),strict:true);
        var before=restored.Hp;restored.ResolveUtilityIntent(Rules("Wood").Selected.Intents(1)[2]);Assert.Equal(before,restored.Hp);
        Assert.Throws<InvalidDataException>(()=>MonsterCombatState.Restore(saved with {ThemeRecoveredHp=budget+1}));
        var pending=Boss("Wood");pending.TakeDamage(pending.Shield+pending.MaximumHp/3);
        for(var tick=0;tick<1000&&!(pending.IntentIndex==2&&pending.WindupRemaining>TimeSpan.Zero);tick++)
        {
            var intent=pending.Advance(TimeSpan.FromMilliseconds(100));if(intent is not null)pending.ResolveIntentDamage(intent);
        }
        Assert.Equal(2,pending.IntentIndex);Assert.True(pending.WindupRemaining>TimeSpan.Zero);pending.ApplyStun(TimeSpan.FromSeconds(2));
        Assert.Equal(3,pending.IntentIndex);Assert.Equal(0,pending.ThemeRecoveredHp);
    }

    [Fact]
    public void EarthShieldAccountingCountsActualGainsAndCannotStackBeyondTheExistingHalfHealthCap()
    {
        var boss=Boss("Earth");var initial=boss.Shield;
        for(var i=0;i<20;i++)boss.ResolveUtilityIntent(boss.ThemeProfile!.Intents(1)[2]);
        Assert.Equal(boss.MaximumHp/2,boss.Shield);Assert.Equal(boss.Shield-initial,boss.ThemeShieldGenerated);
        var recorded=boss.ThemeShieldGenerated;boss.ResolveUtilityIntent(boss.ThemeProfile!.Intents(1)[2]);Assert.Equal(recorded,boss.ThemeShieldGenerated);
        Assert.Equal(recorded,MonsterCombatState.Restore(boss.Capture()).ThemeShieldGenerated);
    }

    [Fact]
    public void ExtraDamageRegenBudgetAndForgedOriginalThemeAreRejected()
    {
        var rules=Rules();Assert.Throws<InvalidDataException>(()=>(rules with {GlobalDamageBasisPoints=12000}).Validate("Fire"));
        Assert.Throws<InvalidDataException>(()=>rules.Validate("Wood"));
        Assert.Throws<InvalidDataException>(()=>(Rules("Wood").Selected with {RegenerationBudgetBasisPoints=501}).Validate());
        var original=Boss("Fire").Capture();
        Assert.Throws<InvalidDataException>(()=>MonsterCombatState.Restore(original with {ThemeProfile=Rules("Water").Selected}));
    }

    private static MonsterCombatState Boss(string theme)=>Assert.Single(PveBattleFactory.Create(new(new(2,2),ChaosMapLayer.Core,true,false,false,"BOSS"),
        GameConfigCatalog.Current.SeasonDifficulty(0),Rules(theme).Selected).Monsters);
}
