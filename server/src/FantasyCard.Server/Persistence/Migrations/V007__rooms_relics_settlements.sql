CREATE TABLE IF NOT EXISTS room_snapshots (
    room_id uuid PRIMARY KEY REFERENCES matches(room_id) ON DELETE CASCADE,
    revision bigint NOT NULL CHECK (revision >= 0),
    snapshot_json jsonb NOT NULL,
    rng_state_json jsonb NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS room_event_buffers (
    room_id uuid NOT NULL REFERENCES matches(room_id) ON DELETE CASCADE,
    sequence bigint NOT NULL CHECK (sequence > 0),
    event_json jsonb NOT NULL,
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (room_id, sequence)
);

CREATE INDEX IF NOT EXISTS ix_room_event_buffers_expiry ON room_event_buffers(expires_at);

CREATE TABLE IF NOT EXISTS relic_piles (
    pile_id uuid PRIMARY KEY,
    room_id uuid NOT NULL REFERENCES matches(room_id) ON DELETE CASCADE,
    grid_row smallint NOT NULL CHECK (grid_row BETWEEN 0 AND 5),
    grid_column smallint NOT NULL CHECK (grid_column BETWEEN 0 AND 5),
    dead_player_id uuid NOT NULL,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    status varchar(16) NOT NULL CHECK (status IN ('Active', 'Closed')),
    created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_relic_piles_room_grid ON relic_piles(room_id, grid_row, grid_column, status);

CREATE TABLE IF NOT EXISTS relic_items (
    item_id uuid PRIMARY KEY,
    pile_id uuid NOT NULL REFERENCES relic_piles(pile_id) ON DELETE CASCADE,
    asset_kind varchar(32) NOT NULL CHECK (asset_kind IN ('Equipment', 'Gold', 'WarriorSoul', 'ClassSoul', 'EquipmentFragments', 'HealthPotion')),
    asset_ref varchar(160) NOT NULL,
    asset_snapshot jsonb NOT NULL,
    quantity bigint NOT NULL CHECK (quantity > 0),
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS match_settlements (
    settlement_id uuid PRIMARY KEY,
    match_id uuid NOT NULL REFERENCES matches(match_id) ON DELETE CASCADE,
    player_id uuid NOT NULL,
    result varchar(16) NOT NULL CHECK (result IN ('Extracted', 'Dead', 'Aborted')),
    details_json jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (match_id, player_id)
);

CREATE TABLE IF NOT EXISTS settlement_asset_holds (
    hold_id uuid PRIMARY KEY,
    settlement_id uuid NOT NULL REFERENCES match_settlements(settlement_id) ON DELETE CASCADE,
    player_id uuid NOT NULL,
    asset_kind varchar(32) NOT NULL,
    asset_ref varchar(160) NOT NULL,
    asset_snapshot jsonb NOT NULL,
    state varchar(16) NOT NULL CHECK (state IN ('Held', 'Committed', 'Released', 'Pending')),
    created_at timestamptz NOT NULL,
    UNIQUE (settlement_id, asset_kind, asset_ref)
);

CREATE INDEX IF NOT EXISTS ix_settlement_asset_holds_player_state
    ON settlement_asset_holds(player_id, state);
