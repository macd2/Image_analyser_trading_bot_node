-- Migration: 006_backtest_uuid_migration
-- Created: 2024-12-04
-- Description: Convert backtest tables from SERIAL integers to TEXT UUIDs
-- This ensures consistent ID handling and portable data

-- Step 1: Create new UUID columns
ALTER TABLE bt_runs ADD COLUMN IF NOT EXISTS new_id TEXT;
ALTER TABLE bt_run_images ADD COLUMN IF NOT EXISTS new_run_id TEXT;
ALTER TABLE bt_analyses ADD COLUMN IF NOT EXISTS new_run_id TEXT;
ALTER TABLE bt_trades ADD COLUMN IF NOT EXISTS new_run_id TEXT;
ALTER TABLE bt_summaries ADD COLUMN IF NOT EXISTS new_run_id TEXT;

-- Step 2: Generate UUIDs for existing bt_runs (format: bt_{timestamp}_{old_id})
UPDATE bt_runs SET new_id = 'bt_' || EXTRACT(EPOCH FROM COALESCE(started_at, NOW()))::BIGINT || '_' || id
WHERE new_id IS NULL;

-- Step 3: Update foreign key references
UPDATE bt_run_images ri SET new_run_id = r.new_id 
FROM bt_runs r WHERE ri.run_id = r.id AND ri.new_run_id IS NULL;

UPDATE bt_analyses a SET new_run_id = r.new_id 
FROM bt_runs r WHERE a.run_id = r.id AND a.new_run_id IS NULL;

UPDATE bt_trades t SET new_run_id = r.new_id 
FROM bt_runs r WHERE t.run_id = r.id AND t.new_run_id IS NULL;

UPDATE bt_summaries s SET new_run_id = r.new_id 
FROM bt_runs r WHERE s.run_id = r.id AND s.new_run_id IS NULL;

-- Step 4: Drop old constraints (CASCADE will handle FKs)
ALTER TABLE bt_run_images DROP CONSTRAINT IF EXISTS bt_run_images_run_id_fkey;
ALTER TABLE bt_analyses DROP CONSTRAINT IF EXISTS bt_analyses_run_id_fkey;
ALTER TABLE bt_trades DROP CONSTRAINT IF EXISTS bt_trades_run_id_fkey;
ALTER TABLE bt_summaries DROP CONSTRAINT IF EXISTS bt_summaries_run_id_fkey;

-- Step 5: Drop old columns and rename new ones
ALTER TABLE bt_run_images DROP COLUMN IF EXISTS run_id;
ALTER TABLE bt_run_images RENAME COLUMN new_run_id TO run_id;

ALTER TABLE bt_analyses DROP COLUMN IF EXISTS run_id;
ALTER TABLE bt_analyses RENAME COLUMN new_run_id TO run_id;

ALTER TABLE bt_trades DROP COLUMN IF EXISTS run_id;
ALTER TABLE bt_trades RENAME COLUMN new_run_id TO run_id;

ALTER TABLE bt_summaries DROP COLUMN IF EXISTS run_id;
ALTER TABLE bt_summaries RENAME COLUMN new_run_id TO run_id;

-- For bt_runs, we need to handle the primary key
ALTER TABLE bt_runs DROP CONSTRAINT IF EXISTS bt_runs_pkey;
ALTER TABLE bt_runs DROP COLUMN IF EXISTS id;
ALTER TABLE bt_runs RENAME COLUMN new_id TO id;
ALTER TABLE bt_runs ADD PRIMARY KEY (id);

-- Step 6: Recreate foreign keys with TEXT type
ALTER TABLE bt_run_images 
  ADD CONSTRAINT bt_run_images_run_id_fkey 
  FOREIGN KEY (run_id) REFERENCES bt_runs(id) ON DELETE CASCADE;

ALTER TABLE bt_analyses 
  ADD CONSTRAINT bt_analyses_run_id_fkey 
  FOREIGN KEY (run_id) REFERENCES bt_runs(id) ON DELETE CASCADE;

ALTER TABLE bt_trades 
  ADD CONSTRAINT bt_trades_run_id_fkey 
  FOREIGN KEY (run_id) REFERENCES bt_runs(id) ON DELETE CASCADE;

ALTER TABLE bt_summaries 
  ADD CONSTRAINT bt_summaries_run_id_fkey 
  FOREIGN KEY (run_id) REFERENCES bt_runs(id) ON DELETE CASCADE;

-- Step 7: Update unique constraints
ALTER TABLE bt_run_images DROP CONSTRAINT IF EXISTS bt_run_images_run_id_image_path_key;
ALTER TABLE bt_run_images ADD CONSTRAINT bt_run_images_run_id_image_path_key UNIQUE(run_id, image_path);

ALTER TABLE bt_analyses DROP CONSTRAINT IF EXISTS bt_analyses_run_id_prompt_name_image_path_key;
ALTER TABLE bt_analyses ADD CONSTRAINT bt_analyses_run_id_prompt_name_image_path_key UNIQUE(run_id, prompt_name, image_path);

ALTER TABLE bt_trades DROP CONSTRAINT IF EXISTS bt_trades_run_id_prompt_name_image_path_key;
ALTER TABLE bt_trades ADD CONSTRAINT bt_trades_run_id_prompt_name_image_path_key UNIQUE(run_id, prompt_name, image_path);

ALTER TABLE bt_summaries DROP CONSTRAINT IF EXISTS bt_summaries_run_id_prompt_name_key;
ALTER TABLE bt_summaries ADD CONSTRAINT bt_summaries_run_id_prompt_name_key UNIQUE(run_id, prompt_name);

-- Record migration
INSERT INTO app_migrations (name) VALUES ('006_backtest_uuid_migration') ON CONFLICT DO NOTHING;

