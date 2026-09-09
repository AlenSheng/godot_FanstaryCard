ALTER TABLE match_settlements
    ADD COLUMN IF NOT EXISTS acknowledged_at timestamptz;

-- Existing rows predate the inbox contract and must not appear as newly pending notices.
UPDATE match_settlements
SET acknowledged_at = created_at
WHERE acknowledged_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_match_settlements_player_unacknowledged
    ON match_settlements(player_id, created_at DESC)
    WHERE acknowledged_at IS NULL;
