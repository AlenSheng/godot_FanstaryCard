ALTER TABLE equipments
    ADD COLUMN unique_affix varchar(24),
    ADD COLUMN unique_element varchar(16),
    ADD CONSTRAINT ck_equipment_unique_affix CHECK (
        unique_affix IS NULL OR quality='Red' AND unique_affix IN ('Inferno','RapidDraw','ChainDraw','Scavenge','GoldenCicada')),
    ADD CONSTRAINT ck_equipment_golden_cicada_slot CHECK (unique_affix IS DISTINCT FROM 'GoldenCicada' OR slot='Feet'),
    ADD CONSTRAINT ck_equipment_unique_element CHECK (unique_element IS NULL OR
        unique_affix IS NOT NULL AND unique_affix='Inferno' AND unique_element IN ('Fire','Wood','Earth','Metal','Water')
        AND (season_id IS NULL OR season_id='legacy-gdd-0.70' OR unique_element=element));

-- Existing equipment and history are retained without inventing a unique affix.
