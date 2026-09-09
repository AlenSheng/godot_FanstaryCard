CREATE TABLE IF NOT EXISTS settlement_notification_outbox (
    settlement_id uuid PRIMARY KEY REFERENCES match_settlements(settlement_id) ON DELETE CASCADE,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    match_id uuid NOT NULL REFERENCES matches(match_id),
    result varchar(16) NOT NULL CHECK (result IN ('Extracted', 'Dead', 'Aborted')),
    created_at timestamptz NOT NULL,
    published_at timestamptz
);

CREATE INDEX IF NOT EXISTS ix_settlement_notification_outbox_pending
    ON settlement_notification_outbox(created_at, settlement_id)
    WHERE published_at IS NULL;

INSERT INTO settlement_notification_outbox(settlement_id, player_id, match_id, result, created_at)
SELECT settlement_id, player_id, match_id, result, created_at
FROM match_settlements
ON CONFLICT (settlement_id) DO NOTHING;
