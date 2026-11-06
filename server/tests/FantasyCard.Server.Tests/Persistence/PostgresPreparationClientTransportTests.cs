using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.ConfigExporter;
using FantasyCard.Contracts.Configuration;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Config;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresPreparationClientTransportTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task RealDraftAndLockedBootstrapsKeepArchivedPreparationValuesAndProduceNativeInputs()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        var source=PreparationConfigTestInputs.Original();
        var season=SeasonDefinition.FromCalendarDays("preparation-client-source",new(2026,11,1),source.Version,PreparationConfigTestInputs.StatsVersion,highestOpenDifficulty:5);
        var clock=new CraftingClock(season.StartsAtUtc.AddHours(2));
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,source.ContentHash,Ct,source);
        using var archive=new ConfigArchiveDirectory();PublishedConfigTestInputs.Store(archive.Root,source.Version,source.ExportPublishedBytes(),source.ContentHash);
        var catalogs=new PublishedConfigCatalogs(GameConfigCatalog.Current,archive.Root);
        var preparations=new PreparationRepository(db.DataSource,clock,catalogs);
        var progression=new ProgressionRepository(db.DataSource,clock,catalogs);
        using var economy=new EconomyRepository(db.DataSource,clock,configurations:catalogs);
        var bootstrap=new BootstrapRepository(db.DataSource,progression,economy,new MailRepository(db.DataSource,clock),preparations,clock);
        var directory=Environment.GetEnvironmentVariable("FANTASYCARD_PREPARATION_INTEROP_OUTPUT")
            ?? Path.Combine(PublishedConfigTestInputs.FindRoot(),"server/.artifacts/preparation-client");
        Directory.CreateDirectory(directory);
        var hashes=new Dictionary<string,string>(StringComparer.Ordinal);
        void Save(string name,byte[] bytes)
        {
            File.WriteAllBytes(Path.Combine(directory,name),bytes);hashes.Add(name,Convert.ToHexStringLower(SHA256.HashData(bytes)));
        }
        Save("original.configuration.envelope",HttpDtoMapper.EncodeResponse(HttpProtocolRegistry.Find("GET","/api/v1/config/"+source.Version)!,
            new PublishedConfigurationResponse(source.Version,source.ContentHash,source.ExportPublishedBytes())));
        // An independently valid body with the same label is a negative cache
        // replacement control. It is never installed or published to the DB.
        var collision=ConfigCompiler.Compile(source.Version,XlsxConfigReader.Read(Path.Combine(PublishedConfigTestInputs.FindRoot(),"config/FantasyCard_Config.xlsx")),out var collisionHash);
        Assert.NotEqual(source.ContentHash,collisionHash);
        Save("collision.configuration.envelope",HttpDtoMapper.EncodeResponse(HttpProtocolRegistry.Find("GET","/api/v1/config/"+source.Version)!,
            new PublishedConfigurationResponse(source.Version,collisionHash,collision)));
        var cases=new List<object>();
        foreach(var borrowed in new[] {false,true})
        {
            var name=borrowed?"borrowed":"owned";
            var player=await new IdentityRepository(db.DataSource,new PlayerProvisioningService()).SignInLocalAsync(Guid.NewGuid().ToString("N"),
                "Prep-"+Guid.NewGuid().ToString("N")[..10],RandomNumberGenerator.GetBytes(32),clock.Now,clock.Now.AddHours(1),Ct);
            await seasons.EnsurePlayerAsync(player.UserId,season.ContextFor(0),Ct);
            await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1 AND season_id=$2",player.UserId,season.SeasonId);
            await CraftingTestInputs.SqlAsync(db,"WITH cards AS(UPDATE player_cards SET level=5 WHERE player_id=$1 AND unlocked RETURNING player_id) UPDATE class_weapons SET level=5 WHERE player_id=$1",player.UserId);
            var item=Guid.NewGuid();
            await CraftingTestInputs.SqlAsync(db,"""
                INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,created_at,element,secondary_trait,
                    origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
                VALUES($1,$2,'Head','Green',5,'Equipped',$3,'Wood','DrawInterval',$4,$4,'ActiveSeason',$5,'NaturalDrop',1)
                """,item,player.UserId,clock.Now,season.SeasonId,season.StatsVersion);
            await CraftingTestInputs.SqlAsync(db,"UPDATE player_loadouts SET head_id=$1 WHERE player_id=$2 AND hero_class=2",item,player.UserId);
            var before=await bootstrap.GetAsync(player,Ct);
            Assert.Null(before.ActivePreparation);Assert.Equal(source.Version,before.Season!.ConfigVersion);
            Assert.Equal(GameConfigCatalog.Current.Version,before.ConfigVersion);Assert.NotEqual(before.ConfigVersion,before.Season.ConfigVersion);
            Save(name+".draft.bootstrap.envelope",HttpDtoMapper.EncodeResponse(HttpProtocolRegistry.Find("GET","/api/v1/bootstrap")!,before));
            var deckVersion=await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2",player.UserId);
            var request=new CreatePreparationRequest(HeroClassDto.Mage,borrowed?0:deckVersion,[item,null,null,null,null],BackpackTierDto.Free,[],0,"D1",season.SeasonId,borrowed);
            var prepared=await preparations.CreateAsync(player.UserId,"native-source-"+name,request,Ct);
            Assert.Equal(CreatePreparationStatus.Created,prepared.Status);var snapshot=prepared.Preparation!.Snapshot;
            Assert.Equal(21,snapshot.BackpackCapacity);Assert.Equal("Wood",snapshot.LootPreferenceElement);Assert.Equal(1,snapshot.ClassWeaponLevel);
            Assert.Equal(5,snapshot.ActualClassWeaponLevel);Assert.All(snapshot.CardLevels!,level=>Assert.Equal(1,level));
            // The D-tier cap projects cards and signature weapons; armor keeps
            // its real enhancement level, as does the authoritative snapshot.
            Assert.Equal(5,Assert.Single(snapshot.EquipmentSnapshots!).Level);Assert.Equal(PreparationConfigTestInputs.StatsVersion,Assert.Single(snapshot.EquipmentSnapshots!).StatsVersion);
            if(borrowed){Assert.Equal("archive-loan-mage",snapshot.BorrowedTemplateId);Assert.Equal("C30",snapshot.CardIds[12]);}
            else {Assert.Null(snapshot.BorrowedTemplateId);Assert.All(snapshot.ActualCardLevels!,level=>Assert.Equal(5,level));}
            Save(name+".preparation.envelope",HttpDtoMapper.EncodeResponse(HttpProtocolRegistry.Find("POST","/api/v1/preparations")!,prepared.Preparation));
            var locked=await bootstrap.GetAsync(player,Ct);Assert.Equal(prepared.Preparation.PreparationId,locked.ActivePreparation!.PreparationId);
            Save(name+".locked.bootstrap.envelope",HttpDtoMapper.EncodeResponse(HttpProtocolRegistry.Find("GET","/api/v1/bootstrap")!,locked));
            Assert.Equal(5,await db.ScalarAsync<int>("SELECT level FROM class_weapons WHERE player_id=$1 AND hero_class=2",player.UserId));
            Assert.Equal(5,await db.ScalarAsync<int>("SELECT level FROM equipments WHERE instance_id=$1",item));
            Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM player_cards WHERE player_id=$1 AND unlocked AND level<>5",player.UserId));
            cases.Add(new {name,borrowed,heroClass="Mage",sourceVersion=source.Version,statsVersion=season.StatsVersion,seasonId=season.SeasonId,
                originalBag=source.Backpack("Free").Capacity,entryQuality=SeasonLootConfig.Quality(source.SeasonDifficulty(1).EntryQualityCap),
                templateId=borrowed?source.BorrowedDeck(FantasyCard.Domain.Players.HeroClass.Mage).TemplateId:null,
                cardIds=snapshot.CardIds,cardLevels=snapshot.CardLevels,actualCardLevels=snapshot.ActualCardLevels,
                originalDamage=CombatCardCatalog.Create(source).Get("C01",1).Effect.ElementalDamage,originalPreference="Wood",permanentWeaponLevel=5,
                effectiveWeaponLevel=1,originalHash=source.ContentHash,preparationId=prepared.Preparation.PreparationId});
        }
        Save("cases.json",JsonSerializer.SerializeToUtf8Bytes(cases));
        File.WriteAllText(Path.Combine(directory,"input-manifest.json"),JsonSerializer.Serialize(hashes));
    }
}
