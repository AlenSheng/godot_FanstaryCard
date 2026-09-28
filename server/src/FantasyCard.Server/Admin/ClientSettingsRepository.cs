using Npgsql;

namespace FantasyCard.Server.Admin;

public sealed record ClientSettings(bool LocalLoginEnabled, string AnnouncementTitle,
    string AnnouncementBody, long Version, DateTimeOffset UpdatedAt,
    string AnnouncementTitleEn = "", string AnnouncementBodyEn = "");

public sealed record UpdateClientSettingsRequest(bool LocalLoginEnabled, string AnnouncementTitle,
    string AnnouncementBody, long ExpectedVersion,
    string? AnnouncementTitleEn = null, string? AnnouncementBodyEn = null);

public sealed class ClientSettingsRepository(NpgsqlDataSource dataSource)
{
    public async Task<ClientSettings> GetAsync(CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT local_login_enabled,announcement_title,announcement_body,version,updated_at,announcement_title_en,announcement_body_en FROM client_settings WHERE id=1");
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
            throw new InvalidOperationException("Client settings are missing.");
        return Read(reader);
    }

    public async Task<ClientSettings?> UpdateAsync(UpdateClientSettingsRequest request, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            UPDATE client_settings
            SET local_login_enabled=$1,announcement_title=$2,announcement_body=$3,
                announcement_title_en=COALESCE($5,announcement_title_en),
                announcement_body_en=COALESCE($6,announcement_body_en),
                version=version+1,updated_at=now()
            WHERE id=1 AND version=$4
            RETURNING local_login_enabled,announcement_title,announcement_body,version,updated_at,announcement_title_en,announcement_body_en
            """);
        command.Parameters.AddWithValue(request.LocalLoginEnabled);
        command.Parameters.AddWithValue(request.AnnouncementTitle.Trim());
        command.Parameters.AddWithValue(request.AnnouncementBody.Trim());
        command.Parameters.AddWithValue(request.ExpectedVersion);
        command.Parameters.Add(new NpgsqlParameter
        {
            NpgsqlDbType = NpgsqlTypes.NpgsqlDbType.Varchar,
            Value = request.AnnouncementTitleEn is null ? DBNull.Value : request.AnnouncementTitleEn.Trim()
        });
        command.Parameters.Add(new NpgsqlParameter
        {
            NpgsqlDbType = NpgsqlTypes.NpgsqlDbType.Varchar,
            Value = request.AnnouncementBodyEn is null ? DBNull.Value : request.AnnouncementBodyEn.Trim()
        });
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken) ? Read(reader) : null;
    }

    private static ClientSettings Read(NpgsqlDataReader reader) =>
        new(reader.GetBoolean(0), reader.GetString(1), reader.GetString(2),
            reader.GetInt64(3), reader.GetFieldValue<DateTimeOffset>(4), reader.GetString(5), reader.GetString(6));
}
