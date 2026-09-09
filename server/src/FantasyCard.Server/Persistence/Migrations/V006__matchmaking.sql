CREATE TABLE IF NOT EXISTS matches (
    match_id uuid PRIMARY KEY,
    room_id uuid NOT NULL UNIQUE,
    mode varchar(32) NOT NULL CHECK (mode = 'ChaosRealm'),
    difficulty varchar(16) NOT NULL CHECK (difficulty = 'Standard'),
    seed integer NOT NULL,
    config_version varchar(80) NOT NULL,
    status varchar(24) NOT NULL CHECK (status IN ('Starting', 'Running', 'Completed', 'Aborted')),
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS match_tickets (
    ticket_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    preparation_id uuid NOT NULL REFERENCES preparations(preparation_id),
    request_id varchar(80) NOT NULL,
    status varchar(16) NOT NULL CHECK (status IN ('Queued', 'Cancelled', 'Matched')),
    queued_at timestamptz NOT NULL,
    matched_at timestamptz,
    UNIQUE (player_id, request_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_match_tickets_active_player
    ON match_tickets(player_id) WHERE status = 'Queued';

CREATE INDEX IF NOT EXISTS ix_match_tickets_queue
    ON match_tickets(status, queued_at);

CREATE TABLE IF NOT EXISTS match_players (
    match_id uuid NOT NULL REFERENCES matches(match_id) ON DELETE CASCADE,
    player_id uuid NOT NULL,
    preparation_id uuid,
    is_bot boolean NOT NULL DEFAULT false,
    state varchar(24) NOT NULL DEFAULT 'Assigned',
    settled_at timestamptz,
    settlement_id uuid,
    PRIMARY KEY (match_id, player_id)
);
