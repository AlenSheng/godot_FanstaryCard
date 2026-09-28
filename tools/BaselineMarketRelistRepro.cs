using FantasyCard.Server.Tests.Persistence;
using FantasyCard.Server.Progression;
using Npgsql;
namespace FantasyCard.Server.Tests.EndToEnd;
public sealed partial class RealNetworkEndToEndTests
{
 [Fact]
 public async Task Baseline_market_relisting_hits_existing_unique_constraint()
 {
  await using var database = await PostgresTestSchema.CreateAsync(migrate:true);
  var ct = TestContext.Current.CancellationToken;
  var seller = await SeedNetworkPlayerAsync(database,"Relist Seller",ct);
  var buyer = await SeedNetworkPlayerAsync(database,"Relist Buyer",ct);
  await database.ExecuteAsync("UPDATE player_wallets SET gold=100000");
  var equipment=Guid.NewGuid();
  await using(var seed=database.DataSource.CreateCommand("INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at) VALUES($1,$2,'Chest','Blue',0,false,'Inventory',1,now())"))
  { seed.Parameters.AddWithValue(equipment); seed.Parameters.AddWithValue(seller.Id); await seed.ExecuteNonQueryAsync(ct); }
  var economy=new EconomyRepository(database.DataSource,TimeProvider.System);
  var listing=await economy.ListAsync(seller.Id,"baseline-listing",new(equipment,100),ct);
  await economy.PurchaseMarketAsync(buyer.Id,"baseline-purchase",listing.ListingId,listing.Version,ct);
  var error=await Assert.ThrowsAsync<PostgresException>(()=>economy.ListAsync(buyer.Id,"baseline-relisting",new(equipment,101),ct));
  Assert.Equal("23505",error.SqlState);
  Assert.Equal("market_listings_equipment_id_key",error.ConstraintName);
  Console.WriteLine("BASELINE REPRO CONFIRMED: purchased equipment relisting violates market_listings_equipment_id_key, SQLSTATE 23505");
 }
}
