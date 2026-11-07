-- Observation only. Existing actor/player and business identities remain the
-- authority; historical missing ownership legs are not inferred or backfilled.
ALTER TABLE inventory_movements ADD COLUMN from_owner_id uuid, ADD COLUMN to_owner_id uuid;
