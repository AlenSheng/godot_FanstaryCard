ALTER TABLE matches
    DROP CONSTRAINT IF EXISTS matches_status_check;

ALTER TABLE matches
    ADD CONSTRAINT matches_status_check
    CHECK (status IN ('Starting', 'Launching', 'Running', 'Completed', 'Aborted'));

ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS ready_deadline timestamptz;

UPDATE matches
SET ready_deadline = created_at + interval '15 seconds'
WHERE status = 'Starting' AND ready_deadline IS NULL;

ALTER TABLE matches
    ADD CONSTRAINT matches_starting_ready_deadline_check
    CHECK (status <> 'Starting' OR ready_deadline IS NOT NULL);

CREATE INDEX IF NOT EXISTS ix_matches_ready_phase
    ON matches(status, ready_deadline)
    WHERE status IN ('Starting', 'Launching');
