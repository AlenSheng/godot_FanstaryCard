-- Permanent business receipt: a retry can acknowledge the original discard after season end.
CREATE TABLE inventory_discard_batches (
    batch_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    request_id varchar(80) NOT NULL,
    request_hash varchar(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    season_id varchar(80) REFERENCES season_definitions(season_id),
    before_items jsonb NOT NULL CHECK (jsonb_typeof(before_items) = 'array'),
    response_json jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (player_id, request_id)
);
