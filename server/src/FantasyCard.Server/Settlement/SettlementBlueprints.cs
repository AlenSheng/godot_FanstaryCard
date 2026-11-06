using System.Security.Cryptography;
using System.Text;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Seasons;
using Npgsql;

namespace FantasyCard.Server.Settlement;

public sealed partial class SettlementRepository
{
    internal GameConfigCatalog ConfigurationFor(string version) => _configurations.Resolve(version);

    private static bool IsBlueprintAsset(SettlementAsset asset) => asset.AssetKind is "BlueprintMarks" or "OrangeBlueprintMarks";

    private async Task ValidateBlueprintAssetsAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
        SettlementContext context, Guid playerId, string result, IReadOnlyList<SettlementAsset> assets, CancellationToken ct)
    {
        var marks = assets.Where(IsBlueprintAsset).ToArray();
        if (marks.Length == 0) return;
        if (marks.Length != 1 || context.Season is null || result != "Extracted")
            throw new InvalidOperationException("Blueprints require one original source and a successful extraction.");
        var policy = _configurations.Resolve(context.ConfigVersion).SeasonCrafting
            ?? throw new InvalidOperationException("This original configuration has no blueprint source policy.");
        var rule = policy.Marks(context.Season.Difficulty);
        var expected = rule.Kind == BlueprintKind.Blueprint ? "BlueprintMarks" : "OrangeBlueprintMarks";
        if (rule.Kind == BlueprintKind.None || marks[0].AssetKind != expected || marks[0].IsSafe ||
            marks[0].Quantity <= 0 || marks[0].Quantity > rule.MatchCap ||
            marks[0].AssetId != (rule.Kind == BlueprintKind.Blueprint ? "blueprint" : "orange-blueprint"))
            throw new InvalidOperationException("Blueprints differ from their original difficulty's source or cap.");
        await using var actor = new NpgsqlCommand("SELECT is_bot FROM match_players WHERE match_id=$1 AND player_id=$2", connection, transaction);
        actor.Parameters.AddWithValue(context.MatchId); actor.Parameters.AddWithValue(playerId);
        if (await actor.ExecuteScalarAsync(ct) is not false)
            throw new InvalidOperationException("Only a real player's own PVE clears can award blueprints.");
    }

    private async Task CreditBlueprintAssetAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
        SettlementHoldRecord hold, CommitRealm realm, SettlementAsset asset, CancellationToken ct)
    {
        string result;
        await using (var settlement = new NpgsqlCommand("SELECT result FROM match_settlements WHERE settlement_id=$1", connection, transaction))
        {
            settlement.Parameters.AddWithValue(hold.SettlementId);
            result = (string)(await settlement.ExecuteScalarAsync(ct))!;
        }
        await ValidateBlueprintAssetsAsync(connection, transaction, realm.Context, hold.PlayerId, result, [asset], ct);
        var business = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(
            hold.SettlementId.ToString("D") + ":" + hold.HoldId.ToString("D") + ":" + hold.AssetSnapshot)));
        await SeasonRepository.ApplyWithinTransactionAsync(connection, transaction, hold.PlayerId, realm.Context.Season!,
            0, 0, 0, "settlement.blueprints", hold.HoldId.ToString("D"), SeasonWalletPurpose.LateSettlement,
            realm.Now, business, ct, asset.AssetKind == "BlueprintMarks" ? asset.Quantity : 0,
            asset.AssetKind == "OrangeBlueprintMarks" ? asset.Quantity : 0);
    }
}
