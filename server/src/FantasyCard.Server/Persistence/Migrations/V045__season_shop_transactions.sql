ALTER TABLE season_definitions ADD COLUMN permanent_card_rule varchar(80)
    CHECK(permanent_card_rule IS NULL OR permanent_card_rule='season-gold-shop-v1');

CREATE TABLE season_shop_days (
    reset_key varchar(10) PRIMARY KEY,
    source_season_id varchar(80) NOT NULL REFERENCES season_definitions(season_id),
    config_version varchar(80) NOT NULL,
    config_sha256 char(64) NOT NULL,
    refreshes_used integer NOT NULL CHECK(refreshes_used>=0),
    products_json jsonb NOT NULL CHECK(jsonb_typeof(products_json)='array'),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

ALTER TABLE shop_purchases
    ADD COLUMN season_id varchar(80) REFERENCES season_definitions(season_id),
    ADD COLUMN config_version varchar(80),
    ADD COLUMN catalog_version varchar(80),
    ADD COLUMN quota_group varchar(80),
    ADD COLUMN response_json jsonb;

CREATE TABLE season_shop_refresh_receipts (
    player_id uuid NOT NULL REFERENCES players(user_id),
    request_id varchar(128) NOT NULL,
    request_hash char(64) NOT NULL,
    response_json jsonb NOT NULL,
    reset_key varchar(10) NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY(player_id,request_id)
);
