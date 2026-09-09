namespace FantasyCard.Domain.Players;

public sealed class DomainValidationException(string message) : Exception(message);
