using System.Data;
using Npgsql;

namespace FantasyCard.Server.Telemetry;

public sealed record SeasonTelemetryDiagnosticsReport(DateTimeOffset FromUtc,DateTimeOffset ToUtc,DateTimeOffset ObservedAtUtc,DateTimeOffset RoomReadCompletedAtUtc,
    IReadOnlyList<DiagnosticSlice> Rows,IReadOnlyList<ChoiceDiagnosticGroup> Choices,ChoiceDiagnosticCoverage ChoiceCoverage,IReadOnlyList<string> TruncatedSources,
    IReadOnlyList<string> ScopeNotes,ChoiceSourceCoverage RoomCoverage);
public sealed record ChoiceSourceCoverage(int SourceRooms,int LegacyUnobservedRooms,int InvalidRooms,int UnknownTimestampEvents,string DroppedEvents,long OmittedItems,bool FullyObserved);

public sealed class SeasonTelemetryDiagnosticsRepository(NpgsqlDataSource dataSource,TimeProvider clock,RoomEventTelemetryRepository roomEvents)
{
    public async Task<SeasonTelemetryDiagnosticsReport> ReadAsync(DateTimeOffset from,DateTimeOffset to,CancellationToken cancellationToken)
    {
        EconomyTelemetryRepository.ValidateWindow(from,to);from=from.ToUniversalTime();to=to.ToUniversalTime();
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);deadline.CancelAfter(TimeSpan.FromSeconds(5));var ct=deadline.Token;
        var rooms=await roomEvents.ReadAsync(from,to,ct);var roomRead=clock.GetUtcNow();var choices=SeasonDiagnosticProjection.Choices(rooms);
        await using var connection=await dataSource.OpenConnectionAsync(ct);await using var transaction=await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        await using(var config=new NpgsqlCommand("SET TRANSACTION READ ONLY",connection,transaction))await config.ExecuteNonQueryAsync(ct);
        await using(var timeout=new NpgsqlCommand("SET LOCAL statement_timeout=5000",connection,transaction))await timeout.ExecuteNonQueryAsync(ct);
        var observed=clock.GetUtcNow();var rows=new List<DiagnosticSlice>();var truncated=new List<string>();
        foreach(var section in Queries)
        {
            ct.ThrowIfCancellationRequested();await using var query=new NpgsqlCommand(section.Sql,connection,transaction);
            query.Parameters.AddWithValue(from);query.Parameters.AddWithValue(to);query.Parameters.AddWithValue(observed);
            await using var reader=await query.ExecuteReaderAsync(ct);var count=0;
            while(await reader.ReadAsync(ct))
            {
                ct.ThrowIfCancellationRequested();if(++count>1000){truncated.Add(section.Kind);break;}
                rows.Add(new(section.Kind,SeasonDiagnosticProjection.Dimensions(reader.GetString(0)),SeasonDiagnosticProjection.Measures(reader.GetString(1))));
            }
        }
        await transaction.CommitAsync(ct);
        return new(from,to,observed,roomRead,rows,choices.Groups,choices.Coverage,truncated,
            ["Account-age/prior-season cohorts are operational facts, never skill labels; preparation levels are frozen effective entry levels.",
            "Room choices are one bounded source snapshot; database sections share a later read-only snapshot. They are not a cross-source conservation equation.",
            "Historical missing offer, profile, wallet or transaction response remains unknown. Legal over-base HP is not an anomaly.",
            "Market depth, zero balances and remaining activity budgets are as-of-query;48h conversion uses fully exposed mature listings separately from shortened/censored listings.",
            "Shop/activity overlap is descriptive, not causal purchase displacement. Equipment trade templates come from immutable transaction responses, not current equipment.",
            "First-extraction/recovery facts use committed equipment movements; outstanding recoveries are right-censored, not permanent-loss verdicts.",
            "Red timelines retain quota/mint and original owner movements; truncation and unknown ownership are explicit. Counts and amounts are exact strings, currencies stay separate."],
            new(rooms.SourceRooms,rooms.LegacyUnobservedRooms,rooms.InvalidRooms,rooms.UnknownTimestampEvents,rooms.DroppedEvents,rooms.OmittedItems,rooms.FullyObserved));
    }

    private static readonly (string Kind,string Sql)[] Queries=
    [
        ("RunCohorts","""
            WITH runs AS(
                SELECT m.season_id,m.difficulty,m.config_version,p.is_bot,s.result,
                    CASE WHEN p.is_bot THEN 'Bot' WHEN a.created_at IS NULL OR a.created_at>m.created_at THEN 'MissingIdentityHistory'
                        WHEN m.created_at-a.created_at<=interval '7 days' THEN 'AccountAgeAtMost7Days'
                        WHEN EXISTS(SELECT 1 FROM player_season_state prior WHERE prior.player_id=p.player_id AND prior.season_id<>m.season_id AND prior.joined_at<m.created_at) THEN 'PriorSeasonParticipant'
                        ELSE 'OlderAccountNoPriorSeasonProof' END cohort,
                    CASE WHEN d.starts_at IS NOT NULL THEN ((m.created_at AT TIME ZONE 'Asia/Shanghai')::date-(d.starts_at AT TIME ZONE 'Asia/Shanghai')::date+1)::text END season_day,
                    prep.snapshot_json->>'heroClass' hero,
                    (SELECT max(v::int)::text FROM jsonb_array_elements_text(CASE WHEN jsonb_typeof(prep.snapshot_json->'cardLevels')='array' THEN prep.snapshot_json->'cardLevels' ELSE '[]'::jsonb END)v) entry_max,
                    s.details_json->'telemetryProfile'->>'buildType' terminal_build,
                    CASE WHEN jsonb_typeof(rp.value->'clearedCells')='array' THEN jsonb_array_length(rp.value->'clearedCells') END cleared
                FROM matches m JOIN match_players p USING(match_id) LEFT JOIN players a ON a.user_id=p.player_id
                LEFT JOIN preparations prep ON prep.preparation_id=p.preparation_id LEFT JOIN match_settlements s ON s.match_id=m.match_id AND s.player_id=p.player_id
                LEFT JOIN season_definitions d ON d.season_id=m.season_id LEFT JOIN room_snapshots snap ON snap.room_id=m.room_id
                LEFT JOIN LATERAL(SELECT value FROM jsonb_array_elements(CASE WHEN jsonb_typeof(snap.snapshot_json->'players')='array' THEN snap.snapshot_json->'players' ELSE '[]'::jsonb END)
                    WHERE value->>'playerId'=p.player_id::text LIMIT 1)rp ON true
                WHERE m.created_at >= $1 AND m.created_at < $2 AND p.state IN('Active','Settled') AND $3::timestamptz IS NOT NULL)
            SELECT jsonb_build_object('season',season_id,'difficulty',difficulty,'config',config_version,'cohort',cohort,'seasonDay',season_day,'class',hero,'entryEffectiveMaxLevel',entry_max,'terminalBuild',terminal_build,'playerKind',CASE WHEN is_bot THEN 'Bot' ELSE 'Human' END)::text,
                jsonb_build_object('attempts',count(*)::text,'extracted',count(*) FILTER(WHERE result='Extracted')::text,'dead',count(*) FILTER(WHERE result='Dead')::text,
                    'aborted',count(*) FILTER(WHERE result='Aborted')::text,'pending',count(*) FILTER(WHERE result IS NULL)::text,
                    'successfulClearedCells',coalesce(sum(cleared) FILTER(WHERE result='Extracted'),0)::text,'failedClearedCells',coalesce(sum(cleared) FILTER(WHERE result='Dead'),0)::text,'missingClearProof',count(*) FILTER(WHERE cleared IS NULL)::text)::text
            FROM runs GROUP BY season_id,difficulty,config_version,cohort,season_day,hero,entry_max,terminal_build,is_bot
            ORDER BY season_id NULLS FIRST,difficulty,cohort,season_day,hero NULLS FIRST,entry_max NULLS FIRST,terminal_build NULLS FIRST,is_bot LIMIT 1001
            """),
        ("MarketDepth","""
            SELECT jsonb_build_object('season',l.season_id,'currency',l.currency,'quality',e.quality)::text,
                jsonb_build_object('activeListings',count(*)::text,'uniqueSellers',count(DISTINCT l.seller_id)::text,'lowestPrice',min(coalesce(l.price,l.price_gold))::text,
                    'highestPrice',max(coalesce(l.price,l.price_gold))::text,'priceSum',sum(coalesce(l.price,l.price_gold))::text)::text
            FROM market_listings l JOIN equipments e ON e.instance_id=l.equipment_id
            WHERE l.status='Active' AND l.expires_at>$3 AND (l.season_ends_at IS NULL OR l.season_ends_at>$3) AND $1<$2
            GROUP BY l.season_id,l.currency,e.quality ORDER BY l.season_id NULLS FIRST,l.currency,e.quality LIMIT 1001
            """),
        ("Listing48HourCohort","""
            WITH cohort AS(SELECT l.*,t.completed_at,
                ($3>=l.created_at+interval '48 hours' AND (l.season_ends_at IS NULL OR l.season_ends_at>=l.created_at+interval '48 hours')) mature,
                (t.completed_at>=l.created_at AND t.completed_at<l.created_at+interval '48 hours') sold48
                FROM market_listings l LEFT JOIN market_transactions t USING(listing_id) WHERE l.created_at >= $1 AND l.created_at < $2)
            SELECT jsonb_build_object('season',season_id,'currency',currency)::text,
                jsonb_build_object('listings',count(*)::text,'matureFull48Hours',count(*) FILTER(WHERE mature)::text,'matureSoldWithin48',count(*) FILTER(WHERE mature AND sold48)::text,
                    'rightCensoredOrShortened',count(*) FILTER(WHERE NOT mature)::text,'youngSoldWithin48',count(*) FILTER(WHERE NOT mature AND sold48)::text,
                    'seasonShortened',count(*) FILTER(WHERE season_ends_at<created_at+interval '48 hours')::text,'relistReplacements',count(*) FILTER(WHERE replaces_listing_id IS NOT NULL)::text)::text
            FROM cohort GROUP BY season_id,currency ORDER BY season_id NULLS FIRST,currency LIMIT 1001
            """),
        ("EquipmentMaterialTrades","""
            SELECT jsonb_build_object('season',t.season_id,'currency',t.currency,'quality',t.response_json->'Listing'->'Equipment'->>'Quality',
                'level',t.response_json->'Listing'->'Equipment'->>'Level','recipeExtracted',t.response_json->'Listing'->'Equipment'->>'RecipeExtracted')::text,
                jsonb_build_object('transactions',count(*)::text,'units',count(*)::text,'priceSum',sum(coalesce(t.price,t.price_gold))::text,'feeSum',sum(coalesce(t.fee,t.fee_gold))::text,
                    'minimumPrice',min(coalesce(t.price,t.price_gold))::text,'maximumPrice',max(coalesce(t.price,t.price_gold))::text,'missingTemplateReceipt',count(*) FILTER(WHERE t.response_json->'Listing'->'Equipment' IS NULL)::text)::text
            FROM market_transactions t WHERE t.completed_at >= $1 AND t.completed_at < $2 AND $3::timestamptz IS NOT NULL
            GROUP BY t.season_id,t.currency,t.response_json->'Listing'->'Equipment'->>'Quality',t.response_json->'Listing'->'Equipment'->>'Level',t.response_json->'Listing'->'Equipment'->>'RecipeExtracted'
            ORDER BY t.season_id NULLS FIRST,t.currency,t.response_json->'Listing'->'Equipment'->>'Quality' NULLS FIRST,
                t.response_json->'Listing'->'Equipment'->>'Level' NULLS FIRST,t.response_json->'Listing'->'Equipment'->>'RecipeExtracted' NULLS FIRST LIMIT 1001
            """),
        ("FirstCommittedEquipmentExtraction","""
            WITH extracted AS(
                SELECT DISTINCT ON(m.item_id) m.item_id,m.created_at,m.player_id,s.match_id,m.season_id,m.difficulty_id,e.quality,e.source_match_id
                FROM inventory_movements m JOIN settlement_asset_holds h ON h.hold_id=CASE WHEN m.request_id ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' THEN m.request_id::uuid END
                    AND h.asset_kind='Equipment' AND h.asset_ref=m.item_id::text AND h.player_id=m.player_id AND h.state='Committed'
                    AND h.season_id IS NOT DISTINCT FROM m.season_id AND h.difficulty_id IS NOT DISTINCT FROM m.difficulty_id
                    AND h.ruleset_id IS NOT DISTINCT FROM m.ruleset_id AND h.config_version IS NOT DISTINCT FROM m.config_version AND h.stats_version IS NOT DISTINCT FROM m.stats_version
                JOIN match_settlements s ON s.settlement_id=h.settlement_id AND s.player_id=h.player_id JOIN equipments e ON e.instance_id=m.item_id
                WHERE m.reason='settlement.extract' AND m.to_location IN('Inventory','Equipped') AND m.created_at<=$3
                ORDER BY m.item_id,m.created_at,m.movement_id)
            SELECT jsonb_build_object('season',season_id,'difficulty',difficulty_id,'quality',quality)::text,
                jsonb_build_object('firstCommittedExtractions',count(*)::text,'knownBornInSameMatch',count(*) FILTER(WHERE source_match_id=match_id)::text,
                    'differentOrUnknownMintMatch',count(*) FILTER(WHERE source_match_id IS DISTINCT FROM match_id)::text)::text
            FROM extracted WHERE created_at >= $1 AND created_at < $2 GROUP BY season_id,difficulty_id,quality ORDER BY season_id NULLS FIRST,difficulty_id NULLS FIRST,quality LIMIT 1001
            """),
        ("DeathEquipmentRecovery","""
            WITH deaths AS MATERIALIZED(
                SELECT movement_id,item_id,player_id,created_at,season_id FROM inventory_movements
                WHERE reason='settlement.death' AND to_location='RelicPile' AND created_at >= $1 AND created_at < $2),
            outcomes AS(
                SELECT d.movement_id,d.season_id,min(r.created_at) recovered_at,
                    (array_agg(r.player_id ORDER BY r.created_at,r.movement_id) FILTER(WHERE r.movement_id IS NOT NULL))[1] recipient,d.player_id
                FROM deaths d LEFT JOIN inventory_movements r ON r.item_id=d.item_id AND r.reason='settlement.extract' AND r.from_location='RelicPile'
                    AND r.to_location IN('Inventory','Equipped') AND r.created_at>=d.created_at AND r.created_at<=$3
                    AND EXISTS(SELECT 1 FROM settlement_asset_holds h WHERE h.hold_id=CASE WHEN r.request_id ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' THEN r.request_id::uuid END
                        AND h.state='Committed' AND h.asset_kind='Equipment' AND h.asset_ref=r.item_id::text AND h.player_id=r.player_id
                        AND h.season_id IS NOT DISTINCT FROM r.season_id AND h.difficulty_id IS NOT DISTINCT FROM r.difficulty_id
                        AND h.ruleset_id IS NOT DISTINCT FROM r.ruleset_id AND h.config_version IS NOT DISTINCT FROM r.config_version AND h.stats_version IS NOT DISTINCT FROM r.stats_version)
                GROUP BY d.movement_id,d.season_id,d.player_id)
            SELECT jsonb_build_object('season',season_id)::text,
                jsonb_build_object('deathCustodyRecords',count(*)::text,'committedRecoveryObserved',count(*) FILTER(WHERE recovered_at IS NOT NULL)::text,
                    'sameActorRecovery',count(*) FILTER(WHERE recovered_at IS NOT NULL AND recipient=player_id)::text,
                    'otherActorRecovery',count(*) FILTER(WHERE recovered_at IS NOT NULL AND recipient<>player_id)::text,
                    'notRecoveredYetRightCensored',count(*) FILTER(WHERE recovered_at IS NULL)::text)::text
            FROM outcomes GROUP BY season_id ORDER BY season_id NULLS FIRST LIMIT 1001
            """),
        ("EquipmentTradePropertiesAsOfQuery","""
            SELECT jsonb_build_object('season',origin_season_id,'quality',quality,'assetScope',asset_scope)::text,
                jsonb_build_object('instances',count(*)::text,'unboundRealActiveRealm',count(*) FILTER(WHERE NOT is_bound AND asset_scope='ActiveSeason' AND coalesce(source_kind,'') NOT IN('BotProjection','Borrowed') AND location IN('Inventory','Equipped','MarketListed'))::text,
                    'currentlyListed',count(*) FILTER(WHERE location='MarketListed')::text,'bound',count(*) FILTER(WHERE is_bound)::text,
                    'sampleAlreadyExtracted',count(*) FILTER(WHERE recipe_extracted)::text)::text
            FROM equipments WHERE $1<$2 AND $3::timestamptz IS NOT NULL GROUP BY origin_season_id,quality,asset_scope ORDER BY origin_season_id NULLS FIRST,quality,asset_scope NULLS FIRST LIMIT 1001
            """),
        ("ZeroBalancesAsOfQuery","""
            SELECT jsonb_build_object('season',w.season_id,'archived',CASE WHEN w.archived_at IS NULL THEN 'false' ELSE 'true' END)::text,
                jsonb_build_object('wallets',count(*)::text,'zeroGold',count(*) FILTER(WHERE w.gold=0)::text,'zeroFragments',count(*) FILTER(WHERE w.equipment_fragments=0)::text,
                    'zeroBlueprints',count(*) FILTER(WHERE w.blueprint_marks=0)::text,'zeroOrangeBlueprints',count(*) FILTER(WHERE w.orange_blueprint_marks=0)::text,
                    'permanentDiamondZero',count(*) FILTER(WHERE p.diamond=0)::text,'missingPermanentWallet',count(*) FILTER(WHERE p.player_id IS NULL)::text)::text
            FROM player_season_wallets w LEFT JOIN player_wallets p USING(player_id) WHERE $1<$2 AND $3::timestamptz IS NOT NULL
            GROUP BY w.season_id,(w.archived_at IS NULL) ORDER BY w.season_id,(w.archived_at IS NULL) LIMIT 1001
            """),
        ("ShopSpendAndActivityOverlap","""
            SELECT jsonb_build_object('season',p.season_id,'config',p.config_version,'quotaGroup',p.quota_group,'reset',p.reset_key)::text,
                jsonb_build_object('purchases',count(*)::text,'buyers',count(DISTINCT p.player_id)::text,'units',sum(p.quantity)::text,'goldSpent',sum(p.price_gold)::text,
                    'missingPostPurchaseBalance',count(*) FILTER(WHERE p.response_json->>'GoldAfter' IS NULL)::text,
                    'postPurchaseBalanceBelow100',count(*) FILTER(WHERE (p.response_json->>'GoldAfter')::numeric<100)::text,
                    'buyersWithActivityClaimsSameShanghaiDay',count(DISTINCT p.player_id) FILTER(WHERE EXISTS(SELECT 1 FROM season_activity_redemptions a WHERE a.player_id=p.player_id AND a.season_id=p.season_id AND a.state='Claimed' AND
                        (a.claimed_at AT TIME ZONE 'Asia/Shanghai')::date=(p.created_at AT TIME ZONE 'Asia/Shanghai')::date))::text)::text
            FROM shop_purchases p WHERE p.created_at >= $1 AND p.created_at < $2 AND $3::timestamptz IS NOT NULL
            GROUP BY p.season_id,p.config_version,p.quota_group,p.reset_key ORDER BY p.season_id NULLS FIRST,p.config_version NULLS FIRST,p.quota_group NULLS FIRST,p.reset_key LIMIT 1001
            """),
        ("ActivityBudgetAndPeak","""
            WITH claims AS(SELECT season_id,event_id,reward_kind,(claimed_at AT TIME ZONE 'Asia/Shanghai')::date claim_day,count(*) claims,sum(reward_amount) amount,sum(token_cost) tokens
                FROM season_activity_redemptions WHERE state='Claimed' AND claimed_at >= $1 AND claimed_at < $2 GROUP BY season_id,event_id,reward_kind,(claimed_at AT TIME ZONE 'Asia/Shanghai')::date),
            summaries AS(SELECT season_id,event_id,reward_kind,sum(claims) claims,sum(amount) amount,sum(tokens) tokens,max(claims) daily_claim_peak,max(amount) daily_amount_peak FROM claims GROUP BY season_id,event_id,reward_kind)
            SELECT jsonb_build_object('season',season_id,'event',event_id,'rewardKind',reward_kind)::text,
                jsonb_build_object('claims',claims::text,'actualRewardAmount',amount::text,'tokensSpent',tokens::text,'peakDailyClaims',daily_claim_peak::text,'peakDailyAmount',daily_amount_peak::text,
                    'accounts',(SELECT count(*)::text FROM player_season_activity_accounts a WHERE a.season_id=s.season_id AND a.event_id=s.event_id),
                    'remainingTokenBudget',(SELECT coalesce(sum(earned-spent),0)::text FROM player_season_activity_accounts a WHERE a.season_id=s.season_id AND a.event_id=s.event_id))::text
            FROM summaries s WHERE $3::timestamptz IS NOT NULL ORDER BY season_id,event_id,reward_kind LIMIT 1001
            """),
        ("RedQuotaAndAttempts","""
            SELECT jsonb_build_object('scope',q.quota_scope,'week',q.week_key::text,'item',q.equipment_id::text,'source',q.source)::text,
                jsonb_build_object('quotaClaimed',q.red_dropped_this_week::text,'mintedAttempts',(SELECT count(*)::text FROM season_red_drop_attempts r WHERE r.quota_scope=q.quota_scope AND r.week_key=q.week_key AND r.status='Minted'),
                    'originalAttempts',(SELECT count(*)::text FROM season_red_drop_attempts r WHERE r.quota_scope=q.quota_scope AND r.week_key=q.week_key),
                    'matchingMint',(SELECT count(*)::text FROM season_red_drop_attempts r WHERE r.quota_scope=q.quota_scope AND r.week_key=q.week_key AND r.equipment_id=q.equipment_id AND r.status='Minted'))::text
            FROM red_equipment_weekly_quotas q WHERE q.week_key >= ($1 AT TIME ZONE 'Asia/Shanghai')::date-7 AND q.week_key <=($2 AT TIME ZONE 'Asia/Shanghai')::date AND $3::timestamptz IS NOT NULL
            ORDER BY q.quota_scope,q.week_key LIMIT 1001
            """),
        ("ActivityAccountsAsOfQuery","""
            SELECT jsonb_build_object('season',e.season_id,'event',e.event_id)::text,
                jsonb_build_object('accounts',count(a.player_id)::text,'earnedTokens',coalesce(sum(a.earned),0)::text,'spentTokens',coalesce(sum(a.spent),0)::text,
                    'remainingEarnedTokens',coalesce(sum(a.earned-a.spent),0)::text,'maximumUnissuedTokensForKnownAccounts',coalesce(sum(e.token_cap-a.earned),0)::text)::text
            FROM season_activity_events e LEFT JOIN player_season_activity_accounts a USING(season_id,event_id)
            WHERE $1<$2 AND $3::timestamptz IS NOT NULL GROUP BY e.season_id,e.event_id ORDER BY e.season_id,e.event_id LIMIT 1001
            """),
        ("RedMintAttempts","""
            SELECT jsonb_build_object('attempt',attempt_id::text,'match',match_id::text,'player',player_id::text,'scope',quota_scope,'week',week_key::text,'source',source,
                'sourceKey',source_key,'season',season_id,'difficulty',difficulty::text,'config',config_version,'stats',stats_version,'status',status,'item',equipment_id::text,
                'occurredAt',occurred_at::text,'handledAt',handled_at::text)::text,jsonb_build_object('originalAttempts','1')::text
            FROM season_red_drop_attempts WHERE occurred_at >= $1 AND occurred_at < $2 AND handled_at<=$3 ORDER BY occurred_at,attempt_id LIMIT 1001
            """),
        ("RedInstanceTimeline","""
            WITH red AS MATERIALIZED(SELECT instance_id,mint_id,quota_scope,mint_week,origin_season_id,stats_version FROM equipments WHERE quality='Red' ORDER BY created_at,instance_id LIMIT 1001)
            SELECT jsonb_build_object('item',e.instance_id::text,'mint',e.mint_id::text,'scope',e.quota_scope,'week',e.mint_week::text,'originSeason',e.origin_season_id,
                'statsVersion',e.stats_version,'movement',m.movement_id::text,'at',m.created_at::text,'reason',m.reason,'from',m.from_location,'to',m.to_location,'fromOwner',m.from_owner_id::text,'toOwner',m.to_owner_id::text)::text,
                jsonb_build_object('recordedMovement',CASE WHEN m.movement_id IS NULL THEN '0' ELSE '1' END,'missingOwnershipLeg',CASE WHEN m.movement_id IS NOT NULL AND(m.from_owner_id IS NULL OR m.to_owner_id IS NULL) THEN '1' ELSE '0' END)::text
            FROM red e LEFT JOIN inventory_movements m ON m.item_id=e.instance_id WHERE $1<$2 AND $3::timestamptz IS NOT NULL ORDER BY e.instance_id,m.created_at NULLS FIRST,m.movement_id LIMIT 1001
            """)
    ];
}
