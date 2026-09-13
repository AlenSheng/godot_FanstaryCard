CREATE TABLE IF NOT EXISTS mail_messages (
    mail_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    title varchar(160) NOT NULL,
    body text NOT NULL,
    sender varchar(80) NOT NULL DEFAULT 'System',
    attachments_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    sent_at timestamptz NOT NULL,
    expires_at timestamptz NULL,
    read_at timestamptz NULL,
    claimed_at timestamptz NULL,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    CHECK (jsonb_typeof(attachments_json) = 'array')
);

CREATE INDEX IF NOT EXISTS ix_mail_messages_player_sent
    ON mail_messages(player_id, sent_at DESC);

CREATE INDEX IF NOT EXISTS ix_mail_messages_player_unread
    ON mail_messages(player_id) WHERE read_at IS NULL;
