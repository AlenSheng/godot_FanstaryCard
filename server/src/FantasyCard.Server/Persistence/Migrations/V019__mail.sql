CREATE TABLE IF NOT EXISTS player_mail (
    mail_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    title varchar(120) NOT NULL,
    body text NOT NULL,
    attachments jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_read boolean NOT NULL DEFAULT false,
    claimed_at timestamptz NULL,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS ix_player_mail_player_created ON player_mail(player_id, created_at DESC);
