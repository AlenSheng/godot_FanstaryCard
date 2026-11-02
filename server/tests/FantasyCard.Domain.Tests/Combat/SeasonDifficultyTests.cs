using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class SeasonDifficultyTests
{
    private static readonly string[] Groups = ["O1","O2","O3","O4","O5","O6","O7","O8","M1","M2","M3","M4","M5","E1","E2","E3","E4","E5","E6","BOSS","BOX"];
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private static readonly int[] NakedIntentDamage = [3,3,4,5,6,7];

    [Theory]
    [InlineData(0,78,200,280,2,3)]
    [InlineData(1,124,320,448,2,3)]
    [InlineData(2,202,520,728,3,4)]
    [InlineData(3,312,800,1120,3,5)]
    [InlineData(4,452,1160,1624,4,6)]
    [InlineData(5,624,1600,2240,5,7)]
    public void PublishedSixDifficultyVectorsUseFixedPointFloors(int difficulty,int batHp,int guardHp,int bossHp,int two,int three)
    {
        var config = GameConfigCatalog.Current.SeasonDifficulty(difficulty);
        Assert.Equal(batHp,Create("O1",config).Monsters[0].MaximumHp);
        Assert.Equal(guardHp,Create("E1",config).Monsters[0].MaximumHp);
        Assert.Equal(bossHp,Create("BOSS",config).Monsters[0].MaximumHp);
        Assert.Equal(two,SeasonDifficultyConfig.Scale(2,config.DamageBasisPoints));
        Assert.Equal(three,SeasonDifficultyConfig.Scale(3,config.DamageBasisPoints));
    }

    [Fact]
    public void EveryGeneratedGroupAcrossSixDifficultiesRestoresWithoutRescalingHealthOrIntents()
    {
        var encounters = 0;
        foreach (var config in GameConfigCatalog.Current.SeasonDifficulties)
        foreach (var group in Groups)
        {
            var legacy = Create(group,null);var battle = Create(group,config);encounters++;
            for (var index=0;index<battle.Monsters.Count;index++)
            {
                var original = legacy.Monsters[index];var monster = battle.Monsters[index];
                Assert.Equal(Math.Max(1,SeasonDifficultyConfig.Scale(original.MaximumHp,config.HpBasisPoints)),monster.MaximumHp);
                Assert.Equal(original.Intents,monster.Intents);
                Assert.Equal(original.ElementalResistance(CardElement.Fire),monster.ElementalResistance(CardElement.Fire));
                var saved = monster.Capture();var restored = MonsterCombatState.Restore(saved);
                Assert.Equivalent(saved,restored.Capture(),strict:true);
                Assert.Equal(monster.MaximumHp,restored.MaximumHp);
                Assert.Equal(config.DamageBasisPoints,monster.DifficultyProfile!.DamageBasisPoints);
            }
        }
        Assert.Equal(126,encounters);
    }

    [Fact]
    public void ChargePrecedesDifficultyAndShieldCycleHasItsOwnScaleAndCap()
    {
        var difficulty = GameConfigCatalog.Current.SeasonDifficulty(5);
        var herald = Create("E2",difficulty).Monsters[0];
        herald.ResolveUtilityIntent(herald.Intents[1]);
        Assert.Equal(26,herald.ResolveIntentDamage(herald.Intents[2],0,out var effective));
        Assert.Equal(23,effective); // floor(floor(6*1.5)*2.6), then floor(23*1.15).
        var guard = Create("E1",difficulty).Monsters[0];
        Assert.Equal(96,guard.Shield);
        guard.TakeDamage(96);guard.ResolveUtilityIntent(guard.Intents[2]);
        Assert.Equal(96,guard.Shield);
        guard.GainShield(int.MaxValue);Assert.Equal(800,guard.Shield);
        Assert.Equal(0,guard.GainShield(1));
    }

    [Theory]
    [InlineData(0)] [InlineData(1)] [InlineData(2)] [InlineData(3)] [InlineData(4)] [InlineData(5)]
    public void BossChangesAfterItsCurrentStepAtRelativeHalfHealthWithoutAddingAnotherHealthPool(int difficulty)
    {
        var config = GameConfigCatalog.Current.SeasonDifficulty(difficulty);
        var boss = Create("BOSS",config).Monsters[0];var half = boss.MaximumHp/2;
        boss.TakeDamage(boss.Shield+boss.MaximumHp-half);
        Assert.True(boss.BossPhaseTransitionPending);Assert.Equal(1,boss.BossPhase);
        boss = MonsterCombatState.Restore(boss.Capture());
        boss.ResolveIntentDamage(boss.Intents[0]);
        Assert.Equal(2,boss.BossPhase);Assert.Equal(half,boss.Hp);
        Assert.Equal(SeasonDifficultyConfig.ScaleInterval(TimeSpan.FromMilliseconds(3800),config.IntervalBasisPoints),boss.AttackInterval);
        if (difficulty==5)
        {
            Assert.Equal(15,boss.ResolveIntentDamage(boss.Intents[0]));
            Assert.Equal(20,boss.ResolveIntentDamage(boss.Intents[5]));
        }
        Assert.Equivalent(boss.Capture(),MonsterCombatState.Restore(boss.Capture()).Capture(),strict:true);
    }

    [Fact]
    public void NormalAndEliteWindupsStayFixedAndIntervalUsesIntegerMilliseconds()
    {
        var config = GameConfigCatalog.Current.SeasonDifficulty(5);
        var bat = Create("O1",config).Monsters[0];Assert.Equal(3312,bat.AttackInterval.TotalMilliseconds);
        Assert.Null(bat.Advance(TimeSpan.FromMilliseconds(2712)));
        Assert.Equal(600,bat.WindupRemaining.TotalMilliseconds);
        Assert.NotNull(bat.Advance(TimeSpan.FromMilliseconds(600)));
        var guard = Create("E1",config).Monsters[0];
        Assert.Null(guard.Advance(TimeSpan.FromMilliseconds(3248)));
        Assert.Equal(800,guard.WindupRemaining.TotalMilliseconds);
        var herald = Create("E2",config).Monsters[0];
        herald.SetRuntimeState(1,TimeSpan.Zero,TimeSpan.Zero,false,0,TimeSpan.Zero,new Dictionary<string,TimeSpan>());
        Assert.Null(herald.Advance(TimeSpan.FromMilliseconds(2664)));Assert.Equal(1200,herald.WindupRemaining.TotalMilliseconds);
        var old = Create("E1",null).Monsters[0];old.Advance(old.AttackInterval);Assert.Equal(600,old.WindupRemaining.TotalMilliseconds);
    }

    [Fact]
    public void Real100MillisecondClockKeepsTheD5GuardShieldCycleNearSixteenPointTwoSeconds()
    {
        var guard = Create("E1",GameConfigCatalog.Current.SeasonDifficulty(5)).Monsters[0];
        var shields = new List<int>();
        for (var tick=1;tick<=400 && shields.Count<2;tick++)
        {
            var intent = guard.Advance(TimeSpan.FromMilliseconds(100));
            if (intent is null) continue;
            if (intent.Kind == MonsterIntentKind.Shield) shields.Add(tick*100);
            if (intent.Kind is MonsterIntentKind.Attack or MonsterIntentKind.Direct) guard.ResolveIntentDamage(intent);
            else guard.ResolveUtilityIntent(intent);
        }
        Assert.Equal(2,shields.Count);Assert.InRange(shields[1]-shields[0],16100,16300);
    }

    [Theory]
    [InlineData(HeroClass.Mage,70)] [InlineData(HeroClass.Priest,80)] [InlineData(HeroClass.Guardian,100)]
    public void ActualRoomClockUsesDifficultyForAllClassesWithoutChangingTheirLegalBaseHealth(HeroClass hero,int hp)
    {
        for (var difficulty=0;difficulty<6;difficulty++)
        {
            var context = new SeasonContext("difficulty",difficulty,"season-v1",GameConfigCatalog.Current.Version,"difficulty-test");
            var room = new BattleRoom(Guid.NewGuid(),context.ConfigVersion,CombatCardCatalog.Create(GameConfigCatalog.Current),73,season:context);
            var cards = SeasonFenxianTests.Starter(hero);SeasonFenxianTests.ValidateDeck(hero,cards);
            var battle = Create("O1",GameConfigCatalog.Current.SeasonDifficulty(difficulty));
            var player = room.AddPlayer(new(Guid.NewGuid(),hero,cards,battle));
            Assert.Equal(hp,player.Combat.MaximumHp);
            for (var tick=0;tick<60 && player.Combat.Hp==hp;tick++) room.Advance(TimeSpan.FromMilliseconds(100));
            Assert.Equal(NakedIntentDamage[difficulty],hp-player.Combat.Hp);
        }
    }

    [Fact]
    public void RoomSnapshotPinsGeneratedPoliciesAndRejectsMissingOrDifferentScaling()
    {
        var context = new SeasonContext("snapshot",5,"season-v1",GameConfigCatalog.Current.Version,"difficulty-test");
        var catalog = CombatCardCatalog.Create(GameConfigCatalog.Current);
        var room = new BattleRoom(Guid.NewGuid(),context.ConfigVersion,catalog,73,season:context);
        room.AddPlayer(new(Guid.NewGuid(),HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null));
        room.InitializeMap(ChaosMapGenerator.Generate(73,1));
        var snapshot = room.Capture();
        var json = JsonSerializer.Serialize(snapshot,Json);
        var decoded = JsonSerializer.Deserialize<BattleRoomSnapshot>(json,Json)!;
        Assert.Equivalent(snapshot,BattleRoom.Restore(decoded,catalog,73).Capture(),strict:true);
        var bad = snapshot with {Players=snapshot.Players.Select(p=>p with {Pve=p.Pve! with
            {Monsters=p.Pve.Monsters.Select(m=>m with {DifficultyProfile=null}).ToArray()}}).ToArray()};
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(bad,catalog,73));
    }

    private static PveBattleState Create(string group,SeasonDifficultyConfig? difficulty) =>
        PveBattleFactory.Create(new(new(0,0),group.StartsWith('E') || group=="BOSS" ? ChaosMapLayer.Core : ChaosMapLayer.Outer,
            group=="BOSS",false,false,group,CardElement.Fire),difficulty);
}
