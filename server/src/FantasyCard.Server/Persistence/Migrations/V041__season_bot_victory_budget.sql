-- Legacy BotBudget entries keep their prior policy. New victory gear is at
-- most one real item for each human/match, even after transfer or destruction.
ALTER TABLE equipments ADD CONSTRAINT ck_season_bot_victory_source CHECK (
    COALESCE(loot_rule_id,'') <> 'season-bot-reward-v1'
    OR COALESCE((
        source_kind='BotReward' AND source_match_id IS NOT NULL
        AND source_loot_json->>'Source'='BotVictory'
        AND length(source_loot_json->>'BotRewardOwnerId')=36
        AND length(source_loot_json->>'DefeatedBotId')=36
        AND quality IN ('White','Green','Blue') AND level=0
    ),false)
);

CREATE UNIQUE INDEX ux_season_bot_victory_human_match
    ON equipments(source_match_id,(source_loot_json->>'BotRewardOwnerId'))
    WHERE loot_rule_id='season-bot-reward-v1';
