CREATE TABLE IF NOT EXISTS account_deletion_requests (
    request_id uuid PRIMARY KEY,
    player_id uuid NULL REFERENCES players(user_id) ON DELETE SET NULL,
    status varchar(16) NOT NULL CHECK (status IN ('Requested', 'Cancelled', 'Completed')),
    requested_at timestamptz NOT NULL,
    scheduled_for timestamptz NOT NULL,
    completed_at timestamptz NULL,
    cancelled_at timestamptz NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_account_deletion_active_player
    ON account_deletion_requests(player_id) WHERE status = 'Requested' AND player_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_account_deletion_due
    ON account_deletion_requests(status, scheduled_for);
