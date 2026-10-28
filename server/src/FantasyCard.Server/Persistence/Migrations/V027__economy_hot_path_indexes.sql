CREATE INDEX IF NOT EXISTS ix_shop_purchases_player_reset_product
    ON shop_purchases(player_id, reset_key, product_id);

CREATE INDEX IF NOT EXISTS ix_market_listings_active_seller
    ON market_listings(seller_id)
    WHERE status = 'Active';

CREATE INDEX IF NOT EXISTS ix_market_listings_active_expiry
    ON market_listings(expires_at)
    WHERE status = 'Active';
