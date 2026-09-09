CREATE TABLE IF NOT EXISTS economy_ledger (
    ledger_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    request_id varchar(80),
    currency varchar(32) NOT NULL CHECK (currency IN ('Gold', 'Diamond', 'WarriorSoul', 'ClassSoul', 'EquipmentFragments')),
    delta bigint NOT NULL,
    balance_after bigint NOT NULL CHECK (balance_after >= 0),
    reason varchar(80) NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_economy_ledger_player_created
    ON economy_ledger(player_id, created_at DESC);

CREATE TABLE IF NOT EXISTS inventory_movements (
    movement_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    item_id uuid,
    from_location varchar(32),
    to_location varchar(32) NOT NULL,
    reason varchar(80) NOT NULL,
    request_id varchar(80),
    created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_inventory_movements_player_created
    ON inventory_movements(player_id, created_at DESC);
