using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

/// <summary>F01 owned input preparation only; no map, encounter clock, rewards or budgeted attempts.</summary>
public sealed class SeasonFirstFortnightInputsTests
{
    private static readonly string[] Cohorts = ["novice", "returning", "skilled"];
    private static readonly JsonSerializerOptions EvidenceJson = new() { WriteIndented = true };
    public static bool Enabled => Environment.GetEnvironmentVariable("FANTASYCARD_RUN_F01_INPUTS") == "1";

    internal sealed record Actor(
        string Id,
        HeroClass Hero,
        string Cohort,
        string[] Cards,
        int[] PermanentCardLevels,
        int PermanentWeaponLevel,
        bool HistoricalOwnershipAssumed);

    /// <summary>Freeze legal decks independently of previous seasonal banks or their earnings.</summary>
    internal static Actor[] DeclareActors()
    {
        var actors = new List<Actor>();
        foreach (var cohort in Cohorts)
        foreach (var hero in Enum.GetValues<HeroClass>())
        {
            var prefix = hero switch
            {
                HeroClass.Priest => "PRI",
                HeroClass.Mage => "MAG",
                HeroClass.Guardian => "GUA",
                _ => throw new InvalidOperationException("Unknown declared hero.")
            };
            var cards = cohort == "novice"
                ? Enumerable.Range(1, 13).Select(index => $"C{index:D2}")
                    .Concat(Enumerable.Range(1, 7).Select(index => $"{prefix}-{index:D2}")).ToArray()
                : SeasonClassEfficiencyPilotTests.Deck(hero, "counter-tempo");
            var level = cohort == "novice" ? 0 : 5;
            actors.Add(new($"F01-{cohort}-{hero}", hero, cohort, cards,
                Enumerable.Repeat(level, cards.Length).ToArray(), level, cohort != "novice"));
        }
        return actors.ToArray();
    }

    /// <summary>Separate first-week scenario: reorganize existing initial copies without granting cards or seasonal capital.</summary>
    internal static Actor[] DeclareSupportedNovices() => Enum.GetValues<HeroClass>()
        .Select(hero => new Actor($"F01-support-novice-{hero}", hero, "novice",
            SeasonStarterSupportTests.Deck("support-guard"), Enumerable.Repeat(0, 20).ToArray(), 0, false)).ToArray();

    [Fact(Skip = "F01 first-week support input preflight only; no actual starts.", SkipUnless = nameof(Enabled))]
    public void SupportedNovicesReorganizeOnlyAlreadyOwnedInitialCards()
    {
        var config = GameConfigCatalog.Current;
        var available = config.Cards.Where(card => card.IsCodex && card.InitiallyUnlocked)
            .ToDictionary(card => card.CardId, card => new OwnedCard(card.CardId, card.HeroClass, (CardRarity)card.Rarity, 1, false));
        Assert.Equal(51, available.Count);
        var actors = DeclareSupportedNovices();
        Assert.Equal(3, actors.Length);
        foreach (var actor in actors)
        {
            DeckRules.Validate(actor.Hero, actor.Cards, available);
            Assert.All(actor.Cards, id => Assert.Contains(id, available.Keys));
            Assert.All(actor.PermanentCardLevels, level => Assert.Equal(0, level));
            Assert.Equal(0, actor.PermanentWeaponLevel);
            Assert.False(actor.HistoricalOwnershipAssumed);
        }
        Write("support-week-inputs.original.json", new { config.Version, config.ContentHash, actors,
            initially_unlocked_count = available.Count, card_grants = 0, seasonal_capital_grants = 0, actual_gameplay_attempts = 0 });
    }

    /// <summary>Use the actual seasonal level projection, without starting a map or advancing time.</summary>
    internal static BattleRoom CreateUnstartedRoom(Actor actor, SeasonContext context, Guid playerId, int seed)
    {
        var config = GameConfigCatalog.Current;
        if (context.ConfigVersion != config.Version)
            throw new InvalidOperationException("F01 input context differs from the frozen current configuration.");
        var room = new BattleRoom(Guid.NewGuid(), config.Version, CombatCardCatalog.Create(config), seed, season: context);
        room.AddPlayer(new(playerId, actor.Hero, actor.Cards, null,
            WeaponLevel: context.ProjectPermanentLevel(actor.PermanentWeaponLevel),
            WornArmor: [],
            CardLevels: actor.PermanentCardLevels.Select(context.ProjectPermanentLevel).ToArray()));
        return room;
    }

