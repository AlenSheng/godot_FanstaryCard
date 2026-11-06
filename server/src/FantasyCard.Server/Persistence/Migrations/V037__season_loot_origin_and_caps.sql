ALTER TABLE equipments
    ADD COLUMN source_loot_json jsonb,
    ADD CONSTRAINT ck_equipment_loot_origin_object CHECK (source_loot_json IS NULL OR jsonb_typeof(source_loot_json)='object'),
    ADD CONSTRAINT ck_equipment_generated_difficulty_quality CHECK (
        season_id IS NULL OR season_id='legacy-gdd-0.70' OR generated_difficulty>=2
        OR (generated_difficulty=0 AND quality IN ('White','Green','Blue'))
        OR (generated_difficulty=1 AND quality IN ('White','Green','Blue','Purple'))
    ) NOT VALID;

-- NOT VALID preserves historical originals for audit. New rows and updates still
-- enforce the cap for every source, including future shop/activity/crafting writes.
