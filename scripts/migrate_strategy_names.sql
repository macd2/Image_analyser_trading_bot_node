-- ============================================================================
-- STRATEGY NAME MIGRATION SCRIPT - WITH DRY RUN SUPPORT
-- ============================================================================
-- Purpose: Migrate old strategy names to new names across all tables
-- 
-- Mapping:
--   PromptStrategy → AiImageAnalyzer
--   CointegrationAnalysisModule → CointegrationSpreadTrader
--
-- Usage:
--   DRY RUN (preview changes):
--     psql $DATABASE_URL -f scripts/migrate_strategy_names.sql
--   
--   ACTUAL MIGRATION (apply changes):
--     psql $DATABASE_URL -v apply=true -f scripts/migrate_strategy_names.sql
-- ============================================================================

-- Set default for apply variable (dry run by default)
\set apply false

-- ============================================================================
-- PHASE 1: VALIDATE DATA BEFORE MIGRATION
-- ============================================================================
\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo 'PHASE 1: VALIDATION - Current state before migration'
\echo '═══════════════════════════════════════════════════════════════════════════════'

\echo ''
\echo '--- TRADES TABLE ---'
SELECT 
  strategy_name,
  strategy_type,
  COUNT(*) as count
FROM trades
GROUP BY strategy_name, strategy_type
ORDER BY strategy_name;

\echo ''
\echo '--- RECOMMENDATIONS TABLE ---'
SELECT 
  COALESCE(strategy_name, 'NULL') as strategy_name,
  COALESCE(strategy_type, 'NULL') as strategy_type,
  COUNT(*) as count
FROM recommendations
GROUP BY strategy_name, strategy_type
ORDER BY strategy_name;

\echo ''
\echo '--- INSTANCES TABLE ---'
SELECT 
  name,
  COALESCE(settings->>'strategy', 'NULL') as strategy
FROM instances
ORDER BY name;

-- ============================================================================
-- PHASE 2: DRY RUN - SHOW WHAT WILL BE CHANGED
-- ============================================================================
\echo ''
\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo 'PHASE 2: DRY RUN - Changes that will be applied'
\echo '═══════════════════════════════════════════════════════════════════════════════'

\echo ''
\echo '--- TRADES: PromptStrategy → AiImageAnalyzer ---'
SELECT 
  'TRADES' as table_name,
  'PromptStrategy' as old_value,
  'AiImageAnalyzer' as new_value,
  COUNT(*) as rows_affected
FROM trades
WHERE strategy_name = 'PromptStrategy';

\echo ''
\echo '--- TRADES: CointegrationAnalysisModule → CointegrationSpreadTrader ---'
SELECT 
  'TRADES' as table_name,
  'CointegrationAnalysisModule' as old_value,
  'CointegrationSpreadTrader' as new_value,
  COUNT(*) as rows_affected
FROM trades
WHERE strategy_name = 'CointegrationAnalysisModule';

\echo ''
\echo '--- RECOMMENDATIONS: PromptStrategy → AiImageAnalyzer ---'
SELECT 
  'RECOMMENDATIONS' as table_name,
  'PromptStrategy' as old_value,
  'AiImageAnalyzer' as new_value,
  COUNT(*) as rows_affected
FROM recommendations
WHERE strategy_name = 'PromptStrategy';

\echo ''
\echo '--- RECOMMENDATIONS: CointegrationAnalysisModule → CointegrationSpreadTrader ---'
SELECT 
  'RECOMMENDATIONS' as table_name,
  'CointegrationAnalysisModule' as old_value,
  'CointegrationSpreadTrader' as new_value,
  COUNT(*) as rows_affected
FROM recommendations
WHERE strategy_name = 'CointegrationAnalysisModule';

\echo ''
\echo '--- RECOMMENDATIONS: NULL strategy_name (will be populated from related trades) ---'
SELECT 
  'RECOMMENDATIONS' as table_name,
  'NULL' as old_value,
  'POPULATED FROM TRADES' as new_value,
  COUNT(*) as rows_affected
FROM recommendations
WHERE strategy_name IS NULL OR strategy_name = '';

\echo ''
\echo '--- INSTANCES: Playboy1 (NULL strategy - needs manual review) ---'
SELECT 
  'INSTANCES' as table_name,
  name,
  COALESCE(settings->>'strategy', 'NULL') as current_strategy,
  'REQUIRES MANUAL REVIEW' as action
FROM instances
WHERE settings->>'strategy' IS NULL OR settings->>'strategy' = '';

