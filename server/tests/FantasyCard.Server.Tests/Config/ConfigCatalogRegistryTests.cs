using System.Collections.Concurrent;
using FantasyCard.ConfigExporter;
using FantasyCard.Domain.Configuration;

namespace FantasyCard.Server.Tests.Config;

public sealed class ConfigCatalogRegistryTests
{
    [Fact]
    public void ExistingEmbeddedBundlePassesIntegrityValidation()
    {
        Assert.Equal(64,GameConfigCatalog.Current.ContentHash.Length);
        var data=File.ReadAllBytes(Path.Combine(FindRoot(),"server/config/generated/fantasycard.config.bytes"));
        var catalog=GameConfigCatalog.Load(data);
        Assert.Equal(GameConfigCatalog.Current.Version,catalog.Version);
        Assert.Equal(GameConfigCatalog.Current.ContentHash,catalog.ContentHash);
        Assert.Equal(GameConfigCatalog.Current.Cards,catalog.Cards);
    }

    [Fact]
    public void DistinctPublishedVersionsRetainTheirOwnCardAndGrowthData()
    {
        var (oldBytes,oldHash)=Bundle("archive-old",8,1);
        var (newBytes,newHash)=Bundle("archive-new",17,4);
        var registry=new ConfigCatalogRegistry(GameConfigCatalog.Current);
        var old=registry.Register("archive-old",oldHash,oldBytes);
        var current=registry.Register("archive-new",newHash,newBytes);
        Assert.Same(old,registry.Resolve("archive-old"));
        Assert.Same(current,registry.Resolve("archive-new"));
        Assert.Equal(8,old.Cards.Single(c=>c.CardId=="C01").Effect.ElementalDamage);
        Assert.Equal(17,current.Cards.Single(c=>c.CardId=="C01").Effect.ElementalDamage);
        Assert.Equal(1,old.CardLevels.Single(c=>c.CardId=="C01" && c.Level==1).ValueBonus);
        Assert.Equal(4,current.CardLevels.Single(c=>c.CardId=="C01" && c.Level==1).ValueBonus);
        Assert.Throws<InvalidDataException>(()=>registry.Resolve("missing-old-version"));
    }

    [Fact]
    public void SameVersionCannotBeReplacedAndOriginalRemainsReadable()
    {
        var (bytes,hash)=Bundle("immutable-version",8,1);
        var (other,otherHash)=Bundle("immutable-version",17,4);
        var registry=new ConfigCatalogRegistry(GameConfigCatalog.Current);
        var original=registry.Register("immutable-version",hash,bytes);
        Assert.Throws<InvalidDataException>(()=>registry.Register("immutable-version",otherHash,other));
        Assert.Same(original,registry.Resolve("immutable-version"));
        Assert.Equal(8,original.Cards.Single(c=>c.CardId=="C01").Effect.ElementalDamage);
    }

    [Fact]
    public void IncorrectPublishedIdentityDoesNotRegisterAnyVersion()
    {
        var (bytes,hash)=Bundle("identity-test",8,1);
        var registry=new ConfigCatalogRegistry(GameConfigCatalog.Current);
        Assert.Throws<InvalidDataException>(()=>registry.Register("other-version",hash,bytes));
        Assert.Throws<InvalidDataException>(()=>registry.Register("identity-test",new string('0',64),bytes));
        Assert.Throws<InvalidDataException>(()=>registry.Resolve("identity-test"));
        Assert.Throws<InvalidDataException>(()=>registry.Resolve("other-version"));
    }

    [Fact]
    public void ConcurrentIdenticalRegistrationRetainsOneCatalog()
    {
        var (bytes,hash)=Bundle("concurrent-config",8,1);
        var registry=new ConfigCatalogRegistry(GameConfigCatalog.Current);
        var values=new ConcurrentBag<GameConfigCatalog>();
        Parallel.For(0,8,_=>values.Add(registry.Register("concurrent-config",hash,bytes)));
        Assert.Equal(8,values.Count);
        Assert.All(values,value=>Assert.Same(registry.Resolve("concurrent-config"),value));
    }

    [Fact]
    public void TamperedTruncatedMissingAndRepeatedHashesAreRejected()
    {
        var (bytes,hash)=Bundle("integrity-test",8,1);
        var tampered=bytes.ToArray();tampered[^1]^=1;
        Assert.Throws<InvalidDataException>(()=>GameConfigCatalog.Load(tampered));
        Assert.Throws<InvalidDataException>(()=>GameConfigCatalog.Load(bytes.AsSpan(0,bytes.Length-1)));
        Assert.Throws<InvalidDataException>(()=>GameConfigCatalog.Load([]));
        byte[] repeated=[..bytes,0x12,0x20,..Convert.FromHexString(hash)];
        Assert.Throws<InvalidDataException>(()=>GameConfigCatalog.Load(repeated));
    }

    private static (byte[] Bytes,string Hash) Bundle(string version,long damage,long bonus)
    {
        var tables=XlsxConfigReader.Read(Path.Combine(FindRoot(),"config/FantasyCard_Config.xlsx"));
        tables=Set(tables,"Cards","id","C01","elemental_damage",damage);
        tables=Set(tables,"CardLevels","id","C01:1","value_bonus",bonus);
        var bytes=ConfigCompiler.Compile(version,tables,out var hash);
        return (bytes,hash);
    }

    private static FantasyCard.ConfigExporter.ConfigTable[] Set(IReadOnlyList<FantasyCard.ConfigExporter.ConfigTable> tables,string name,string key,string id,string field,long value)
    {
        var table=tables.Single(t=>t.Name==name);
        var keyIndex=table.Columns.Select((c,i)=>(c,i)).Single(x=>x.c.Name==key).i;
        var fieldIndex=table.Columns.Select((c,i)=>(c,i)).Single(x=>x.c.Name==field).i;
        var rows=table.Rows.Select(row=>
        {
            if ((string)row[keyIndex].Value! != id) return row;
            var changed=row.ToArray();changed[fieldIndex]=new(ConfigValueType.WholeNumber,value);return changed;
        }).ToArray();
        Assert.Contains(rows,row=>(string)row[keyIndex].Value! == id && Equals(row[fieldIndex].Value,value));
        return tables.Select(t=>t==table?t with {Rows=rows}:t).ToArray();
    }

    private static string FindRoot()
    {
        var directory=new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName,"config/FantasyCard_Config.xlsx"))) return directory.FullName;
            directory=directory.Parent;
        }
        throw new DirectoryNotFoundException("Pinned formal workbook is required.");
    }
}
