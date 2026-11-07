using System.Text.Json;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonArchiveReadTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private const string Required="Requires isolated PostgreSQL.";
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;
    private static async Task<PostgresTestSchema> OpenAsync()
    {
        var db=await PostgresTestSchema.CreateAsync(false);
        try
        {
            var output=Environment.GetEnvironmentVariable("FANTASYCARD_ARCHIVE_READ_SCHEMA_EVIDENCE");
            if(output is not null)File.AppendAllText(output,JsonSerializer.Serialize(new {schema=new NpgsqlConnectionStringBuilder(db.ConnectionString).SearchPath,kind="archive-read",at=DateTimeOffset.UtcNow})+Environment.NewLine);
            await db.MigrateAsync();return db;
        }
        catch{await db.DisposeAsync();throw;}
    }
    private static async Task<CraftingPlayer> OriginalAsync(PostgresTestSchema db)
    {
        using var stream=typeof(PostgresSeasonArchiveReadTests).Assembly.GetManifestResourceStream("ArchivedD0Config15")!;
        using var bytes=new MemoryStream();await stream.CopyToAsync(bytes,Ct);var original=GameConfigCatalog.Load(bytes.ToArray());
        var season=SeasonDefinition.FromCalendarDays("archive-original",new(2026,11,1),original.Version,"season-equipment-v1",highestOpenDifficulty:5);
        var clock=new CraftingClock(season.StartsAtUtc.AddHours(2));var player=await CraftingTestInputs.PlayerAsync(db,clock);
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,original.ContentHash,Ct,original);
        await seasons.EnsurePlayerAsync(player,season.ContextFor(0),Ct);
        return new(player,season,clock,seasons,new(db.DataSource,clock,new(original)));
    }
    private static async Task<string> Snapshot(PostgresTestSchema db,Guid player)=>await db.ScalarAsync<string>("""
        SELECT jsonb_build_object(
            'equipment',(SELECT jsonb_agg(to_jsonb(e) ORDER BY instance_id) FROM equipments e WHERE owner_id=$1),
            'state',(SELECT jsonb_agg(to_jsonb(s) ORDER BY season_id) FROM player_season_state s WHERE player_id=$1),
            'wallet',(SELECT jsonb_agg(to_jsonb(w) ORDER BY season_id) FROM player_season_wallets w WHERE player_id=$1),
            'jobs',(SELECT jsonb_agg(to_jsonb(j) ORDER BY job_id) FROM season_archive_jobs j WHERE player_id=$1),
            'recipes',(SELECT jsonb_agg(to_jsonb(r) ORDER BY recipe_id) FROM learned_season_recipes r WHERE player_id=$1),
            'wishes',(SELECT jsonb_agg(to_jsonb(p) ORDER BY quality,slot,element,wished_effect) FROM player_crafting_wishes p WHERE player_id=$1),
            'loadouts',(SELECT jsonb_agg(to_jsonb(l) ORDER BY season_id,hero_class) FROM season_archive_loadouts l WHERE player_id=$1),
            'movements',(SELECT count(*) FROM inventory_movements WHERE player_id=$1))::text
        """,player);

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task EndedOriginalPagesRetainAllLocationsAndExactMetadataWithoutAnyWriteOrCurrentSeasonFallback()
    {
        await using var db=await OpenAsync();var f=await OriginalAsync(db);var ids=new List<Guid>();
        foreach(var location in new[]{"SeasonArchive","MarketReturnPending","Recycled","EnhanceMaterialConsumed","InMatchBackpack"})
        {
            var id=await CraftingTestInputs.ItemAsync(db,f,level:3,bound:true);ids.Add(id);
            await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location=$2,asset_scope=$3 WHERE instance_id=$1",id,location,location=="InMatchBackpack"?"ActiveSeason":"ArchivedSeason");
        }
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_wallets SET gold=9007199254740993,equipment_fragments=123,challenge_marks=77,blueprint_marks=4,orange_blueprint_marks=14 WHERE player_id=$1",f.Player);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO season_archive_jobs(job_id,player_id,from_season_id,status,phase,created_at,updated_at) VALUES($1,$2,$3,'WaitingAssets','WaitingAssets',now(),now())",Guid.NewGuid(),f.Player,f.Season.SeasonId);
        var other=await CraftingTestInputs.PlayerAsync(db,f.Clock);await f.Seasons.EnsurePlayerAsync(other,f.Season.ContextFor(0),Ct);
        await CraftingTestInputs.ItemAsync(db,f with {Player=other});
        f.Clock.Now=f.Season.EndsAtUtc.AddHours(1);
        var current=SeasonDefinition.FromCalendarDays("archive-current",DateOnly.FromDateTime(TimeZoneInfo.ConvertTime(f.Season.EndsAtUtc,TimeZoneInfo.FindSystemTimeZoneById(SeasonDefinition.TimeZoneId)).DateTime),GameConfigCatalog.Current.Version,"season-equipment-v1");
        await f.Seasons.PublishAsync(current,GameConfigCatalog.Current.ContentHash,Ct);await f.Seasons.EnsurePlayerAsync(f.Player,current.ContextFor(0),Ct);
        var newInputs=f with {Season=current};await CraftingTestInputs.ItemAsync(db,newInputs,"Blue",effect:null);
        var before=await Snapshot(db,f.Player);var reader=new ProgressionRepository(db.DataSource,f.Clock);
        var list=await reader.GetSeasonArchivesAsync(f.Player,1,0,Ct);var source=Assert.Single(list.Items);
        Assert.Equal("season-v1-config-15",source.ConfigVersion);Assert.NotEqual(GameConfigCatalog.Current.Version,source.ConfigVersion);
        Assert.Equal("WaitingAssets",source.Status);Assert.Equal(5,source.EquipmentCount);Assert.Equal(9007199254740993,source.Wallet!.Gold);
        Assert.Equal(77,source.Wallet.ChallengeMarks);Assert.Equal(4,source.Wallet.BlueprintMarks);Assert.Equal(14,source.Wallet.OrangeBlueprintMarks);
        var all=new List<FantasyCard.Contracts.Progression.EquipmentResponse>();int? offset=0;
        while(offset is not null)
        {
            var page=(await reader.GetSeasonArchiveSectionAsync(f.Player,f.Season.SeasonId,"equipment",2,offset.Value,Ct))!;
            Assert.True(page.ReadOnly);Assert.Equal(source,page.Season);Assert.Empty(page.Recipes);Assert.Empty(page.Wishes);Assert.Empty(page.Loadouts);
            Assert.All(page.Equipments,item=>{Assert.Equal(f.Season.SeasonId,item.SeasonId);Assert.Equal(3,item.Level);Assert.True(item.IsBound);});
            all.AddRange(page.Equipments);offset=page.NextOffset;
        }
        Assert.Equal(ids.Order(),all.Select(x=>x.InstanceId).Order());Assert.Equal(5,all.Select(x=>x.Location).Distinct().Count());
        Assert.Null(await reader.GetSeasonArchiveSectionAsync(f.Player,current.SeasonId,"equipment",20,0,Ct));
        Assert.Empty((await reader.GetSeasonArchivesAsync(f.Player,20,5,Ct)).Items);
        Assert.Equal(before,await Snapshot(db,f.Player));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task RecipesPityAndOriginalLoadoutReferencesAreBoundedAndDoNotUseCurrentPolicyOrLoadouts()
    {
        await using var db=await OpenAsync();var f=await OriginalAsync(db);var ids=new List<Guid>();
        foreach(var slot in new[]{"Head","Chest","Hands"})
        {
            var id=await CraftingTestInputs.ItemAsync(db,f,slot:slot);ids.Add(id);
            await f.Progression.LearnSeasonRecipeAsync(f.Player,"learn-"+slot,new(f.Season.SeasonId,id,1),Ct);
            await CraftingTestInputs.SqlAsync(db,"INSERT INTO player_crafting_wishes(player_id,season_id,quality,slot,element,wished_effect,failures,updated_at) VALUES($1,$2,'Purple',$3,'Water','Vitality',2,now())",f.Player,f.Season.SeasonId,slot);
        }
        for(short hero=1;hero<=3;hero++)await CraftingTestInputs.SqlAsync(db,"INSERT INTO season_archive_loadouts(player_id,season_id,hero_class,head_id,chest_id,hands_id,original_version,archived_at) VALUES($1,$2,$3,$4,$5,$6,9,now())",f.Player,f.Season.SeasonId,hero,ids[0],ids[1],ids[2]);
        f.Clock.Now=f.Season.EndsAtUtc;var reader=new ProgressionRepository(db.DataSource,f.Clock);var before=await Snapshot(db,f.Player);
        foreach(var section in new[]{"recipes","wishes","loadouts"})
        {
            var page=(await reader.GetSeasonArchiveSectionAsync(f.Player,f.Season.SeasonId,section,2,0,Ct))!;
            Assert.True(page.ReadOnly);Assert.Equal(2,page.NextOffset);
            var last=(await reader.GetSeasonArchiveSectionAsync(f.Player,f.Season.SeasonId,section,2,2,Ct))!;Assert.Null(last.NextOffset);
            if(section=="recipes"){Assert.Equal(2,page.Recipes.Count);Assert.Single(last.Recipes);Assert.All(page.Recipes,x=>Assert.Equal(f.Season.StatsVersion,x.StatsVersion));}
            if(section=="wishes"){Assert.Equal(2,page.Wishes.Count);Assert.Single(last.Wishes);Assert.All(page.Wishes,x=>Assert.Equal(2,x.Failures));}
            if(section=="loadouts"){Assert.Equal(3,page.ReferencedEquipments!.Count);Assert.Equal(2,page.Loadouts.Count);Assert.Single(last.Loadouts);Assert.All(page.Loadouts,x=>{Assert.Equal(9,x.Version);Assert.Equal(ids[0],x.EquipmentIds[0]);Assert.Equal(ids[1],x.EquipmentIds[1]);Assert.Equal(ids[2],x.EquipmentIds[2]);Assert.Equal(f.Season.SeasonId,x.SeasonId);});}
        }
        Assert.Equal(before,await Snapshot(db,f.Player));
        // Retain the historical reference, but never expose another account's current item row.
        var other=await CraftingTestInputs.PlayerAsync(db,f.Clock);
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET owner_id=$2 WHERE instance_id=$1",ids[0],other);
        var transferred=(await f.Progression.GetSeasonArchiveSectionAsync(f.Player,f.Season.SeasonId,"loadouts",20,0,Ct))!;
        Assert.Contains(ids[0],transferred.Loadouts[0].EquipmentIds);
        Assert.Equal(2,transferred.ReferencedEquipments!.Count);
        Assert.DoesNotContain(transferred.ReferencedEquipments,item=>item.InstanceId==ids[0]);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ForeignAndActiveMembershipsAreNotExposedAndEndedSeasonsPaginateDeterministically()
    {
        await using var db=await OpenAsync();var f=await OriginalAsync(db);var other=await CraftingTestInputs.PlayerAsync(db,f.Clock);
        await f.Seasons.EnsurePlayerAsync(other,f.Season.ContextFor(0),Ct);Assert.Empty((await f.Progression.GetSeasonArchivesAsync(f.Player,20,0,Ct)).Items);
        f.Clock.Now=f.Season.EndsAtUtc;
        var next=SeasonDefinition.FromCalendarDays("archive-next",DateOnly.FromDateTime(TimeZoneInfo.ConvertTime(f.Season.EndsAtUtc,TimeZoneInfo.FindSystemTimeZoneById(SeasonDefinition.TimeZoneId)).DateTime),GameConfigCatalog.Current.Version,"season-equipment-v1");
        await f.Seasons.PublishAsync(next,GameConfigCatalog.Current.ContentHash,Ct);await f.Seasons.EnsurePlayerAsync(f.Player,next.ContextFor(0),Ct);
        f.Clock.Now=next.EndsAtUtc;var a=await f.Progression.GetSeasonArchivesAsync(f.Player,1,0,Ct);Assert.Equal(next.SeasonId,Assert.Single(a.Items).SeasonId);Assert.Equal(1,a.NextOffset);
        var b=await f.Progression.GetSeasonArchivesAsync(f.Player,1,1,Ct);Assert.Equal(f.Season.SeasonId,Assert.Single(b.Items).SeasonId);Assert.Null(b.NextOffset);
        Assert.Null(await new ProgressionRepository(db.DataSource,f.Clock).GetSeasonArchiveSectionAsync(other,next.SeasonId,"equipment",20,0,Ct));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task LegacyMarkerKeepsUnknownDatesVersionsAndOpaqueBalancesWhileCurrentSeasonIsActive()
    {
        await using var db=await OpenAsync();var f=await CraftingTestInputs.CreateAsync(db);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO player_season_state(player_id,season_id,joined_at,archived_at) VALUES($1,'legacy-gdd-0.70',now(),now())",f.Player);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO player_season_wallets(player_id,season_id,gold,equipment_fragments,challenge_marks,archived_at) VALUES($1,'legacy-gdd-0.70',123,456,77,now())",f.Player);
        var id=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"INSERT INTO equipments(instance_id,owner_id,slot,quality,location,origin_season_id,season_id,asset_scope,created_at) VALUES($1,$2,'Head','White','SeasonArchive','legacy-gdd-0.70','legacy-gdd-0.70','ArchivedSeason',now())",id,f.Player);
        var before=await Snapshot(db,f.Player);var row=Assert.Single((await f.Progression.GetSeasonArchivesAsync(f.Player,20,0,Ct)).Items);
        Assert.Equal("Legacy",row.Status);Assert.Null(row.StartsAt);Assert.Null(row.EndsAt);Assert.Null(row.ConfigVersion);Assert.Null(row.ConfigSha256);Assert.Null(row.StatsVersion);
        Assert.Equal(77,row.Wallet!.ChallengeMarks);Assert.False(row.Wallet.CanFundWeapon);
        var page=(await f.Progression.GetSeasonArchiveSectionAsync(f.Player,row.SeasonId,"equipment",20,0,Ct))!;
        Assert.True(page.ReadOnly);Assert.Equal(id,Assert.Single(page.Equipments).InstanceId);Assert.Null(page.Equipments[0].StatsVersion);
        Assert.Equal(before,await Snapshot(db,f.Player));
    }
}
