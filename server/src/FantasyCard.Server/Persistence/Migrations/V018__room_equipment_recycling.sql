ALTER TABLE equipments DROP CONSTRAINT equipments_location_check;
ALTER TABLE equipments ADD CONSTRAINT equipments_location_check CHECK (
    location IN ('Inventory', 'Equipped', 'MarketListed', 'PreparationLocked',
        'InMatchEquipped', 'InMatchBackpack', 'RelicPile', 'EnhanceMaterialConsumed', 'Recycled'));
