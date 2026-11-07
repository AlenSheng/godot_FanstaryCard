-- Legacy receipts and amounts keep their original columns and meanings.
-- New diamond prices never appear in a field named price_gold.
ALTER TABLE market_listings
    ADD COLUMN currency varchar(16) NOT NULL DEFAULT 'Gold' CHECK(currency IN ('Gold','Diamond')),
    ADD COLUMN price bigint,
    ADD COLUMN season_id varchar(80) REFERENCES season_definitions(season_id),
    ADD COLUMN config_version varchar(80),
    ADD COLUMN stats_version varchar(80),
    ADD COLUMN season_ends_at timestamptz,
    ADD COLUMN market_rule_version varchar(80),
    ADD COLUMN tax_basis_points integer,
    ADD COLUMN minimum_fee bigint,
    ADD COLUMN replaces_listing_id uuid REFERENCES market_listings(listing_id);

-- Old market rows may already hold real seasonal items. Their original asset
-- realm is retained; this does not reclassify their historical wallet entries.
UPDATE market_listings l SET season_id=e.season_id,config_version=d.config_version,
    stats_version=d.stats_version,season_ends_at=d.ends_at
FROM equipments e JOIN season_definitions d ON d.season_id=e.season_id
WHERE l.equipment_id=e.instance_id;

ALTER TABLE market_listings DROP CONSTRAINT market_listings_price_gold_check;
ALTER TABLE market_listings ADD CONSTRAINT ck_market_currency_price CHECK(
    (currency='Gold' AND price_gold>0 AND (price IS NULL OR price=price_gold))
    OR (currency='Diamond' AND price_gold=0 AND price IS NOT NULL AND price>0 AND season_id IS NOT NULL));
ALTER TABLE market_listings ADD CONSTRAINT ck_market_frozen_policy CHECK(
    market_rule_version IS NULL OR (market_rule_version='season-market-v1' AND season_id IS NOT NULL
        AND config_version IS NOT NULL AND stats_version IS NOT NULL AND season_ends_at IS NOT NULL
        AND tax_basis_points IS NOT NULL AND minimum_fee IS NOT NULL AND tax_basis_points=1000 AND minimum_fee=1 AND price IS NOT NULL
        AND expires_at=created_at+interval '48 hours'));

ALTER TABLE market_transactions
    ADD COLUMN currency varchar(16) NOT NULL DEFAULT 'Gold' CHECK(currency IN ('Gold','Diamond')),
    ADD COLUMN price bigint,
    ADD COLUMN fee bigint,
    ADD COLUMN seller_net bigint,
    ADD COLUMN season_id varchar(80) REFERENCES season_definitions(season_id),
    ADD COLUMN response_json jsonb;
ALTER TABLE market_transactions DROP CONSTRAINT market_transactions_price_gold_check;
ALTER TABLE market_transactions DROP CONSTRAINT market_transactions_fee_gold_check;
ALTER TABLE market_transactions ADD CONSTRAINT ck_market_transaction_currency CHECK(
    (currency='Gold' AND price_gold>0 AND fee_gold>=1 AND (price IS NULL OR price=price_gold)
        AND (fee IS NULL OR fee=fee_gold) AND (seller_net IS NULL OR seller_net=seller_net_gold))
    OR (currency='Diamond' AND price_gold=0 AND fee_gold=0 AND seller_net_gold=0 AND season_id IS NOT NULL
        AND price IS NOT NULL AND fee IS NOT NULL AND seller_net IS NOT NULL
        AND price>0 AND fee>=1 AND seller_net>=0 AND price=fee+seller_net));

-- A stable insertion order disambiguates several operations at the same
-- business-clock instant; currency-domain reconciliation does not order UUID4s.
ALTER TABLE economy_ledger ADD COLUMN ledger_sequence bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE inventory_movements ADD COLUMN source_kind varchar(32);

ALTER TABLE equipments DROP CONSTRAINT equipments_location_check;
ALTER TABLE equipments ADD CONSTRAINT equipments_location_check CHECK(location IN
    ('Inventory','Equipped','MarketListed','MarketReturnPending','PreparationLocked','InMatchEquipped','InMatchBackpack',
     'RelicPile','EnhanceMaterialConsumed','Recycled'));

CREATE TABLE market_return_holds(
    return_id uuid PRIMARY KEY,
    listing_id uuid NOT NULL UNIQUE REFERENCES market_listings(listing_id),
    equipment_id uuid NOT NULL REFERENCES equipments(instance_id),
    player_id uuid NOT NULL REFERENCES players(user_id),
    season_id varchar(80) REFERENCES season_definitions(season_id),
    state varchar(16) NOT NULL CHECK(state IN ('Pending','Claimed')),
    created_at timestamptz NOT NULL,
    claimed_at timestamptz,
    CHECK((state='Pending' AND claimed_at IS NULL) OR (state='Claimed' AND claimed_at IS NOT NULL))
);
CREATE UNIQUE INDEX ux_market_return_pending_item ON market_return_holds(equipment_id) WHERE state='Pending';
CREATE INDEX ix_market_returns_player ON market_return_holds(player_id,created_at) WHERE state='Pending';

CREATE TABLE market_action_receipts(
    player_id uuid NOT NULL REFERENCES players(user_id),
    action_kind varchar(32) NOT NULL,
    request_id varchar(80) NOT NULL,
    request_hash varchar(64) NOT NULL,
    response_json jsonb NOT NULL,
    season_id varchar(80) REFERENCES season_definitions(season_id),
    created_at timestamptz NOT NULL,
    PRIMARY KEY(player_id,action_kind,request_id)
);

CREATE INDEX ix_market_active_season_currency ON market_listings(season_id,currency,price,created_at,listing_id) WHERE status='Active';
