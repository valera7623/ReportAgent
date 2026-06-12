-- Add request_type to history for voice vs API tracking

ALTER TABLE history ADD COLUMN request_type TEXT DEFAULT 'api';

CREATE INDEX IF NOT EXISTS idx_history_request_type ON history(request_type);
