-- Settings table for persisting instance-specific configuration
-- instance_id: unique identifier for the instance/page (e.g., 'tournament', 'backtest')
-- settings: JSON object containing all settings for that instance

CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    instance_id TEXT NOT NULL UNIQUE,
    settings TEXT NOT NULL DEFAULT '{}',  -- JSON stored as TEXT (SQLite doesn't have native JSONB)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast lookup by instance_id
CREATE INDEX IF NOT EXISTS idx_settings_instance_id ON settings(instance_id);

-- Trigger to auto-update updated_at
CREATE TRIGGER IF NOT EXISTS settings_updated_at 
    AFTER UPDATE ON settings
    FOR EACH ROW
BEGIN
    UPDATE settings SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

