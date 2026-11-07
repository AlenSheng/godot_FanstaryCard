-- Do not reconstruct historical application times from updated_at: replay can
-- legitimately change that field. Only a future Reserved -> Applied transition
-- records its original observation time.
ALTER TABLE reward_refresh_operations ADD COLUMN applied_at timestamptz;
ALTER TABLE reward_refresh_operations ADD CONSTRAINT ck_refresh_applied_observation_time
    CHECK (applied_at IS NULL OR state='Applied');
