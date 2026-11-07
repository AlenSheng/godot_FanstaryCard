-- Observation only. Existing durable business actions remain the idempotency
-- authority; old rows stay unknown and are never reconstructed from live pity.
ALTER TABLE season_equipment_actions ADD COLUMN telemetry_json jsonb;
ALTER TABLE season_equipment_actions ADD CONSTRAINT ck_equipment_action_telemetry_object
    CHECK (telemetry_json IS NULL OR jsonb_typeof(telemetry_json)='object');
