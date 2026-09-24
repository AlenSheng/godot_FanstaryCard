using System.Security.Cryptography;
using System.Text;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed class PlayerProvisioningService
{
    public async Task<bool> IsProvisionedAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        CancellationToken cancellationToken)
    {
        var classCount = Enum.GetValues<HeroClass>().Length;
        var cardCount = GameConfigCatalog.Current.Cards.Count(card => card.IsCodex);
        await using var command = new NpgsqlCommand(
            """
            SELECT
                (SELECT count(*) FROM player_cards WHERE player_id=$1) >= $2
                AND (SELECT count(*) FROM player_decks WHERE player_id=$1) = $3
                AND (SELECT count(*) FROM player_deck_cards dc
                     JOIN player_decks d ON d.deck_id=dc.deck_id WHERE d.player_id=$1) = $4
                AND (SELECT count(*) FROM class_weapons WHERE player_id=$1) = $3
                AND (SELECT count(*) FROM player_loadouts WHERE player_id=$1) = $3
                AND EXISTS (SELECT 1 FROM player_wallets WHERE player_id=$1)
                AND EXISTS (SELECT 1 FROM player_materials WHERE player_id=$1)
                AND EXISTS (SELECT 1 FROM player_consumables WHERE player_id=$1)
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(cardCount);
        command.Parameters.AddWithValue(classCount);
        command.Parameters.AddWithValue(classCount * 20);
        return (bool)(await command.ExecuteScalarAsync(cancellationToken) ?? false);
    }

    public async Task ProvisionAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        string displayName,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        await InsertAccountsAsync(connection, transaction, playerId, cancellationToken);
        if (Environment.GetEnvironmentVariable("ASPNETCORE_ENVIRONMENT") is "Development" or "DevelopmentLocal" &&
            displayName.StartsWith("test_", StringComparison.OrdinalIgnoreCase))
            await InsertDevelopmentTestMailAsync(connection, transaction, playerId, now, cancellationToken);
        await InsertStarterCardsAsync(connection, transaction, playerId, cancellationToken);

        foreach (var heroClass in Enum.GetValues<HeroClass>())
        {
            await InsertClassWeaponAsync(connection, transaction, playerId, heroClass, cancellationToken);
            await InsertDefaultDeckAsync(connection, transaction, playerId, heroClass, now, cancellationToken);
            await InsertDefaultLoadoutAsync(connection, transaction, playerId, heroClass, cancellationToken);
        }
    }

    private static async Task InsertDevelopmentTestMailAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, Guid playerId, DateTimeOffset now, CancellationToken cancellationToken)
    {
        await using var mail = new NpgsqlCommand("INSERT INTO player_mail(mail_id,player_id,title,body,attachments,created_at) VALUES ($1,$2,'开发测试资源','测试账号资源已通过邮件发放，请领取附件。',$3::jsonb,$4) ON CONFLICT (mail_id) DO NOTHING", connection, transaction);
        mail.Parameters.AddWithValue(CreateStableGuid(playerId, "dev-mail")); mail.Parameters.AddWithValue(playerId); mail.Parameters.AddWithValue("{\"gold\":100000,\"diamond\":100000,\"warriorSoul\":100000,\"priestSoul\":100000,\"mageSoul\":100000,\"guardianSoul\":100000,\"equipmentFragments\":100000,\"equipmentQualities\":[\"White\",\"Green\",\"Blue\",\"Purple\",\"Orange\",\"Red\"]}"); mail.Parameters.AddWithValue(now); await mail.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task InsertAccountsAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        CancellationToken cancellationToken)
    {
        // 命令携带参数时 Npgsql 走 prepared statement，PostgreSQL 拒绝多语句（42601），逐条执行
        foreach (var table in new[] { "player_wallets", "player_materials", "player_consumables" })
        {
            await using var command = new NpgsqlCommand(
                $"INSERT INTO {table}(player_id) VALUES ($1) ON CONFLICT DO NOTHING",
                connection,
                transaction);
            command.Parameters.AddWithValue(playerId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
    }

    private static async Task InsertStarterCardsAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        CancellationToken cancellationToken)
    {
        foreach (var card in GameConfigCatalog.Current.Cards.Where(card => card.IsCodex))
        {
            await using var command = new NpgsqlCommand(
                """
                INSERT INTO player_cards(player_id, card_id, hero_class, rarity, is_monster, unlocked, copy_count, level, version)
                VALUES ($1, $2, $3, $4, false, $5, $6, 0, 1)
                ON CONFLICT (player_id, card_id) DO NOTHING
                """,
                connection,
                transaction);
            command.Parameters.AddWithValue(playerId);
            command.Parameters.AddWithValue(card.CardId);
            command.Parameters.Add(new NpgsqlParameter
            {
                NpgsqlDbType = NpgsqlDbType.Smallint,
                Value = card.HeroClass is null ? DBNull.Value : (short)card.HeroClass.Value
            });
            command.Parameters.AddWithValue(card.Rarity);
            command.Parameters.AddWithValue(card.InitiallyUnlocked);
            command.Parameters.AddWithValue(card.InitiallyUnlocked ? 1 : 0);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
    }

    private static async Task InsertClassWeaponAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        HeroClass heroClass,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            """
            INSERT INTO class_weapons(player_id, hero_class, level, version)
            VALUES ($1, $2, 0, 1)
            ON CONFLICT (player_id, hero_class) DO NOTHING
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue((short)heroClass);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task InsertDefaultDeckAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        HeroClass heroClass,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        var deckId = CreateStableGuid(playerId, $"deck:{heroClass}");
        await using (var deckCommand = new NpgsqlCommand(
            """
            INSERT INTO player_decks(deck_id, player_id, hero_class, version, updated_at)
            VALUES ($1, $2, $3, 1, $4)
            ON CONFLICT (player_id, hero_class) DO NOTHING
            """,
            connection,
            transaction))
        {
            deckCommand.Parameters.AddWithValue(deckId);
            deckCommand.Parameters.AddWithValue(playerId);
            deckCommand.Parameters.AddWithValue((short)heroClass);
            deckCommand.Parameters.AddWithValue(now);
            await deckCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        var classPrefix = heroClass switch
        {
            HeroClass.Priest => "PRI",
            HeroClass.Mage => "MAG",
            HeroClass.Guardian => "GUA",
            _ => throw new ArgumentOutOfRangeException(nameof(heroClass))
        };
        var defaultCardIds = Enumerable.Range(1, 13)
            .Select(index => $"C{index:D2}")
            .Concat(Enumerable.Range(1, 7).Select(index => $"{classPrefix}-{index:D2}"))
            .ToArray();
        for (var index = 0; index < defaultCardIds.Length; index++)
        {
            await using var cardCommand = new NpgsqlCommand(
                """
                INSERT INTO player_deck_cards(deck_id, slot_index, card_id)
                SELECT deck_id, $3, $4
                FROM player_decks
                WHERE player_id = $1 AND hero_class = $2
                ON CONFLICT (deck_id, slot_index) DO NOTHING
                """,
                connection,
                transaction);
            cardCommand.Parameters.AddWithValue(playerId);
            cardCommand.Parameters.AddWithValue((short)heroClass);
            cardCommand.Parameters.AddWithValue(index);
            cardCommand.Parameters.AddWithValue(defaultCardIds[index]);
            await cardCommand.ExecuteNonQueryAsync(cancellationToken);
        }
    }

    private static async Task InsertDefaultLoadoutAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        HeroClass heroClass,
        CancellationToken cancellationToken)
    {
        await using var loadoutCommand = new NpgsqlCommand(
            """
            INSERT INTO player_loadouts(player_id, hero_class, head_id, chest_id, hands_id, legs_id, feet_id, version)
            VALUES ($1, $2, NULL, NULL, NULL, NULL, NULL, 1)
            ON CONFLICT (player_id, hero_class) DO NOTHING
            """,
            connection,
            transaction);
        loadoutCommand.Parameters.AddWithValue(playerId);
        loadoutCommand.Parameters.AddWithValue((short)heroClass);
        await loadoutCommand.ExecuteNonQueryAsync(cancellationToken);
    }

    private static Guid CreateStableGuid(Guid playerId, string discriminator)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes($"{playerId:N}:{discriminator}"));
        Span<byte> guidBytes = stackalloc byte[16];
        bytes.AsSpan(0, 16).CopyTo(guidBytes);
        guidBytes[7] = (byte)((guidBytes[7] & 0x0F) | 0x50);
        guidBytes[8] = (byte)((guidBytes[8] & 0x3F) | 0x80);
        return new Guid(guidBytes);
    }
}
