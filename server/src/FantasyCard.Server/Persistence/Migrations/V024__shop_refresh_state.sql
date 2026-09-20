CREATE TABLE IF NOT EXISTS shop_refresh_states (
    reset_key varchar(32) PRIMARY KEY,
    shop_reset_key varchar(32) NOT NULL,
    rotation_key varchar(32) NOT NULL,
    used_count integer NOT NULL DEFAULT 0 CHECK (used_count >= 0),
    updated_at timestamptz NOT NULL
);
