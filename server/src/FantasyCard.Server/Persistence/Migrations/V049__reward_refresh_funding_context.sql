ALTER TABLE reward_refresh_operations
    ADD COLUMN funding_scope varchar(24) NOT NULL DEFAULT 'LegacyWallet'
        CHECK(funding_scope IN ('LegacyWallet','SeasonWallet')),
    ADD COLUMN season_id varchar(80),
    ADD COLUMN difficulty_id varchar(16),
    ADD COLUMN ruleset_id varchar(80),
    ADD COLUMN config_version varchar(80),
    ADD COLUMN stats_version varchar(80),
    ADD CONSTRAINT ck_reward_refresh_funding_context CHECK (
        (funding_scope='LegacyWallet' AND season_id IS NULL AND ruleset_id IS NULL AND stats_version IS NULL
            AND (difficulty_id IS NULL OR difficulty_id='Standard'))
        OR
        (funding_scope='SeasonWallet' AND season_id IS NOT NULL AND difficulty_id IS NOT NULL AND difficulty_id IN ('D0','D1','D2','D3','D4','D5')
            AND ruleset_id IS NOT NULL AND ruleset_id='season-v1' AND config_version IS NOT NULL AND stats_version IS NOT NULL)),
    ADD CONSTRAINT fk_reward_refresh_match_context
        FOREIGN KEY(match_id,season_id,difficulty_id,ruleset_id,config_version,stats_version)
        REFERENCES matches(match_id,season_id,difficulty,ruleset_id,config_version,stats_version);

-- Every pre-migration reservation actually debited player_wallets.gold, even
-- when its room was seasonal. Keep that real payer; never infer a new payer
-- from today's season or from the referenced match.
