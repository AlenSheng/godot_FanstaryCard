using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using Npgsql;

namespace FantasyCard.Server.Settlement;

public sealed partial class SettlementRepository
{
    private static readonly JsonSerializerOptions BotRewardJson=new(JsonSerializerDefaults.Web)
    {
        Converters={new JsonStringEnumConverter()}
    };

    private async Task RequireBotVictoryProofAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,
        CommitRealm realm,string itemId,EquipmentRewardData equipment,CancellationToken ct)
    {
        var origin=equipment.SeasonOrigin!;
        var season=realm.Context.Season??throw new InvalidOperationException("Bot victory rewards require an original season.");
        var policy=_configurations.Resolve(realm.Context.ConfigVersion).SeasonBotRewards
            ??throw new InvalidOperationException("The original configuration has no bot victory reward policy.");
        policy.RequireOrigin(equipment,season);
        if(itemId!=policy.EquipmentId(realm.Context.RoomId,origin.BotRewardOwnerId!.Value).ToString("D"))
            throw new InvalidOperationException("Bot victory reward item identity differs from its original human/match.");
        await using(var actors=new NpgsqlCommand("""
            SELECT count(*) FROM match_players WHERE match_id=$1 AND
                ((player_id=$2 AND NOT is_bot) OR (player_id=$3 AND is_bot))
            """,connection,transaction))
        {
            actors.Parameters.AddWithValue(realm.Context.MatchId);actors.Parameters.AddWithValue(origin.BotRewardOwnerId.Value);
            actors.Parameters.AddWithValue(origin.DefeatedBotId!.Value);
            if(await actors.ExecuteScalarAsync(ct) is not long count || count!=2)
                throw new InvalidOperationException("Bot victory source must identify an original human and bot participant.");
        }
        await using var saved=new NpgsqlCommand("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1",connection,transaction);
        saved.Parameters.AddWithValue(realm.Context.RoomId);
        var json=await saved.ExecuteScalarAsync(ct) as string
            ??throw new InvalidOperationException("Bot victory reward requires its durable room receipt.");
        var snapshot=JsonSerializer.Deserialize<BattleRoomSnapshot>(json,BotRewardJson)
            ??throw new InvalidOperationException("Bot victory room receipt is invalid.");
        var owner=snapshot.Players.SingleOrDefault(player=>player.PlayerId==origin.BotRewardOwnerId);
        var receipt=owner?.BotVictoryReward;
        if(snapshot.RoomId!=realm.Context.RoomId || snapshot.Season!=season || snapshot.ConfigVersion!=realm.Context.ConfigVersion ||
            owner is null || owner.IsBot || receipt is null || receipt.BotId!=origin.DefeatedBotId ||
            receipt.Equipment is not { } issued || issued.ItemId!=itemId || issued.IsCombatProjection || issued.IsGenerated!=true ||
            issued.Equipment!=equipment || !snapshot.Players.Any(player=>player.PlayerId==receipt.BotId && player.IsBot && player.Phase==RoomPlayerPhase.Dead))
            throw new InvalidOperationException("Bot victory reward differs from the durable once-only outcome.");
    }
}
