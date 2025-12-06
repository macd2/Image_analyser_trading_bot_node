-- Migration: 007_tournament_uuid_migration
-- Created: 2024-12-05
-- Description: Convert tournament tables from SERIAL integers to TEXT UUIDs
-- Affects: tourn_tournaments, tourn_phases, tourn_prompts, tourn_phase_results, 
--          tourn_phase_images, tourn_analyses

-- Step 1: Add new UUID columns to all tournament tables
ALTER TABLE tourn_tournaments ADD COLUMN IF NOT EXISTS new_id TEXT;
ALTER TABLE tourn_phases ADD COLUMN IF NOT EXISTS new_id TEXT;
ALTER TABLE tourn_phases ADD COLUMN IF NOT EXISTS new_tournament_id TEXT;
ALTER TABLE tourn_prompts ADD COLUMN IF NOT EXISTS new_id TEXT;
ALTER TABLE tourn_prompts ADD COLUMN IF NOT EXISTS new_tournament_id TEXT;
ALTER TABLE tourn_phase_results ADD COLUMN IF NOT EXISTS new_phase_id TEXT;
ALTER TABLE tourn_phase_results ADD COLUMN IF NOT EXISTS new_tournament_prompt_id TEXT;
ALTER TABLE tourn_phase_images ADD COLUMN IF NOT EXISTS new_phase_id TEXT;
ALTER TABLE tourn_analyses ADD COLUMN IF NOT EXISTS new_phase_id TEXT;
ALTER TABLE tourn_analyses ADD COLUMN IF NOT EXISTS new_tournament_prompt_id TEXT;
ALTER TABLE tourn_analyses ADD COLUMN IF NOT EXISTS new_phase_image_id TEXT;

-- Step 2: Generate UUIDs for tourn_tournaments
UPDATE tourn_tournaments SET new_id = 'tourn_' || id || '_' || EXTRACT(EPOCH FROM COALESCE(started_at, created_at, NOW()))::BIGINT
WHERE new_id IS NULL;

-- Step 3: Generate UUIDs for tourn_phases  
UPDATE tourn_phases SET new_id = 'phase_' || tournament_id || '_' || phase_number
WHERE new_id IS NULL;

-- Step 4: Generate UUIDs for tourn_prompts
UPDATE tourn_prompts SET new_id = 'tprompt_' || tournament_id || '_' || REPLACE(prompt_name, ' ', '_')
WHERE new_id IS NULL;

-- Step 5: Generate UUIDs for tourn_phase_images
ALTER TABLE tourn_phase_images ADD COLUMN IF NOT EXISTS new_id TEXT;
UPDATE tourn_phase_images SET new_id = 'pimg_' || phase_id || '_' || selection_order
WHERE new_id IS NULL;

-- Step 6: Update FK references in tourn_phases
UPDATE tourn_phases p SET new_tournament_id = t.new_id
FROM tourn_tournaments t WHERE p.tournament_id = t.id AND p.new_tournament_id IS NULL;

-- Step 7: Update FK references in tourn_prompts
UPDATE tourn_prompts tp SET new_tournament_id = t.new_id
FROM tourn_tournaments t WHERE tp.tournament_id = t.id AND tp.new_tournament_id IS NULL;

-- Step 8: Update FK references in tourn_phase_results
UPDATE tourn_phase_results pr SET new_phase_id = p.new_id
FROM tourn_phases p WHERE pr.phase_id = p.id AND pr.new_phase_id IS NULL;

UPDATE tourn_phase_results pr SET new_tournament_prompt_id = tp.new_id
FROM tourn_prompts tp WHERE pr.tournament_prompt_id = tp.id AND pr.new_tournament_prompt_id IS NULL;

-- Step 9: Update FK references in tourn_phase_images
UPDATE tourn_phase_images pi SET new_phase_id = p.new_id
FROM tourn_phases p WHERE pi.phase_id = p.id AND pi.new_phase_id IS NULL;

-- Step 10: Update FK references in tourn_analyses
UPDATE tourn_analyses a SET new_phase_id = p.new_id
FROM tourn_phases p WHERE a.phase_id = p.id AND a.new_phase_id IS NULL;

UPDATE tourn_analyses a SET new_tournament_prompt_id = tp.new_id
FROM tourn_prompts tp WHERE a.tournament_prompt_id = tp.id AND a.new_tournament_prompt_id IS NULL;

UPDATE tourn_analyses a SET new_phase_image_id = pi.new_id
FROM tourn_phase_images pi WHERE a.phase_image_id = pi.id AND a.new_phase_image_id IS NULL;

-- Step 11: Drop old FK constraints
ALTER TABLE tourn_phases DROP CONSTRAINT IF EXISTS tourn_phases_tournament_id_fkey;
ALTER TABLE tourn_prompts DROP CONSTRAINT IF EXISTS tourn_prompts_tournament_id_fkey;
ALTER TABLE tourn_phase_results DROP CONSTRAINT IF EXISTS tourn_phase_results_phase_id_fkey;
ALTER TABLE tourn_phase_results DROP CONSTRAINT IF EXISTS tourn_phase_results_tournament_prompt_id_fkey;
ALTER TABLE tourn_phase_images DROP CONSTRAINT IF EXISTS tourn_phase_images_phase_id_fkey;
ALTER TABLE tourn_analyses DROP CONSTRAINT IF EXISTS tourn_analyses_phase_id_fkey;
ALTER TABLE tourn_analyses DROP CONSTRAINT IF EXISTS tourn_analyses_tournament_prompt_id_fkey;
ALTER TABLE tourn_analyses DROP CONSTRAINT IF EXISTS tourn_analyses_phase_image_id_fkey;

