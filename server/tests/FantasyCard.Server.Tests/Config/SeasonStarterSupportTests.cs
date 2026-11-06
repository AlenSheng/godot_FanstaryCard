using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Exploratory owned-initial-card reorganizations; branch outputs never replenish an observed bank.</summary>
public sealed class SeasonStarterSupportTests
{
    public static bool Enabled=>Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D03_STARTER_SUPPORT")=="1";
    private static readonly string[] Mix=["C01","C03","C04","C05","C06","C07","C08","C09","C10","C11","C12","C14","C21","C30","C22","C23","C28","C29","C27","C16"];
    private static readonly string[] Guard=["C01","C03","C04","C05","C06","C07","C08","C09","C10","C24","C12","C15","C21","C30","C22","C23","C28","C29","C27","C16"];
    private sealed record Case(string Id,string Hero,string Loadout,int Seed);
    internal static string[] Deck(string variant)=>variant switch{"support-mix"=>Mix.ToArray(),"support-guard"=>Guard.ToArray(),_=>throw new InvalidOperationException("Unknown declared support candidate.")};
    private static Case[] Plan()
    {
        using var doc=JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_SUPPORT_PLAN")??throw new InvalidOperationException("Frozen support roster required.")));
        var prior=doc.RootElement.GetProperty("prior_used").GetInt32();var rows=doc.RootElement.GetProperty("cases").EnumerateArray().Select(x=>new Case(x.GetProperty("id").GetString()!,x.GetProperty("hero").GetString()!,x.GetProperty("loadout").GetString()!,x.GetProperty("seed").GetInt32())).ToArray();
        Assert.InRange(prior,0,299);Assert.InRange(rows.Length,1,300-prior);Assert.Equal(rows.Length,rows.Select(x=>x.Id).Distinct(StringComparer.Ordinal).Count());
        foreach(var row in rows){Assert.True(Enum.TryParse<HeroClass>(row.Hero,out var hero)&&Enum.IsDefined(hero));Assert.True(row.Loadout is "support-mix" or "support-guard");}return rows;
    }
    [Fact(Skip="Explicit D03 owned-starter support preflight, no battle clock.",SkipUnless=nameof(Enabled))]
    public void SupportCandidatesUseOnlyAlreadyUnlockedOwnedInitialCards()
    {
        var config=GameConfigCatalog.Current;var available=config.Cards.Where(x=>x.IsCodex&&x.InitiallyUnlocked).ToDictionary(x=>x.CardId,x=>new OwnedCard(x.CardId,x.HeroClass,(CardRarity)x.Rarity,1,false));var rows=Plan();
        foreach(var row in rows){var deck=Deck(row.Loadout);Assert.Equal(20,deck.Length);Assert.All(deck,id=>Assert.True(config.Cards.Single(x=>x.CardId==id).InitiallyUnlocked));DeckRules.Validate(Enum.Parse<HeroClass>(row.Hero),deck,available);}
        File.WriteAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_SUPPORT_PREFLIGHT_OUTPUT")??throw new InvalidOperationException("New proof path required."),JsonSerializer.Serialize(new {cases=rows.Length,config.Version,config.ContentHash,owned_initial_51=config.Cards.Count(x=>x.InitiallyUnlocked),new_matches=0,published_template_modified=false}));
    }
    [Fact(Skip="Budgeted D03 counterfactual support branches, not longitudinal bank grants.",SkipUnless=nameof(Enabled))]
    public void DeclaredSupportBranchesRecordRealUnmodifiedD0Outcomes()
    {
        var rows=Plan();var root=Environment.GetEnvironmentVariable("FANTASYCARD_D03_SUPPORT_OUTPUT")??throw new InvalidOperationException("Owned output required.");Assert.False(Directory.Exists(root));Directory.CreateDirectory(root);
        using var attempts=new StreamWriter(Path.Combine(root,"attempts.original.jsonl"));using var trace=new StreamWriter(Path.Combine(root,"events.original.jsonl"));using var results=new StreamWriter(Path.Combine(root,"routes.original.jsonl"));
        foreach(var row in rows)
        {
            attempts.WriteLine(JsonSerializer.Serialize(row));attempts.Flush();var scenario=new SeasonCohortRouteTests.Scenario(row.Id,row.Hero,"novice",row.Seed,0,"natural-shortest",true,true,row.Loadout);
            SeasonCohortRouteTests.Run(scenario,trace,results,Array.Empty<ExplorationItem>());trace.Flush();results.Flush();
        }
    }
}
