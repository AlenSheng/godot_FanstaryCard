namespace FantasyCard.Server.Players;

public sealed class PlayerNameConflictException(string message, Exception? innerException = null)
    : Exception(message, innerException)
{
    internal const string UniqueIndexName = "ux_players_display_name_key";
}
