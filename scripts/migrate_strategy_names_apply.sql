-- ============================================================================
-- STRATEGY NAME MIGRATION - APPLY CHANGES
-- ============================================================================
-- This script applies the actual migrations
-- Run ONLY after reviewing the dry-run output
-- ============================================================================

BEGIN;

\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo 'APPLYING MIGRATIONS...'
\echo '═══════════════════════════════════════════════════════════════════════════════'

-- ============================================================================
-- MIGRATION 1: TRADES TABLE
-- ============================================================================
\echo ''
\echo '--- MIGRATION 1: TRADES TABLE ---'

\echo 'Updating: PromptStrategy → AiImageAnalyzer'
UPDATE trades 
SET strategy_name = 'AiImageAnalyzer' 
WHERE strategy_name = 'PromptStrategy';
\echo 'Rows affected:' :ROWCOUNT

\echo 'Updating: CointegrationAnalysisModule → CointegrationSpreadTrader'
UPDATE trades 
SET strategy_name = 'CointegrationSpreadTrader' 
WHERE strategy_name = 'CointegrationAnalysisModule';
\echo 'Rows affected:' :ROWCOUNT

-- ============================================================================
-- MIGRATION 2: RECOMMENDATIONS TABLE - Name changes
-- ============================================================================
\echo ''
\echo '--- MIGRATION 2: RECOMMENDATIONS TABLE (Name changes) ---'

\echo 'Updating: PromptStrategy → AiImageAnalyzer'
UPDATE recommendations 
SET strategy_name = 'AiImageAnalyzer' 
WHERE strategy_name = 'PromptStrategy';
\echo 'Rows affected:' :ROWCOUNT

\echo 'Updating: CointegrationAnalysisModule → CointegrationSpreadTrader'
UPDATE recommendations 
SET strategy_name = 'CointegrationSpreadTrader' 
WHERE strategy_name = 'CointegrationAnalysisModule';
\echo 'Rows affected:' :ROWCOUNT

-- ============================================================================
-- MIGRATION 3: RECOMMENDATIONS TABLE - Populate NULL strategy_name
-- ============================================================================
\echo ''
\echo '--- MIGRATION 3: RECOMMENDATIONS TABLE (Populate NULL strategy_name) ---'

\echo 'Populating NULL strategy_name from related trades...'
UPDATE recommendations r
SET 
  strategy_name = t.strategy_name,
  strategy_type = t.strategy_type
FROM trades t
WHERE (r.strategy_name IS NULL OR r.strategy_name = '')
  AND r.symbol = t.symbol
  AND r.created_at::date = t.created_at::date
  AND t.strategy_name IS NOT NULL;
\echo 'Rows affected:' :ROWCOUNT

-- ============================================================================
-- VALIDATION: Check for remaining NULL values
-- ============================================================================
\echo ''
\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo 'VALIDATION: Checking for remaining issues'
\echo '═══════════════════════════════════════════════════════════════════════════════'

\echo ''
\echo '--- Remaining NULL strategy_name in RECOMMENDATIONS ---'
SELECT COUNT(*) as remaining_null_count
FROM recommendations
WHERE strategy_name IS NULL OR strategy_name = '';

\echo ''
\echo '--- Remaining old names in TRADES ---'
SELECT COUNT(*) as remaining_old_names
FROM trades
WHERE strategy_name IN ('PromptStrategy', 'CointegrationAnalysisModule');

\echo ''
\echo '--- Remaining old names in RECOMMENDATIONS ---'
SELECT COUNT(*) as remaining_old_names
FROM recommendations
WHERE strategy_name IN ('PromptStrategy', 'CointegrationAnalysisModule');

-- ============================================================================
-- FINAL STATE VERIFICATION
-- ============================================================================
\echo ''
\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo 'FINAL STATE: After migration'
\echo '═══════════════════════════════════════════════════════════════════════════════'

\echo ''
\echo '--- TRADES TABLE (Final) ---'
SELECT 
  strategy_name,
  strategy_type,
  COUNT(*) as count
FROM trades
GROUP BY strategy_name, strategy_type
ORDER BY strategy_name;

\echo ''
\echo '--- RECOMMENDATIONS TABLE (Final) ---'
SELECT 
  COALESCE(strategy_name, 'NULL') as strategy_name,
  COALESCE(strategy_type, 'NULL') as strategy_type,
  COUNT(*) as count
FROM recommendations
GROUP BY strategy_name, strategy_type
ORDER BY strategy_name;

COMMIT;

\echo ''
\echo '═══════════════════════════════════════════════════════════════════════════════'
\echo 'MIGRATION COMPLETE'
\echo '═══════════════════════════════════════════════════════════════════════════════'

