CREATE TABLE red_equipment_weekly_quotas (
    week_key date PRIMARY KEY,
    red_dropped_this_week smallint NOT NULL CHECK (red_dropped_this_week IN (0, 1)),
    source varchar(32) NULL CHECK (source IN ('ChaosBoss', 'ShopChest')),
    player_id uuid NULL,
    match_id uuid NULL,
    equipment_id uuid NULL UNIQUE,
    claimed_at timestamptz NULL,
    CHECK (
        (red_dropped_this_week = 0 AND source IS NULL AND player_id IS NULL AND match_id IS NULL AND equipment_id IS NULL AND claimed_at IS NULL)
        OR
        (red_dropped_this_week = 1 AND source IS NOT NULL AND player_id IS NOT NULL AND equipment_id IS NOT NULL AND claimed_at IS NOT NULL)
    )
);

