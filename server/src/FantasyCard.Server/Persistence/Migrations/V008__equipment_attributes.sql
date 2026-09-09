ALTER TABLE equipments
    ADD COLUMN IF NOT EXISTS element varchar(16) NULL,
    ADD COLUMN IF NOT EXISTS effect_affix varchar(24) NULL,
    ADD COLUMN IF NOT EXISTS secondary_trait varchar(32) NULL;

ALTER TABLE equipments
    DROP CONSTRAINT IF EXISTS ck_equipments_element,
    ADD CONSTRAINT ck_equipments_element
        CHECK (element IS NULL OR element IN ('Wood', 'Fire', 'Earth', 'Metal', 'Water')),
    DROP CONSTRAINT IF EXISTS ck_equipments_effect_affix,
    ADD CONSTRAINT ck_equipments_effect_affix
        CHECK (effect_affix IS NULL OR effect_affix IN ('Piercing', 'Bulwark', 'Vitality')),
    DROP CONSTRAINT IF EXISTS ck_equipments_secondary_trait,
    ADD CONSTRAINT ck_equipments_secondary_trait
        CHECK (secondary_trait IS NULL OR secondary_trait IN ('DrawInterval', 'ForcedEscape'));
