CREATE TABLE IF NOT EXISTS realtime_tickets (
    ticket_hash bytea PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    used_at timestamptz NULL
);

CREATE INDEX IF NOT EXISTS ix_realtime_tickets_expiry ON realtime_tickets(expires_at);
