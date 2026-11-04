using System.Security.Cryptography;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresPermanentCardCopyTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;
    private const string RequiresDatabase="Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.";

    [Fact(Skip=RequiresDatabase,SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task Opt_in_preserves_all_permanent_rows_and_keeps_its_first_configuration_after_restart()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var player=await CreatePlayer(db);
        var repo=new ProgressionRepository(db.DataSource);var before=await repo.GetCardsAsync(player,Ct);var decks=await repo.GetDecksAsync(player,Ct);
        await Enable(db,player,"season-shop-config-9");await Enable(db,player,"later-season-config");
        var after=await new ProgressionRepository(db.DataSource).GetCardsAsync(player,Ct);
        Assert.Equal(before,after);Assert.Equal(decks,await repo.GetDecksAsync(player,Ct));
        Assert.Equal("season-shop-config-9",await db.ScalarAsync<string>("SELECT enabled_by_config FROM player_card_copy_modes WHERE player_id=$1",player));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM player_card_reserves WHERE player_id=$1",player));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1",player));
    }

    [Theory(Skip=RequiresDatabase,SkipUnless=nameof(HasTestDatabase))]
    [InlineData("C01")]
    [InlineData("MAG-01")]
    [InlineData("PRI-10")]
    [InlineData("GUA-09")]
    [Trait("Category","PostgresIntegration")]
    public async Task Every_soul_pool_consumes_exactly_one_extra_copy_at_four_and_five_and_replays_once(string cardId)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var player=await CreatePlayer(db);await Enable(db,player);
        var repo=new ProgressionRepository(db.DataSource);var card=await Card(repo,player,cardId);
        if(!card.Unlocked)card=(await repo.MutateCardAsync(player,cardId,"unlock",new(card.Version),true,Ct)).Card;
        for(var level=1;level<=3;level++)
        {
            Assert.Equal(0,card.UpgradeCopyCost);
            var up=await repo.UpgradeCardAsync(player,cardId,"up-"+level,new(card.Version),Ct);
            Assert.Equal(0,up.ConsumedCopies);Assert.Equal(1,up.Card.CopyCount);card=up.Card;
        }
        var before=await db.ScalarAsync<string>("SELECT row_to_json(m)::text FROM player_materials m WHERE player_id=$1",player);
        Assert.Equal(1,card.UpgradeCopyCost);Assert.False(card.CanUpgrade);
        await Assert.ThrowsAsync<DomainValidationException>(()=>repo.UpgradeCardAsync(player,cardId,"missing-copy",new(card.Version),Ct));
        Assert.Equal(before,await db.ScalarAsync<string>("SELECT row_to_json(m)::text FROM player_materials m WHERE player_id=$1",player));
        for(var level=4;level<=5;level++)
        {
            var copy=await repo.MutateCardAsync(player,cardId,"copy-"+level,new(card.Version),true,Ct);
            Assert.Equal(GameConfigCatalog.Current.Cards.Single(c=>c.CardId==cardId).CopyCost,copy.SoulAmount);
            Assert.Equal(2,copy.Card.CopyCount);Assert.True(copy.Card.CanUpgrade);
            var request=new CardMutationRequest(copy.Card.Version);
            var up=await repo.UpgradeCardAsync(player,cardId,"up-"+level,request,Ct);
            Assert.Equal(1,up.ConsumedCopies);Assert.Equal(1,up.Card.CopyCount);Assert.Equal(level,up.Card.Level);
            Assert.Equal(up,await new ProgressionRepository(db.DataSource).UpgradeCardAsync(player,cardId,"up-"+level,request,Ct));
            card=up.Card;
        }
        Assert.False(card.CanUpgrade);Assert.Equal(0,card.UpgradeCopyCost);
        Assert.Equal(1,await db.ScalarAsync<int>("SELECT copy_count FROM player_cards WHERE player_id=$1 AND card_id=$2",player,cardId));
        Assert.Equal(0,await db.ScalarAsync<int>("SELECT extra_count FROM player_card_reserves WHERE player_id=$1 AND card_id=$2",player,cardId));
        Assert.Equal(-2L,await db.ScalarAsync<long>("SELECT sum(delta)::bigint FROM card_copy_ledger WHERE player_id=$1 AND reason='card.upgrade'",player));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip=RequiresDatabase,SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task Dismantling_an_extra_does_not_refund_the_trained_base_or_remove_a_saved_deck_card()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var player=await CreatePlayer(db);await Enable(db,player);
        var repo=new ProgressionRepository(db.DataSource);var id=(await repo.GetDecksAsync(player,Ct))[0].CardIds[0];
        var card=await Card(repo,player,id);card=(await repo.UpgradeCardAsync(player,id,"train-base",new(card.Version),Ct)).Card;
        Assert.False(card.CanDismantle);
        card=(await repo.MutateCardAsync(player,id,"extra",new(card.Version),true,Ct)).Card;
        Assert.True(card.CanDismantle);Assert.Equal(GameConfigCatalog.Current.Cards.Single(c=>c.CardId==id).CopyCost/4,card.DismantleRefund);
        var removed=await repo.MutateCardAsync(player,id,"remove-extra",new(card.Version),false,Ct);
        Assert.Equal(1,removed.Card.CopyCount);Assert.Equal(1,removed.Card.Level);Assert.True(removed.Card.Unlocked);
        Assert.False(removed.Card.CanDismantle);Assert.True(removed.Card.UpgradeSoulSpent>0);
        await Assert.ThrowsAsync<DomainValidationException>(()=>repo.MutateCardAsync(player,id,"last-base",new(removed.Card.Version),false,Ct));
        var deck=(await repo.GetDecksAsync(player,Ct))[0];
        var ids=deck.CardIds.ToArray();ids[1]=ids[0];
        await Assert.ThrowsAsync<DomainValidationException>(()=>repo.SaveDeckAsync(player,(HeroClass)(short)deck.HeroClass,ids,"duplicate-deck",deck.Version,DateTimeOffset.UtcNow,Ct));
    }

    [Fact(Skip=RequiresDatabase,SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task Repeated_pack_draws_count_copies_and_only_the_first_unowned_copy_unlocks_the_card()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var player=await CreatePlayer(db);await Enable(db,player);
        var repo=new ProgressionRepository(db.DataSource);var cards=await repo.GetCardsAsync(player,Ct);
        var owned=cards.First(c=>c.Unlocked);var unowned=cards.First(c=>!c.Unlocked&&c.HeroClass is null);
        var first=await Grant(db,player,owned.CardId,3,"owned-pack");
        var second=await Grant(db,player,unowned.CardId,3,"new-pack");
        Assert.False(first.NewlyUnlocked);Assert.Equal(4,first.CopiesAfter);
        Assert.True(second.NewlyUnlocked);Assert.Equal(3,second.CopiesAfter);
        Assert.Equal(owned.Version+1,first.Version);Assert.Equal(unowned.Version+1,second.Version);
        Assert.Equal(4,(await Card(repo,player,owned.CardId)).CopyCount);
        Assert.Equal(3,(await Card(repo,player,unowned.CardId)).CopyCount);
        Assert.Equal(2L,await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1",player));
        Assert.Equal(6L,await db.ScalarAsync<long>("SELECT sum(delta)::bigint FROM card_copy_ledger WHERE player_id=$1",player));
    }

    [Fact(Skip=RequiresDatabase,SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task Concurrent_same_key_is_one_copy_and_distinct_stale_keys_cannot_both_spend()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var player=await CreatePlayer(db);await Enable(db,player);
        var repo=new ProgressionRepository(db.DataSource);var card=(await repo.GetCardsAsync(player,Ct)).First(c=>c.Unlocked&&c.HeroClass is null);
        var request=new CardMutationRequest(card.Version);
        var results=await Task.WhenAll(Enumerable.Range(0,4).Select(_=>repo.MutateCardAsync(player,card.CardId,"same-copy",request,true,Ct)));
        Assert.All(results,result=>Assert.Equal(results[0],result));Assert.Equal(2,results[0].Card.CopyCount);
        var version=results[0].Card.Version;
        async Task<bool> Attempt(string id)
        {
            try { await repo.MutateCardAsync(player,card.CardId,id,new(version),true,Ct);return true; }
            catch(DomainValidationException) { return false; }
        }
        Assert.Equal(1,(await Task.WhenAll(Attempt("race-a"),Attempt("race-b"))).Count(result=>result));
        Assert.Equal(3,(await Card(repo,player,card.CardId)).CopyCount);
        Assert.Equal(2L,await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1",player));
    }

    [Fact(Skip=RequiresDatabase,SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task Copy_ledger_failure_rolls_back_the_soul_debit_base_version_and_reserve_together()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var player=await CreatePlayer(db);await Enable(db,player);
        var repo=new ProgressionRepository(db.DataSource);var card=(await repo.GetCardsAsync(player,Ct)).First(c=>c.Unlocked&&c.HeroClass is null);
        var soul=await db.ScalarAsync<long>("SELECT warrior_soul FROM player_materials WHERE player_id=$1",player);
        await Sql(db,"""
            CREATE FUNCTION fail_copy_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'isolated card ledger fault'; END $$;
            CREATE TRIGGER copy_fault BEFORE INSERT ON card_copy_ledger FOR EACH ROW EXECUTE FUNCTION fail_copy_receipt();
            """);
        var error=await Assert.ThrowsAsync<PostgresException>(()=>repo.MutateCardAsync(player,card.CardId,"fault",new(card.Version),true,Ct));
        Assert.Equal(PostgresErrorCodes.RaiseException,error.SqlState);
        Assert.Equal(card,await Card(repo,player,card.CardId));
        Assert.Equal(soul,await db.ScalarAsync<long>("SELECT warrior_soul FROM player_materials WHERE player_id=$1",player));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM player_card_reserves WHERE player_id=$1",player));
        await Sql(db,"DROP TRIGGER copy_fault ON card_copy_ledger;");
        Assert.Equal(2,(await repo.MutateCardAsync(player,card.CardId,"fault",new(card.Version),true,Ct)).Card.CopyCount);
    }

    [Fact(Skip=RequiresDatabase,SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task Database_rejects_orphan_reserves_and_unenabled_grants_without_rewriting_the_legacy_constraint()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var player=await CreatePlayer(db);
        await Assert.ThrowsAsync<DomainValidationException>(()=>Grant(db,player,"C01",1,"unenabled"));
        await Enable(db,player);await Grant(db,player,"C01",1,"extra");
        var error=await Assert.ThrowsAsync<PostgresException>(()=>Sql(db,"UPDATE player_cards SET unlocked=false,copy_count=0 WHERE player_id=$1 AND card_id='C01'",player));
        Assert.Equal(PostgresErrorCodes.CheckViolation,error.SqlState);
        error=await Assert.ThrowsAsync<PostgresException>(()=>Sql(db,"UPDATE player_cards SET copy_count=2 WHERE player_id=$1 AND card_id='C01'",player));
        Assert.Equal(PostgresErrorCodes.CheckViolation,error.SqlState);
        Assert.Equal(2,(await Card(new(db.DataSource),player,"C01")).CopyCount);
    }

    private static async Task<Guid> CreatePlayer(PostgresTestSchema db)
    {
        var now=DateTimeOffset.UtcNow;
        var profile=await new IdentityRepository(db.DataSource,new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString("N"),"Permanent card test",RandomNumberGenerator.GetBytes(32),now,now.AddHours(1),Ct);
        await Sql(db,"UPDATE player_materials SET warrior_soul=10000,priest_soul=10000,mage_soul=10000,guardian_soul=10000 WHERE player_id=$1",profile.UserId);
        return profile.UserId;
    }

    private static async Task<CardResponse> Card(ProgressionRepository repo,Guid player,string id)=>(await repo.GetCardsAsync(player,Ct)).Single(card=>card.CardId==id);

    private static async Task Enable(PostgresTestSchema db,Guid player,string config="season-shop-config-9")
    {
        await using var connection=await db.DataSource.OpenConnectionAsync(Ct);await using var transaction=await connection.BeginTransactionAsync(Ct);
        await Lock(connection,transaction,player);
        await PermanentCardCopies.EnableWithinTransactionAsync(connection,transaction,player,config,DateTimeOffset.UtcNow,Ct);
        await transaction.CommitAsync(Ct);
    }

    private static async Task<PermanentCardGrant> Grant(PostgresTestSchema db,Guid player,string id,int count,string request)
    {
        await using var connection=await db.DataSource.OpenConnectionAsync(Ct);await using var transaction=await connection.BeginTransactionAsync(Ct);
        await Lock(connection,transaction,player);
        var result=await PermanentCardCopies.GrantWithinTransactionAsync(connection,transaction,player,
            GameConfigCatalog.Current.Cards.Single(card=>card.CardId==id),count,"shop.purchase",request,DateTimeOffset.UtcNow,Ct);
        await transaction.CommitAsync(Ct);return result;
    }

    private static async Task Lock(NpgsqlConnection c,NpgsqlTransaction t,Guid player)
    {
        await using var command=new NpgsqlCommand("SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE",c,t);
        command.Parameters.AddWithValue(player);await command.ExecuteScalarAsync(Ct);
    }

    private static async Task Sql(PostgresTestSchema db,string sql,params object[] values)
    {
        await using var command=db.DataSource.CreateCommand(sql);
        foreach(var value in values)command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(Ct);
    }
}
