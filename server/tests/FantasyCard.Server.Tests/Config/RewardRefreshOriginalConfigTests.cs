using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.ConfigExporter;

namespace FantasyCard.Server.Tests.Config;

public sealed class RewardRefreshOriginalConfigTests
{
    [Theory]
    [InlineData(0,7)] [InlineData(3,4)] [InlineData(7,0)] [InlineData(10,0)]
    public void QuoteAndRefreshUseTheSameOriginalCatalogAfterRestore(int temporaryGold,long accountGold)
    {
        var original=CreateConfig("refresh-original").Catalog;
        var lobby=CreateConfig("refresh-lobby",alternate:true).Catalog;
        Assert.Equal(11,lobby.RewardRefreshGold(1));
        var player=Guid.NewGuid();var room=ChoiceRoom(original,player,temporaryGold);
        var revision=room.Revision;var before=room.Capture();
        Assert.Equal(new RewardRefreshFundingQuote(7,accountGold),room.GetRewardRefreshFundingQuote(player));
        Assert.Equivalent(before,room.Capture(),strict:true);
        room=BattleRoom.Restore(room.Capture(),CombatCardCatalog.Create(original),73);
        var receipt=room.RefreshRewardChoice(player,revision,accountGold,"original-refresh");
        Assert.Equal(Math.Max(0,temporaryGold-7),room.GetPlayer(player).Inventory.GoldQuantity);
        Assert.Equal(1,receipt.Choice.RefreshCount);
        Assert.Equal(original.Version,receipt.Choice.SeasonLoot!.Season.ConfigVersion);
    }

    [Fact]
    public void QuoteRejectsTheFourthRefreshAndNonChoiceWithoutChangingAnything()
    {
        var config=CreateConfig("refresh-limit").Catalog;
        var player=Guid.NewGuid();var room=ChoiceRoom(config,player,0);
        for(var index=0;index<3;index++)room.RefreshRewardChoice(player,room.Revision,7,"refresh-"+index);
        var before=room.Capture();
        Assert.Throws<DomainValidationException>(()=>room.GetRewardRefreshFundingQuote(player));
        Assert.Equivalent(before,room.Capture(),strict:true);
        room.ClaimReward(player,room.GetRewardChoice(player).Options.Single(o=>o.Kind==RewardChoiceKind.ImmediateHeal).OptionId);
        before=room.Capture();
        Assert.Throws<DomainValidationException>(()=>room.GetRewardRefreshFundingQuote(player));
        Assert.Equivalent(before,room.Capture(),strict:true);
    }

    internal static BattleRoom ChoiceRoom(GameConfigCatalog config,Guid player,int temporaryGold=0,bool legacy=false)
    {
        // This is an explicit pending-choice checkpoint fixture, not a combat or capacity route.
        var room=PublishedConfigTestInputs.Room(config,player,withMap:true,legacy:legacy);
        var snapshot=room.Capture();
        var choice=RewardChoiceState.Create(ChaosMapLayer.Outer,new Random(73),configuration:config,
            season:room.Season is {} source?new SeasonRewardContext(source,SeasonRewardBias.None):null).Capture();
        room=BattleRoom.Restore(snapshot with {Players=snapshot.Players.Select(p=>p with
            {Phase=RoomPlayerPhase.Choice,Pve=null,RewardChoice=choice}).ToArray()},CombatCardCatalog.Create(config),73);
        if(temporaryGold>0)Assert.True(room.GetPlayer(player).Inventory.TryAdd(new("refresh-gold",ExplorationItemKind.Gold,temporaryGold)));
        return room;
    }

    internal static (GameConfigCatalog Catalog,byte[] Bytes) CreateConfig(string version,bool alternate=false)
    {
        // Keep the complete current original table set, including the coupled
        // theme/preference policy. Only distinct test prices and versioned stats change.
        var tables=XlsxConfigReader.Read(Path.Combine(PublishedConfigTestInputs.FindRoot(),"config/FantasyCard_Config.xlsx"));
        tables=tables.Select(table=>
        {
            var field=table.Name switch {"LootRules"=>"refresh_gold","SeasonEquipment" or "SeasonEquipmentRules"=>"stats_version",_=>null};
            if(field is null)return table;
            var column=table.Columns.Select((c,i)=>(c,i)).Single(p=>p.c.Name==field).i;
            return table with {Rows=table.Rows.Select(row=>
            {
                if(table.Name=="LootRules" && (row[0].Value is not string key || !key.StartsWith("refresh-",StringComparison.Ordinal)))return row;
                var changed=row.ToArray();changed[column]=new(changed[column].Type,table.Name=="LootRules"?(object)(alternate?11L:7L):"archive-control-stats");
                return changed;
            }).ToArray()};
        }).ToArray();
        var bytes=ConfigCompiler.Compile(version,tables,out _);return (GameConfigCatalog.Load(bytes),bytes);
    }
}