    [Fact(Skip = "Explicit F01 owned-input preparation; no gameplay attempts.", SkipUnless = nameof(Enabled))]
    public void DeclaredActorsUseActualStarterCardsOrExplicitHistoricalOwnership()
    {
        var config = GameConfigCatalog.Current;
        Assert.Equal("season-v1-config-17", config.Version);
        var actors = DeclareActors();
        Assert.Equal(9, actors.Length);
        Assert.Equal(9, actors.Select(actor => actor.Id).Distinct(StringComparer.Ordinal).Count());
        foreach (var actor in actors)
        {
            var allowed = config.Cards.Where(card => card.IsCodex && card.Enabled
                    && (actor.HistoricalOwnershipAssumed || card.InitiallyUnlocked))
                .ToDictionary(card => card.CardId,
                    card => new OwnedCard(card.CardId, card.HeroClass, (CardRarity)card.Rarity, 1, false),
                    StringComparer.Ordinal);
            DeckRules.Validate(actor.Hero, actor.Cards, allowed);
            Assert.Equal(20, actor.PermanentCardLevels.Length);
            Assert.Equal(actor.Cohort != "novice", actor.HistoricalOwnershipAssumed);
            var expectedLevel = actor.Cohort == "novice" ? 0 : 5;
            Assert.All(actor.PermanentCardLevels, level => Assert.Equal(expectedLevel, level));
            Assert.Equal(expectedLevel, actor.PermanentWeaponLevel);
            for (var index = 0; index < actor.Cards.Length; index++)
                if (actor.PermanentCardLevels[index] > 0)
                    Assert.Contains(config.CardLevels, row => row.CardId == actor.Cards[index] && row.Level == actor.PermanentCardLevels[index]);
        }
        Write("declared-actors.original.json", new
        {
            config.Version,
            config.ContentHash,
            actors,
            initial_season_gold = 0,
            initial_season_fragments = 0,
            initial_blueprints = 0,
            initial_orange_blueprints = 0,
            initial_season_equipment = Array.Empty<object>(),
            historical_permanent_ownership_is_fixture_not_earned_this_season = true,
            old_D03_bank_capital_imported = false,
            actual_gameplay_attempts = 0
        });
    }

    [Fact(Skip = "Explicit F01 unstarted state projection; no encounter clock.", SkipUnless = nameof(Enabled))]
    public void UnstartedRoomsUseDeclaredSeasonAndProjectOwnedLevelsWithoutAutomaticNoviceGrowth()
    {
        var config = GameConfigCatalog.Current;
        var states = new List<object>();
        foreach (var actor in DeclareActors())
        for (var difficulty = 0; difficulty <= 5; difficulty++)
        {
            var context = new SeasonContext("f01-firstseason", difficulty, "season-v1", config.Version, "season-equipment-v1");
            var playerId = Guid.NewGuid();
            var room = CreateUnstartedRoom(actor, context, playerId, 390001 + difficulty);
            var state = room.CapturePlayer(playerId);
            var cards = state.Combat.Deck.Hand.Concat(state.Combat.Deck.Library).Concat(state.Combat.Deck.Discard).ToArray();
            var expectedLevel = context.ProjectPermanentLevel(actor.PermanentWeaponLevel);
            Assert.Equal(context, room.Season);
            Assert.Equal(TimeSpan.Zero, room.Elapsed);
            Assert.Null(state.Pve);
            Assert.Empty(state.WornArmor!);
            Assert.Equal(20, cards.Length);
            Assert.Equal(actor.Cards.Order(StringComparer.Ordinal), cards.Select(card => card.CardId).Order(StringComparer.Ordinal));
            Assert.All(cards, card => Assert.Equal(expectedLevel, card.Level));
            Assert.Equal(expectedLevel, state.Combat.WeaponLevel);
            if (actor.Cohort == "novice") Assert.Equal(0, expectedLevel);
            states.Add(new { actor.Id, context, owned_permanent_level = actor.PermanentWeaponLevel,
                actual_effective_level = expectedLevel, unstarted_elapsed_seconds = room.Elapsed.TotalSeconds,
                no_map_or_battle_executed = true });
        }
        Assert.Equal(54, states.Count);
        Write("unstarted-projections.original.json", new { states, actual_gameplay_attempts = 0,
            does_not_prove_unlocks_or_open_difficulty = true, model_calendar_not_run = true });
    }

    private static void Write(string name, object value)
    {
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_F01_INPUT_OUTPUT")
            ?? throw new InvalidOperationException("New owned F01 evidence directory required.");
        Directory.CreateDirectory(output);
        var path = Path.Combine(output, name);
        Assert.False(File.Exists(path));
        File.WriteAllText(path, JsonSerializer.Serialize(value, EvidenceJson));
    }
}
