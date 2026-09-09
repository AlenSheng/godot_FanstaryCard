CREATE TABLE IF NOT EXISTS reward_refresh_operations (
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    request_id varchar(80) NOT NULL,
    match_id uuid NOT NULL REFERENCES matches(match_id),
    room_id uuid NOT NULL,
    expected_revision bigint NOT NULL CHECK (expected_revision >= 0),
    account_gold bigint NOT NULL CHECK (account_gold > 0),
    state varchar(16) NOT NULL CHECK (state IN ('Reserved', 'Applied', 'Refunded')),
    response_json jsonb,
    room_revision bigint,
    recover_after timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (player_id, request_id)
);

CREATE INDEX IF NOT EXISTS ix_reward_refresh_operations_recovery
    ON reward_refresh_operations(state, recover_after)
    WHERE state = 'Reserved';
