CREATE TABLE IF NOT EXISTS shop_rotations (
    reset_key varchar(32) NOT NULL,
    product_id varchar(80) NOT NULL,
    kind varchar(32) NOT NULL,
    payload_json jsonb NOT NULL,
    price_gold bigint NOT NULL CHECK (price_gold > 0),
    limit_count integer NOT NULL CHECK (limit_count > 0),
    PRIMARY KEY (reset_key, product_id)
);

CREATE TABLE IF NOT EXISTS shop_purchases (
    purchase_id uuid PRIMARY KEY,
    player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    reset_key varchar(32) NOT NULL,
    product_id varchar(80) NOT NULL,
    request_id varchar(80) NOT NULL,
    request_hash varchar(64) NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    price_gold bigint NOT NULL CHECK (price_gold > 0),
    granted_json jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (player_id, request_id)
);

CREATE TABLE IF NOT EXISTS market_listings (
    listing_id uuid PRIMARY KEY,
    seller_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    equipment_id uuid NOT NULL UNIQUE REFERENCES equipments(instance_id),
    price_gold bigint NOT NULL CHECK (price_gold > 0),
    status varchar(16) NOT NULL CHECK (status IN ('Active', 'Sold', 'Cancelled', 'Expired')),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    request_id varchar(80),
    request_hash varchar(64),
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_market_listings_active
    ON market_listings(status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS ux_market_listings_request
    ON market_listings(seller_id, request_id) WHERE request_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS market_transactions (
    transaction_id uuid PRIMARY KEY,
    listing_id uuid NOT NULL REFERENCES market_listings(listing_id),
    buyer_id uuid NOT NULL REFERENCES players(user_id),
    seller_id uuid NOT NULL REFERENCES players(user_id),
    price_gold bigint NOT NULL CHECK (price_gold > 0),
    fee_gold bigint NOT NULL CHECK (fee_gold >= 1),
    seller_net_gold bigint NOT NULL CHECK (seller_net_gold >= 0),
    request_id varchar(80),
    request_hash varchar(64),
    completed_at timestamptz NOT NULL,
    UNIQUE (listing_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_market_transactions_request
    ON market_transactions(buyer_id, request_id) WHERE request_id IS NOT NULL;