-- Step 12: Replace columns (drop old, rename new)
-- tourn_tournaments
ALTER TABLE tourn_tournaments DROP CONSTRAINT IF EXISTS tourn_tournaments_pkey;
ALTER TABLE tourn_tournaments DROP COLUMN IF EXISTS id;
ALTER TABLE tourn_tournaments RENAME COLUMN new_id TO id;
ALTER TABLE tourn_tournaments ADD PRIMARY KEY (id);

-- tourn_phases
ALTER TABLE tourn_phases DROP CONSTRAINT IF EXISTS tourn_phases_pkey;
ALTER TABLE tourn_phases DROP COLUMN IF EXISTS id;
ALTER TABLE tourn_phases RENAME COLUMN new_id TO id;
ALTER TABLE tourn_phases DROP COLUMN IF EXISTS tournament_id;
ALTER TABLE tourn_phases RENAME COLUMN new_tournament_id TO tournament_id;
ALTER TABLE tourn_phases ADD PRIMARY KEY (id);

-- tourn_prompts
ALTER TABLE tourn_prompts DROP CONSTRAINT IF EXISTS tourn_prompts_pkey;
ALTER TABLE tourn_prompts DROP COLUMN IF EXISTS id;
ALTER TABLE tourn_prompts RENAME COLUMN new_id TO id;
ALTER TABLE tourn_prompts DROP COLUMN IF EXISTS tournament_id;
ALTER TABLE tourn_prompts RENAME COLUMN new_tournament_id TO tournament_id;
ALTER TABLE tourn_prompts ADD PRIMARY KEY (id);

-- tourn_phase_results
ALTER TABLE tourn_phase_results DROP COLUMN IF EXISTS phase_id;
ALTER TABLE tourn_phase_results RENAME COLUMN new_phase_id TO phase_id;
ALTER TABLE tourn_phase_results DROP COLUMN IF EXISTS tournament_prompt_id;
ALTER TABLE tourn_phase_results RENAME COLUMN new_tournament_prompt_id TO tournament_prompt_id;

-- tourn_phase_images
ALTER TABLE tourn_phase_images DROP CONSTRAINT IF EXISTS tourn_phase_images_pkey;
ALTER TABLE tourn_phase_images DROP COLUMN IF EXISTS id;
ALTER TABLE tourn_phase_images RENAME COLUMN new_id TO id;
ALTER TABLE tourn_phase_images DROP COLUMN IF EXISTS phase_id;
ALTER TABLE tourn_phase_images RENAME COLUMN new_phase_id TO phase_id;
ALTER TABLE tourn_phase_images ADD PRIMARY KEY (id);

-- tourn_analyses
ALTER TABLE tourn_analyses DROP COLUMN IF EXISTS phase_id;
ALTER TABLE tourn_analyses RENAME COLUMN new_phase_id TO phase_id;
ALTER TABLE tourn_analyses DROP COLUMN IF EXISTS tournament_prompt_id;
ALTER TABLE tourn_analyses RENAME COLUMN new_tournament_prompt_id TO tournament_prompt_id;
ALTER TABLE tourn_analyses DROP COLUMN IF EXISTS phase_image_id;
ALTER TABLE tourn_analyses RENAME COLUMN new_phase_image_id TO phase_image_id;

-- Step 13: Recreate FK constraints with TEXT types
ALTER TABLE tourn_phases ADD CONSTRAINT tourn_phases_tournament_id_fkey 
  FOREIGN KEY (tournament_id) REFERENCES tourn_tournaments(id) ON DELETE CASCADE;

ALTER TABLE tourn_prompts ADD CONSTRAINT tourn_prompts_tournament_id_fkey 
  FOREIGN KEY (tournament_id) REFERENCES tourn_tournaments(id) ON DELETE CASCADE;

ALTER TABLE tourn_phase_results ADD CONSTRAINT tourn_phase_results_phase_id_fkey 
  FOREIGN KEY (phase_id) REFERENCES tourn_phases(id) ON DELETE CASCADE;

ALTER TABLE tourn_phase_results ADD CONSTRAINT tourn_phase_results_tournament_prompt_id_fkey 
  FOREIGN KEY (tournament_prompt_id) REFERENCES tourn_prompts(id) ON DELETE CASCADE;

ALTER TABLE tourn_phase_images ADD CONSTRAINT tourn_phase_images_phase_id_fkey 
  FOREIGN KEY (phase_id) REFERENCES tourn_phases(id) ON DELETE CASCADE;

ALTER TABLE tourn_analyses ADD CONSTRAINT tourn_analyses_phase_id_fkey 
  FOREIGN KEY (phase_id) REFERENCES tourn_phases(id) ON DELETE CASCADE;

ALTER TABLE tourn_analyses ADD CONSTRAINT tourn_analyses_tournament_prompt_id_fkey 
  FOREIGN KEY (tournament_prompt_id) REFERENCES tourn_prompts(id) ON DELETE CASCADE;

ALTER TABLE tourn_analyses ADD CONSTRAINT tourn_analyses_phase_image_id_fkey 
  FOREIGN KEY (phase_image_id) REFERENCES tourn_phase_images(id) ON DELETE CASCADE;

-- Record migration
INSERT INTO app_migrations (name) VALUES ('007_tournament_uuid_migration') ON CONFLICT DO NOTHING;

