CREATE TABLE IF NOT EXISTS players (
    user_id uuid PRIMARY KEY,
    display_name varchar(80) NOT NULL,
    selected_class smallint NULL CHECK (selected_class BETWEEN 1 AND 3),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS external_identities (
    provider varchar(32) NOT NULL,
    external_subject varchar(160) NOT NULL,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (provider, external_subject),
    UNIQUE (provider, player_id)
);

CREATE TABLE IF NOT EXISTS player_sessions (
    session_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    token_hash bytea NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_player_sessions_player_id ON player_sessions(player_id);
CREATE INDEX IF NOT EXISTS ix_player_sessions_expires_at ON player_sessions(expires_at);
