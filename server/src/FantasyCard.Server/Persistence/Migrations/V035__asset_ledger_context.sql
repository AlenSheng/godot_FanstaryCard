ALTER TABLE economy_ledger
    ADD COLUMN difficulty_id varchar(16), ADD COLUMN ruleset_id varchar(80),
    ADD COLUMN config_version varchar(80), ADD COLUMN stats_version varchar(80),
    ADD CONSTRAINT fk_economy_ledger_context FOREIGN KEY (season_id,ruleset_id,config_version,stats_version)
        REFERENCES season_definitions(season_id,ruleset_id,config_version,stats_version);
ALTER TABLE inventory_movements
    ADD COLUMN difficulty_id varchar(16), ADD COLUMN ruleset_id varchar(80),
    ADD COLUMN config_version varchar(80), ADD COLUMN stats_version varchar(80),
    ADD CONSTRAINT fk_inventory_movement_context FOREIGN KEY (season_id,ruleset_id,config_version,stats_version)
        REFERENCES season_definitions(season_id,ruleset_id,config_version,stats_version);
-- Existing unknown fields remain NULL; no historical difficulty is invented.
