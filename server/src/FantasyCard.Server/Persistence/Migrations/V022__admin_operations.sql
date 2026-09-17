CREATE TABLE player_bans (
    player_id uuid PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
    reason varchar(500) NOT NULL,
    banned_at timestamptz NOT NULL,
    banned_by varchar(80) NOT NULL
);

CREATE TABLE admin_audit (
    audit_id uuid PRIMARY KEY,
    actor varchar(80) NOT NULL,
    action varchar(40) NOT NULL,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    details_json jsonb NOT NULL,
    request_id varchar(80) NOT NULL UNIQUE,
    created_at timestamptz NOT NULL
);

CREATE INDEX ix_admin_audit_player_created ON admin_audit(player_id, created_at DESC);
