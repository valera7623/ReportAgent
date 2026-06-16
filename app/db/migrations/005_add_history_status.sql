-- Task completion status and duration for dashboard / reports API

ALTER TABLE history ADD COLUMN status TEXT DEFAULT 'PENDING';
ALTER TABLE history ADD COLUMN duration_seconds REAL;

CREATE INDEX IF NOT EXISTS idx_history_task_id ON history(task_id);
CREATE INDEX IF NOT EXISTS idx_history_status ON history(status);
