-- Add default_output_format to user preferences (Step 4: multi-format output)
ALTER TABLE preferences ADD COLUMN default_output_format TEXT DEFAULT 'pdf';

-- Track output format in request history
ALTER TABLE history ADD COLUMN output_format TEXT DEFAULT 'pdf';
CREATE INDEX IF NOT EXISTS idx_history_output_format ON history(output_format);
