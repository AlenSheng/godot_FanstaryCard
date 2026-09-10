using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class ProgressionRepository
{
    private static CardResponse EmptyCard(CardConfigDefinition definition) => new(
        definition.CardId, definition.HeroClass is { } heroClass ? (HeroClassDto)(short)heroClass : null,
        definition.Quality!, false, 0, 0, 0);

    private static CardResponse QuoteCard(CardConfigDefinition definition, CardResponse card, int requiredCopies)
    {
        var owned = card.Unlocked && card.CopyCount > 0;
        // The aggregate stores one trained card plus untrained duplicates; spend is returned once.
        var dismantleLevel = card.CopyCount == 1 ? card.Level : 0;
        var blockedReason = !owned ? "Card is not owned."
            : card.CopyCount <= requiredCopies ? "Card is required by a saved deck." : null;
        var upgrade = card.Level < 5 ? CardEconomyRules.Level(card.CardId, card.Level + 1) : null;
        var upgradeBlockedReason = CardEconomyRules.UpgradeBlockedReason(
            card.CardId, card.Unlocked, card.CopyCount, card.Level, requiredCopies);
        return card with
        {
            Rarity = definition.Quality!,
            CraftCost = CardEconomyRules.CraftCost(definition, owned),
            UpgradeSoulSpent = CardEconomyRules.UpgradeSoulSpent(card.CardId, dismantleLevel),
            DismantleRefund = owned ? CardEconomyRules.DismantleRefund(definition, dismantleLevel) : 0,
            CurrencyKind = CardEconomyRules.CurrencyKind(definition),
            CanDismantle = blockedReason is null,
            BlockedReason = blockedReason,
            UpgradeCost = upgrade?.SoulCost ?? 0,
            UpgradeCopyCost = upgrade?.RequiresCopy == true ? 1 : 0,
            CanUpgrade = upgradeBlockedReason is null,
            UpgradeBlockedReason = upgradeBlockedReason,
            CurrentEffect = CardEffect(CardEconomyRules.ApplyLevel(card.CardId, definition.Effect, card.Level)),
            NextEffect = upgrade is null ? null : CardEffect(CardEconomyRules.ApplyLevel(card.CardId, definition.Effect, card.Level + 1))
        };
    }

    private static CardEffectResponse CardEffect(CombatCardEffect effect) => new(
        effect.ElementalDamage, effect.Element.ToString(), effect.DirectDamage, effect.Heal, effect.Shield,
        effect.DrawCharge, effect.ImmediateDraw, effect.DrawSpeedModifier, effect.DrawSpeedSeconds,
        effect.StunSeconds, effect.DrawBlockSeconds, effect.HealthCost, effect.SameElementBonus,
        effect.ResonanceBonus, effect.ConflictCancelBonus, effect.ConflictHealCoefficient, effect.IsClassReveal,
        effect.SecondaryElementalDamage, effect.SecondaryElement.ToString());

    public Task<CardMutationResponse> MutateCardAsync(
        Guid playerId, string cardId, string requestId, CardMutationRequest request,
        bool craft, CancellationToken cancellationToken) =>
        MutateCardAsync(playerId, cardId, requestId, request, craft ? "craft" : "dismantle", cancellationToken);

    public Task<CardMutationResponse> UpgradeCardAsync(
        Guid playerId, string cardId, string requestId, CardMutationRequest request, CancellationToken cancellationToken) =>
        MutateCardAsync(playerId, cardId, requestId, request, "upgrade", cancellationToken);

    private async Task<CardMutationResponse> MutateCardAsync(
        Guid playerId, string cardId, string requestId, CardMutationRequest request,
        string operation, CancellationToken cancellationToken)
    {
        var craft = operation == "craft";
        var upgrade = operation == "upgrade";
        var scope = "card." + operation;
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        var requestHash = HashIdempotentRequest(cardId, request);
        var replay = await ReadIdempotentResultAsync<CardMutationResponse>(
            connection, transaction, playerId, scope, requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return replay;
        }

        var definition = CardEconomyRules.GetCard(cardId);
        var card = EmptyCard(definition);
        await using (var query = new NpgsqlCommand(
            "SELECT unlocked,copy_count,level,version FROM player_cards WHERE player_id=$1 AND card_id=$2 FOR UPDATE",
            connection, transaction))
        {
            query.Parameters.AddWithValue(playerId);
            query.Parameters.AddWithValue(cardId);
            await using var reader = await query.ExecuteReaderAsync(cancellationToken);
            if (await reader.ReadAsync(cancellationToken))
                card = card with
                {
                    Unlocked = reader.GetBoolean(0), CopyCount = reader.GetInt32(1),
                    Level = reader.GetInt32(2), Version = reader.GetInt64(3)
                };
        }
        if (card.Version != request.ExpectedVersion)
            throw new DomainValidationException("Card changed. Reload and retry with its latest version.");

        int requiredCopies;
        await using (var decks = new NpgsqlCommand(
            """
            SELECT COALESCE(max(copies),0)::integer FROM (
                SELECT count(*) AS copies FROM player_deck_cards dc
                JOIN player_decks d ON d.deck_id=dc.deck_id
                WHERE d.player_id=$1 AND dc.card_id=$2 GROUP BY d.deck_id) required
            """, connection, transaction))
        {
            decks.Parameters.AddWithValue(playerId);
            decks.Parameters.AddWithValue(cardId);
            requiredCopies = (int)(await decks.ExecuteScalarAsync(cancellationToken))!;
        }
        card = QuoteCard(definition, card, requiredCopies);
        if (upgrade && !card.CanUpgrade)
            throw new DomainValidationException(card.UpgradeBlockedReason!);
        if (!craft && !upgrade && !card.CanDismantle)
            throw new DomainValidationException(card.BlockedReason!);
        var amount = upgrade ? card.UpgradeCost : craft ? card.CraftCost : card.DismantleRefund;
        var delta = craft || upgrade ? -amount : amount;
        var currency = card.CurrencyKind;
        var column = currency switch
        {
            "WarriorSoul" => "warrior_soul", "PriestSoul" => "priest_soul",
            "MageSoul" => "mage_soul", "GuardianSoul" => "guardian_soul",
            _ => throw new DomainValidationException("Unknown soul material.")
        };
        MaterialsResponse materials;
        // Column names come exclusively from the fixed currency mapping above.
        await using (var wallet = new NpgsqlCommand(
            $"UPDATE player_materials SET {column}={column}+$1,version=version+1 WHERE player_id=$2 AND {column}+$1>=0 RETURNING warrior_soul,priest_soul,mage_soul,guardian_soul,equipment_fragments",
            connection, transaction))
        {
            wallet.Parameters.AddWithValue(delta);
            wallet.Parameters.AddWithValue(playerId);
            await using var reader = await wallet.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken))
                throw new DomainValidationException("Not enough " + currency + ".");
            materials = new(reader.GetInt64(0), reader.GetInt64(1), reader.GetInt64(2), reader.GetInt64(3), reader.GetInt64(4));
        }

        var consumedCopies = upgrade ? card.UpgradeCopyCost : 0;
        var copiesAfter = checked(card.CopyCount + (upgrade ? -consumedCopies : craft ? 1 : -1));
        card = card with
        {
            Unlocked = copiesAfter > 0, CopyCount = copiesAfter,
            Level = upgrade ? card.Level + 1 : copiesAfter == 0 ? 0 : card.Level, Version = card.Version + 1
        };
        await using (var save = new NpgsqlCommand(
            """
            INSERT INTO player_cards(player_id,card_id,hero_class,rarity,is_monster,unlocked,copy_count,level,version)
            VALUES($1,$2,$3,$4,false,$5,$6,$7,$8)
            ON CONFLICT(player_id,card_id) DO UPDATE SET unlocked=EXCLUDED.unlocked,
                copy_count=EXCLUDED.copy_count,level=EXCLUDED.level,version=EXCLUDED.version
            """, connection, transaction))
        {
            save.Parameters.AddWithValue(playerId);
            save.Parameters.AddWithValue(cardId);
            save.Parameters.Add(new NpgsqlParameter
            {
                NpgsqlDbType = NpgsqlDbType.Smallint,
                Value = definition.HeroClass is { } heroClass ? (short)heroClass : DBNull.Value
            });
            save.Parameters.AddWithValue(definition.Rarity);
            save.Parameters.AddWithValue(card.Unlocked);
            save.Parameters.AddWithValue(card.CopyCount);
            save.Parameters.AddWithValue(card.Level);
            save.Parameters.AddWithValue(card.Version);
            await save.ExecuteNonQueryAsync(cancellationToken);
        }
        var balance = currency switch
        {
            "WarriorSoul" => materials.WarriorSoul, "PriestSoul" => materials.PriestSoul,
            "MageSoul" => materials.MageSoul, _ => materials.GuardianSoul
        };
        await WriteEconomyLedgerAsync(connection, transaction, playerId, delta, balance,
            currency, scope, cancellationToken, requestId);
        var result = new CardMutationResponse(QuoteCard(definition, card, requiredCopies), materials, currency, amount, consumedCopies);
        await WriteIdempotentResultAsync(connection, transaction, playerId, scope, requestId,
            requestHash, result, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return result;
    }
}
