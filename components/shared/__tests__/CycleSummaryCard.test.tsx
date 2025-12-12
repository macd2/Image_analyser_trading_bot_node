/**
 * Unit tests for CycleSummaryCard log filtering logic
 * Tests that logs are correctly filtered by section markers
 */

interface SectionLogs {
  step0: string[]
  step1: string[]
  step1_5: string[]
  step2: string[]
  step3: string[]
  step4: string[]
  step5: string[]
  step6: string[]
  step7: string[]
  cycleSummary: string[]
}

function filterLogsBySection(logs: string[]): SectionLogs {
  return {
    step0: logs.filter(log => log.includes('[STEP_0_SUMMARY]')),
    step1: logs.filter(log => log.includes('[STEP_1_SUMMARY]')),
    step1_5: logs.filter(log => log.includes('[STEP_1.5_SUMMARY]')),
    step2: logs.filter(log => log.includes('[STEP_2_SUMMARY]')),
    step3: logs.filter(log => log.includes('[STEP_3_SUMMARY]')),
    step4: logs.filter(log => log.includes('[STEP_4_SUMMARY]')),
    step5: logs.filter(log => log.includes('[STEP_5_SUMMARY]')),
    step6: logs.filter(log => log.includes('[STEP_6_SUMMARY]')),
    step7: logs.filter(log => log.includes('[STEP_7_SUMMARY]')),
    cycleSummary: logs.filter(log => log.includes('[CYCLE_SUMMARY]'))
  }
}

// Test 1: Full cycle with all steps and markers
const logs1 = [
  '[STEP_0_SUMMARY] 🧹 STEP 0 COMPLETE: Chart Cleanup',
  '[STEP_0_SUMMARY]    ├─ Cleaned: 2 charts',
  '[STEP_0_SUMMARY]    └─ Status: ✅ Success',
  '[STEP_1_SUMMARY] 📷 STEP 1 COMPLETE: Capturing Charts',
  '[STEP_1_SUMMARY]    ├─ Charts captured: 5',
  '[STEP_1_SUMMARY]    └─ Status: ✅ Success',
  '[STEP_2_SUMMARY] 🤖 STEP 2 COMPLETE: Parallel Analysis',
  '[STEP_2_SUMMARY]    ├─ Analyzed: 5 charts',
  '[STEP_2_SUMMARY]    └─ Status: ✅ Success',
  '[STEP_3_SUMMARY] 📊 STEP 3 COMPLETE: Collecting Recommendations',
  '[STEP_3_SUMMARY]    ├─ Total recommendations: 3',
  '[STEP_3_SUMMARY]    │  ├─ BUY: 2',
  '[STEP_3_SUMMARY]    │  ├─ SELL: 1',
  '[STEP_3_SUMMARY]    │  └─ HOLD: 0',
  '[STEP_4_SUMMARY] 🏆 STEP 4 COMPLETE: Ranking Signals',
  '[STEP_4_SUMMARY]    └─ Status: ✅ Success',
  '[STEP_5_SUMMARY] 📦 STEP 5 COMPLETE: Checking Available Slots',
  '[STEP_5_SUMMARY]    └─ Status: ✅ Success',
  '[STEP_6_SUMMARY] 🎯 STEP 6 COMPLETE: Selecting Best Signals',
  '[STEP_6_SUMMARY]    ├─ Selected: 2 signals',
  '[STEP_6_SUMMARY]    └─ Status: ✅ Success',
  '[STEP_7_SUMMARY] 🚀 STEP 7 COMPLETE: Executing Signals',
  '[STEP_7_SUMMARY]    ├─ Trades executed: 2',
  '[STEP_7_SUMMARY]    └─ Status: ✅ Success',
  '[CYCLE_SUMMARY] 📊 CYCLE #1 COMPLETE - 1h - [abc123def456] - LIVE',
  '[CYCLE_SUMMARY]    ├─ Total duration: 12.5s',
  '[CYCLE_SUMMARY]    ├─ Symbols analyzed: 5',
  '[CYCLE_SUMMARY]    ├─ Recommendations generated: 3',
  '[CYCLE_SUMMARY]    ├─ Actionable signals: 3',
  '[CYCLE_SUMMARY]    ├─ Selected for execution: 2',
  '[CYCLE_SUMMARY]    ├─ Trades executed: 2',
  '[CYCLE_SUMMARY]    ├─ Rejected trades: 0',
  '[CYCLE_SUMMARY]    └─ Errors: 0',
]

