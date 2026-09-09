CREATE TABLE IF NOT EXISTS equipments (
    instance_id uuid PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    slot varchar(24) NOT NULL CHECK (slot IN ('Head', 'Chest', 'Hands', 'Legs', 'Feet')),
    quality varchar(24) NOT NULL,
    level integer NOT NULL DEFAULT 0 CHECK (level BETWEEN 0 AND 5),
    is_bound boolean NOT NULL DEFAULT false,
    location varchar(32) NOT NULL CHECK (location IN ('Inventory', 'Equipped', 'MarketListed', 'PreparationLocked', 'InMatchEquipped', 'InMatchBackpack', 'RelicPile', 'EnhanceMaterialConsumed')),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_equipments_owner_location ON equipments(owner_id, location);

CREATE TABLE IF NOT EXISTS player_loadouts (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    hero_class smallint NOT NULL CHECK (hero_class BETWEEN 1 AND 3),
    head_id uuid NULL REFERENCES equipments(instance_id),
    chest_id uuid NULL REFERENCES equipments(instance_id),
    hands_id uuid NULL REFERENCES equipments(instance_id),
    legs_id uuid NULL REFERENCES equipments(instance_id),
    feet_id uuid NULL REFERENCES equipments(instance_id),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    PRIMARY KEY (player_id, hero_class)
);

CREATE TABLE IF NOT EXISTS idempotency_records (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    scope varchar(80) NOT NULL,
    request_id varchar(80) NOT NULL,
    request_hash varchar(64) NOT NULL,
    response_json jsonb NULL,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (player_id, scope, request_id)
);

CREATE TABLE IF NOT EXISTS preparations (
    preparation_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    request_id varchar(80) NOT NULL,
    request_hash varchar(64) NOT NULL,
    snapshot_json jsonb NOT NULL,
    status varchar(24) NOT NULL CHECK (status IN ('Active', 'Queued', 'Matched', 'Cancelled', 'Expired', 'Settled')),
    config_version varchar(80) NOT NULL,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    UNIQUE (player_id, request_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_preparations_active_player
    ON preparations(player_id) WHERE status IN ('Active', 'Queued', 'Matched');

CREATE TABLE IF NOT EXISTS preparation_assets (
    preparation_id uuid NOT NULL REFERENCES preparations(preparation_id) ON DELETE CASCADE,
    asset_type varchar(32) NOT NULL,
    asset_id varchar(80) NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (preparation_id, asset_type, asset_id)
);
