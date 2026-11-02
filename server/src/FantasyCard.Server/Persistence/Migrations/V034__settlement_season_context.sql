ALTER TABLE matches ADD CONSTRAINT uq_match_settlement_context
    UNIQUE (match_id,season_id,difficulty,ruleset_id,config_version,stats_version);
ALTER TABLE match_settlements
    ADD COLUMN season_id varchar(80), ADD COLUMN difficulty_id varchar(16),
    ADD COLUMN ruleset_id varchar(80), ADD COLUMN config_version varchar(80), ADD COLUMN stats_version varchar(80),
    ADD CONSTRAINT ck_settlement_season_context CHECK (
        (season_id IS NULL AND ruleset_id IS NULL AND stats_version IS NULL
         AND (difficulty_id IS NULL OR difficulty_id='Standard'))
        OR (season_id IS NOT NULL AND difficulty_id IS NOT NULL AND difficulty_id IN ('D0','D1','D2','D3','D4','D5')
            AND ruleset_id IS NOT NULL AND ruleset_id='season-v1' AND config_version IS NOT NULL AND stats_version IS NOT NULL)),
    ADD CONSTRAINT fk_settlement_match_context
        FOREIGN KEY (match_id,season_id,difficulty_id,ruleset_id,config_version,stats_version)
        REFERENCES matches(match_id,season_id,difficulty,ruleset_id,config_version,stats_version),
    ADD CONSTRAINT uq_settlement_hold_context
        UNIQUE (settlement_id,player_id,season_id,difficulty_id,ruleset_id,config_version,stats_version);
ALTER TABLE settlement_asset_holds
    ADD COLUMN season_id varchar(80), ADD COLUMN difficulty_id varchar(16),
    ADD COLUMN ruleset_id varchar(80), ADD COLUMN config_version varchar(80), ADD COLUMN stats_version varchar(80),
    ADD CONSTRAINT ck_settlement_hold_season_context CHECK (
        (season_id IS NULL AND ruleset_id IS NULL AND stats_version IS NULL
         AND (difficulty_id IS NULL OR difficulty_id='Standard'))
        OR (season_id IS NOT NULL AND difficulty_id IS NOT NULL AND difficulty_id IN ('D0','D1','D2','D3','D4','D5')
            AND ruleset_id IS NOT NULL AND ruleset_id='season-v1' AND config_version IS NOT NULL AND stats_version IS NOT NULL)),
    ADD CONSTRAINT fk_hold_settlement_context
        FOREIGN KEY (settlement_id,player_id,season_id,difficulty_id,ruleset_id,config_version,stats_version)
        REFERENCES match_settlements(settlement_id,player_id,season_id,difficulty_id,ruleset_id,config_version,stats_version);
CREATE INDEX ix_settlement_season ON match_settlements(season_id,created_at);
-- Historical NULL contexts stay unknown. Never infer their season from today's schedule.
