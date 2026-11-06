ALTER TABLE preparations
    ADD COLUMN season_id varchar(80) REFERENCES season_definitions(season_id),
    ADD COLUMN difficulty_id smallint CHECK (difficulty_id BETWEEN 0 AND 5),
    ADD COLUMN ruleset_id varchar(80),
    ADD COLUMN stats_version varchar(80),
    ADD CONSTRAINT ck_preparation_season_context CHECK (
        (season_id IS NULL AND difficulty_id IS NULL AND ruleset_id IS NULL AND stats_version IS NULL)
        OR
        (season_id IS NOT NULL AND difficulty_id IS NOT NULL AND ruleset_id IS NOT NULL AND ruleset_id='season-v1'
         AND stats_version IS NOT NULL AND length(stats_version)>0)
    );
ALTER TABLE season_definitions ADD CONSTRAINT uq_season_definition_context
    UNIQUE (season_id,ruleset_id,config_version,stats_version);
ALTER TABLE preparations ADD CONSTRAINT fk_preparation_published_context
    FOREIGN KEY (season_id,ruleset_id,config_version,stats_version)
    REFERENCES season_definitions(season_id,ruleset_id,config_version,stats_version);
CREATE INDEX ix_preparations_season_status ON preparations(season_id,status);
