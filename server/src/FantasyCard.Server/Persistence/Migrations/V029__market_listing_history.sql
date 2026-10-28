-- Historical listings must survive resale, cancellation and expiration.
-- Ownership/location transitions stay transactional; only one Active listing may hold an item.
ALTER TABLE market_listings DROP CONSTRAINT market_listings_equipment_id_key;
CREATE UNIQUE INDEX ux_market_listings_active_equipment
    ON market_listings(equipment_id) WHERE status = 'Active';
