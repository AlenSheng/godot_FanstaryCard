-- Retain existing claims in the same primary logical economy. A new season,
-- process or channel cannot create a second entry for the same scope/week.
ALTER TABLE red_equipment_weekly_quotas ADD COLUMN quota_scope varchar(80) NOT NULL DEFAULT 'primary';
ALTER TABLE red_equipment_weekly_quotas DROP CONSTRAINT red_equipment_weekly_quotas_pkey;
ALTER TABLE red_equipment_weekly_quotas ADD PRIMARY KEY(quota_scope,week_key);
ALTER TABLE red_equipment_weekly_quotas DROP CONSTRAINT IF EXISTS red_equipment_weekly_quotas_source_check;
ALTER TABLE red_equipment_weekly_quotas ADD CONSTRAINT ck_red_quota_source CHECK(source IS NULL OR source IN ('ChaosBoss','ShopChest','Activity'));

CREATE TABLE red_economy_scope_binding (
    singleton boolean PRIMARY KEY CHECK(singleton),
    quota_scope varchar(80) NOT NULL UNIQUE
);
INSERT INTO red_economy_scope_binding VALUES(true,'primary');
ALTER TABLE red_equipment_weekly_quotas ADD CONSTRAINT fk_red_quota_economy
    FOREIGN KEY(quota_scope) REFERENCES red_economy_scope_binding(quota_scope);

CREATE TABLE season_red_drop_attempts (
    attempt_id uuid PRIMARY KEY,
    match_id uuid NOT NULL REFERENCES matches(match_id),
    player_id uuid NOT NULL REFERENCES players(user_id),
    quota_scope varchar(80) NOT NULL,
    week_key date NOT NULL,
    source varchar(32) NOT NULL CHECK(source IN ('ChaosBoss','ShopChest','Activity')),
    source_key varchar(160) NOT NULL,
    season_id varchar(80) NOT NULL REFERENCES season_definitions(season_id),
    difficulty smallint NOT NULL CHECK(difficulty BETWEEN 0 AND 5),
    ruleset_id varchar(80) NOT NULL,
    config_version varchar(80) NOT NULL,
    stats_version varchar(80) NOT NULL,
    roll integer NOT NULL CHECK(roll BETWEEN 0 AND 9999),
    equipment_seed integer NOT NULL,
    occurred_at timestamptz NOT NULL,
    request_hash varchar(64) NOT NULL,
    status varchar(16) NOT NULL CHECK(status IN ('Miss','Exhausted','Closed','Minted')),
    equipment_id uuid UNIQUE REFERENCES equipments(instance_id),
    equipment_json jsonb,
    handled_at timestamptz NOT NULL,
    UNIQUE(match_id,player_id,source,source_key),
    CHECK((status='Minted' AND equipment_id IS NOT NULL AND equipment_json IS NOT NULL)
        OR (status<>'Minted' AND equipment_id IS NULL AND equipment_json IS NULL))
);

CREATE UNIQUE INDEX ux_red_original_mint_id ON equipments(mint_id) WHERE mint_id IS NOT NULL;
