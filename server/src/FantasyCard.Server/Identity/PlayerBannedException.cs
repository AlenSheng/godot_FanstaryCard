namespace FantasyCard.Server.Identity;

public sealed class PlayerBannedException : Exception
{
    public PlayerBannedException() : base("This account is banned.") { }
}