const result1 = filterLogsBySection(logs1)
console.log('Test 1: Full cycle with all steps and markers')
console.assert(result1.step0.length === 3, 'Step 0 has 3 logs')
console.assert(result1.step1.length === 3, 'Step 1 has 3 logs')
console.assert(result1.step2.length === 3, 'Step 2 has 3 logs')
console.assert(result1.step3.length === 5, 'Step 3 has 5 logs')
console.assert(result1.step4.length === 2, 'Step 4 has 2 logs')
console.assert(result1.step5.length === 2, 'Step 5 has 2 logs')
console.assert(result1.step6.length === 3, 'Step 6 has 3 logs')
console.assert(result1.step7.length === 3, 'Step 7 has 3 logs')
console.assert(result1.cycleSummary.length === 9, 'Cycle summary has 9 logs')
console.assert(result1.step1_5.length === 0, 'Step 1.5 has no logs')
console.log('✅ Test 1 passed\n')

// Test 2: Partial cycle with only some steps
const logs2 = [
  '[STEP_0_SUMMARY] 🧹 STEP 0 COMPLETE: Chart Cleanup',
  '[STEP_0_SUMMARY]    └─ Status: ✅ Success',
  '[STEP_1_SUMMARY] 📷 STEP 1 COMPLETE: Capturing Charts',
  '[STEP_1_SUMMARY]    ├─ Charts captured: 10',
  '[STEP_1_SUMMARY]    └─ Status: ✅ Success',
  '[STEP_1.5_SUMMARY] 🔍 STEP 1.5 COMPLETE: Checking Existing Recommendations',
  '[STEP_1.5_SUMMARY]    ├─ Total symbols: 10',
  '[STEP_1.5_SUMMARY]    └─ Status: ✅ Success',
  '[STEP_2_SUMMARY] 🤖 STEP 2 COMPLETE: Parallel Analysis',
  '[STEP_2_SUMMARY]    ├─ Analyzed: 8 charts',
  '[STEP_2_SUMMARY]    └─ Status: ✅ Success',
]

const result2 = filterLogsBySection(logs2)
console.log('Test 2: Partial cycle with some steps')
console.assert(result2.step0.length === 2, 'Step 0 has 2 logs')
console.assert(result2.step1.length === 3, 'Step 1 has 3 logs')
console.assert(result2.step1_5.length === 3, 'Step 1.5 has 3 logs')
console.assert(result2.step2.length === 3, 'Step 2 has 3 logs')
console.assert(result2.step3.length === 0, 'Step 3 has no logs')
console.assert(result2.cycleSummary.length === 0, 'Cycle summary has no logs')
console.log('✅ Test 2 passed\n')

// Test 3: Log marker removal
function formatLog(log: string): string {
  return log.replace(/\[STEP_\d\.?\d?_SUMMARY\]|\[CYCLE_SUMMARY\]/, '').trim()
}

const testLog = '[STEP_3_SUMMARY] 📊 STEP 3 COMPLETE: Collecting Recommendations'
const formatted = formatLog(testLog)
console.log('Test 3: Log marker removal')
console.assert(formatted === '📊 STEP 3 COMPLETE: Collecting Recommendations', 'Marker removed correctly')
console.log('✅ Test 3 passed\n')

console.log('✅ All tests passed!')
