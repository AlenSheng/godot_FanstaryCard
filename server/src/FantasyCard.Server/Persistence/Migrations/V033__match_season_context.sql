ALTER TABLE matches
    ADD COLUMN season_id varchar(80),
    ADD COLUMN ruleset_id varchar(80),
    ADD COLUMN stats_version varchar(80),
    ADD CONSTRAINT fk_match_published_context
        FOREIGN KEY (season_id,ruleset_id,config_version,stats_version)
        REFERENCES season_definitions(season_id,ruleset_id,config_version,stats_version);
ALTER TABLE matches DROP CONSTRAINT matches_difficulty_check;
ALTER TABLE matches ADD CONSTRAINT ck_match_season_context CHECK (
    (season_id IS NULL AND ruleset_id IS NULL AND stats_version IS NULL AND difficulty='Standard')
    OR
    (season_id IS NOT NULL AND ruleset_id IS NOT NULL AND ruleset_id='season-v1'
     AND stats_version IS NOT NULL AND length(stats_version)>0 AND difficulty IN ('D0','D1','D2','D3','D4','D5'))
);
CREATE INDEX ix_preparations_match_context ON preparations
    (season_id,difficulty_id,ruleset_id,config_version,stats_version) WHERE status='Queued';
