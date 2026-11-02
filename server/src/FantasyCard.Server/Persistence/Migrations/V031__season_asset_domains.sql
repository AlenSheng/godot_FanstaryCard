-- Published configuration snapshots support recovery; Excel remains the authoring source.
CREATE TABLE season_definitions (
    season_id varchar(80) PRIMARY KEY CHECK (season_id ~ '^[A-Za-z0-9_.-]+$'),
    ruleset_id varchar(80) NOT NULL,
    config_version varchar(80),
    config_sha256 varchar(64),
    stats_version varchar(80),
    starts_at timestamptz,
    ends_at timestamptz,
    duration_days integer,
    highest_open_difficulty smallint NOT NULL DEFAULT 0 CHECK (highest_open_difficulty BETWEEN 0 AND 5),
    published_at timestamptz NOT NULL,
    CONSTRAINT ck_season_definition_shape CHECK (
        (season_id = 'legacy-gdd-0.70' AND ruleset_id = 'legacy'
         AND config_version IS NULL AND config_sha256 IS NULL AND stats_version IS NULL
         AND starts_at IS NULL AND ends_at IS NULL AND duration_days IS NULL
         AND highest_open_difficulty = 0)
        OR
        (season_id <> 'legacy-gdd-0.70' AND ruleset_id = 'season-v1'
         AND config_version IS NOT NULL AND config_version ~ '^[A-Za-z0-9_.-]+$'
         AND config_sha256 IS NOT NULL AND config_sha256 ~ '^[0-9a-f]{64}$'
         AND stats_version IS NOT NULL AND stats_version ~ '^[A-Za-z0-9_.-]+$'
         AND starts_at IS NOT NULL AND ends_at IS NOT NULL AND ends_at > starts_at
         AND duration_days IS NOT NULL AND duration_days BETWEEN 30 AND 60
         AND (starts_at AT TIME ZONE 'Asia/Shanghai')::time = TIME '00:00'
         AND (ends_at AT TIME ZONE 'Asia/Shanghai')::time = TIME '00:00'
         AND (ends_at AT TIME ZONE 'Asia/Shanghai') =
             (starts_at AT TIME ZONE 'Asia/Shanghai') + make_interval(days => duration_days))
    ),
    EXCLUDE USING gist (tstzrange(starts_at, ends_at, '[)') WITH &&)
        WHERE (ruleset_id = 'season-v1')
);

-- This marker has deliberately unknown historical dates/versions. It cannot open rooms.
INSERT INTO season_definitions (season_id, ruleset_id, published_at)
VALUES ('legacy-gdd-0.70', 'legacy', CURRENT_TIMESTAMP);

CREATE TABLE player_season_state (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    season_id varchar(80) NOT NULL REFERENCES season_definitions(season_id),
    highest_unlocked_difficulty smallint NOT NULL DEFAULT 0 CHECK (highest_unlocked_difficulty BETWEEN 0 AND 5),
    experience bigint NOT NULL DEFAULT 0 CHECK (experience >= 0),
    joined_at timestamptz NOT NULL,
    archived_at timestamptz,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    PRIMARY KEY (player_id, season_id)
);

CREATE TABLE player_season_wallets (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    season_id varchar(80) NOT NULL REFERENCES season_definitions(season_id),
    gold bigint NOT NULL DEFAULT 0 CHECK (gold >= 0),
    equipment_fragments bigint NOT NULL DEFAULT 0 CHECK (equipment_fragments >= 0),
    challenge_marks bigint NOT NULL DEFAULT 0 CHECK (challenge_marks >= 0),
    archived_at timestamptz,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    PRIMARY KEY (player_id, season_id)
);

CREATE TABLE season_archive_jobs (
    job_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    from_season_id varchar(80) NOT NULL REFERENCES season_definitions(season_id),
    to_season_id varchar(80) REFERENCES season_definitions(season_id),
    status varchar(24) NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending', 'WaitingAssets', 'Running', 'Completed', 'Failed')),
    phase varchar(24) NOT NULL DEFAULT 'WaitingAssets',
    cursor_id uuid,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error_code varchar(80),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    CHECK (from_season_id IS DISTINCT FROM to_season_id),
    UNIQUE (player_id, from_season_id)
);

-- The business transaction still owns item grants; this key also protects wallet replay.
CREATE TABLE season_wallet_operations (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    season_id varchar(80) NOT NULL REFERENCES season_definitions(season_id),
    reason varchar(80) NOT NULL,
    request_id varchar(80) NOT NULL,
    request_hash varchar(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    gold_after bigint NOT NULL CHECK (gold_after >= 0),
    fragments_after bigint NOT NULL CHECK (fragments_after >= 0),
    marks_after bigint NOT NULL CHECK (marks_after >= 0),
    wallet_version bigint NOT NULL CHECK (wallet_version > 0),
    archived_at timestamptz,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (player_id, season_id, reason, request_id)
);

ALTER TABLE equipments
    ADD COLUMN origin_season_id varchar(80) REFERENCES season_definitions(season_id),
    ADD COLUMN season_id varchar(80) REFERENCES season_definitions(season_id),
    ADD COLUMN asset_scope varchar(24),
    ADD COLUMN source_match_id uuid,
    ADD COLUMN generated_difficulty smallint CHECK (generated_difficulty BETWEEN 0 AND 5),
    ADD COLUMN loot_rule_id varchar(80),
    ADD COLUMN stats_version varchar(80),
    ADD COLUMN source_kind varchar(32),
    ADD COLUMN mint_id uuid,
    ADD COLUMN quota_scope varchar(80),
    ADD COLUMN mint_week date,
    ADD COLUMN recipe_extracted boolean NOT NULL DEFAULT false,
    ADD CONSTRAINT ck_equipment_season_domain CHECK (
        (origin_season_id IS NULL AND season_id IS NULL AND asset_scope IS NULL)
        OR
        (origin_season_id IS NOT NULL AND season_id IS NOT NULL
         AND origin_season_id = season_id AND asset_scope IS NOT NULL
         AND asset_scope IN ('ActiveSeason', 'ArchivedSeason')
         AND (season_id <> 'legacy-gdd-0.70' OR asset_scope = 'ArchivedSeason')
         AND (season_id = 'legacy-gdd-0.70'
              OR (stats_version IS NOT NULL AND length(stats_version) > 0
                  AND source_kind IS NOT NULL AND length(source_kind) > 0
                  AND generated_difficulty IS NOT NULL)))
    );

-- Match history may expire before an item's provenance, so source_match_id has no FK.
CREATE INDEX ix_equipments_owner_season_location ON equipments(owner_id, season_id, location);
CREATE INDEX ix_season_archive_jobs_pending ON season_archive_jobs(status, updated_at)
    WHERE status IN ('Pending', 'WaitingAssets', 'Running', 'Failed');

ALTER TABLE economy_ledger
    ADD COLUMN season_id varchar(80) REFERENCES season_definitions(season_id),
    ADD COLUMN source_kind varchar(32);
ALTER TABLE economy_ledger DROP CONSTRAINT economy_ledger_currency_check;
ALTER TABLE economy_ledger ADD CONSTRAINT economy_ledger_currency_check
    CHECK (currency IN ('Gold', 'Diamond', 'WarriorSoul', 'ClassSoul',
                        'PriestSoul', 'MageSoul', 'GuardianSoul', 'EquipmentFragments', 'ChallengeMarks'));
ALTER TABLE inventory_movements ADD COLUMN season_id varchar(80) REFERENCES season_definitions(season_id);

-- No existing wallet, card, weapon, deck or equipment is reset by this migration.
