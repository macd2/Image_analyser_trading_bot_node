/**
 * Unit tests for CycleSummaryCard log parsing logic
 * Tests that regex patterns correctly extract cycle summary data and steps
 */

function parseLogsForCycleSummary(logs: string[]) {
  const cycleSummaryLine = logs.find(log =>
    log.includes('CYCLE #') && log.includes('COMPLETE')
  )

  if (!cycleSummaryLine) return null

  const cycleMatch = cycleSummaryLine.match(/CYCLE #(\d+).*\[([a-z0-9]+)\].*-\s*(LIVE|DRYRUN)/)
  const timeframeMatch = cycleSummaryLine.match(/(\d+h)/)

  if (!cycleMatch) return null

  const cycleNumber = parseInt(cycleMatch[1])
  const cycleId = cycleMatch[2]
  const mode = cycleMatch[3] as 'LIVE' | 'DRYRUN'
  const timeframe = timeframeMatch ? timeframeMatch[1] : 'unknown'

  let symbolsAnalyzed = 0, recommendationsGenerated = 0, buySignals = 0, sellSignals = 0
  let holdSignals = 0, actionableSignals = 0, selectedForExecution = 0, tradesExecuted = 0
  let rejectedTrades = 0, errors = 0, duration = 0

  logs.forEach(log => {
    if (log.includes('Symbols analyzed:')) {
      const m = log.match(/Symbols analyzed:\s*(\d+)/)
      if (m) symbolsAnalyzed = parseInt(m[1])
    }
    if (log.includes('Recommendations generated:')) {
      const m = log.match(/Recommendations generated:\s*(\d+)/)
      if (m) recommendationsGenerated = parseInt(m[1])
    }
    if (log.includes('BUY:')) {
      const m = log.match(/BUY:\s*(\d+)/)
      if (m) buySignals = parseInt(m[1])
    }
    if (log.includes('SELL:')) {
      const m = log.match(/SELL:\s*(\d+)/)
      if (m) sellSignals = parseInt(m[1])
    }
    if (log.includes('HOLD:')) {
      const m = log.match(/HOLD:\s*(\d+)/)
      if (m) holdSignals = parseInt(m[1])
    }
    if (log.includes('Actionable signals:')) {
      const m = log.match(/Actionable signals:\s*(\d+)/)
      if (m) actionableSignals = parseInt(m[1])
    }
    if (log.includes('Selected for execution:')) {
      const m = log.match(/Selected for execution:\s*(\d+)/)
      if (m) selectedForExecution = parseInt(m[1])
    }
    if (log.includes('Trades executed:')) {
      const m = log.match(/Trades executed:\s*(\d+)/)
      if (m) tradesExecuted = parseInt(m[1])
    }
    if (log.includes('Rejected trades:')) {
      const m = log.match(/Rejected trades:\s*(\d+)/)
      if (m) rejectedTrades = parseInt(m[1])
    }
    if (log.includes('Errors:')) {
      const m = log.match(/Errors:\s*(\d+)/)
      if (m) errors = parseInt(m[1])
    }
    if (log.includes('Total duration:')) {
      const m = log.match(/Total duration:\s*([\d.]+)s/)
      if (m) duration = parseFloat(m[1])
    }
  })

  // Extract steps
  const steps: Array<{ step: string; emoji: string; title: string; logs: string[] }> = []
  const stepPatterns = [
    { step: '0', emoji: '🧹', title: 'Chart Cleanup', pattern: /STEP 0 COMPLETE/ },
    { step: '1', emoji: '📷', title: 'Capturing Charts', pattern: /STEP 1 COMPLETE/ },
    { step: '1.5', emoji: '🔍', title: 'Checking Existing Recommendations', pattern: /STEP 1.5 COMPLETE/ },
    { step: '2', emoji: '🤖', title: 'Parallel Analysis', pattern: /STEP 2 COMPLETE/ },
    { step: '3', emoji: '📊', title: 'Collecting Recommendations', pattern: /STEP 3 COMPLETE/ },
    { step: '4', emoji: '🏆', title: 'Ranking Signals by Quality', pattern: /STEP 4 COMPLETE/ },
    { step: '5', emoji: '📦', title: 'Checking Available Slots', pattern: /STEP 5 COMPLETE/ },
    { step: '6', emoji: '🎯', title: 'Selecting Best Signals', pattern: /STEP 6 COMPLETE/ },
    { step: '7', emoji: '🚀', title: 'Executing Signals', pattern: /STEP 7 COMPLETE/ },
  ]

  stepPatterns.forEach(({ step, emoji, title, pattern }) => {
    const idx = logs.findIndex(log => pattern.test(log))
    if (idx !== -1) {
      const stepLogs: string[] = []
      for (let i = idx; i < logs.length; i++) {
        const log = logs[i]
        if (i > idx && (log.includes('STEP') || log.includes('CYCLE #'))) break
        stepLogs.push(log)
      }
      steps.push({ step, emoji, title, logs: stepLogs })
    }
  })

  return {
    cycleNumber, cycleId, timeframe, mode, duration,
    status: errors === 0 ? 'success' : 'error',
    symbolsAnalyzed, recommendationsGenerated, buySignals, sellSignals, holdSignals,
    actionableSignals, selectedForExecution, tradesExecuted, rejectedTrades, errors, steps,
  }
}

// Test 1: Full cycle with all steps
const logs1 = [
  'STEP 0 COMPLETE: Chart Cleanup',
  '   ├─ Cleaned: 2 charts',
  '   └─ Status: Success',
  'STEP 1 COMPLETE: Capturing Charts',
  '   ├─ Charts captured: 5',
  '   └─ Status: Success',
  'STEP 2 COMPLETE: Parallel Analysis',
  '   ├─ Analyzed: 5 charts',
  '   └─ Status: Success',
  'STEP 3 COMPLETE: Collecting Recommendations',
  '   ├─ Total recommendations: 3',
  '   ├─ BUY: 2',
  '   ├─ SELL: 1',
  '   └─ HOLD: 0',
  'STEP 4 COMPLETE: Ranking Signals',
  '   └─ Status: Success',
  'STEP 5 COMPLETE: Checking Available Slots',
  '   └─ Status: Success',
  'STEP 6 COMPLETE: Selecting Best Signals',
  '   ├─ Selected: 2 signals',
  '   └─ Status: Success',
  'STEP 7 COMPLETE: Executing Signals',
  '   ├─ Trades executed: 2',
  '   └─ Status: Success',
  'CYCLE #1 COMPLETE - 1h - [abc123def456] - LIVE',
  '   ├─ Total duration: 12.5s',
  '   ├─ Symbols analyzed: 5',
  '   ├─ Recommendations generated: 3',
  '   ├─ Actionable signals: 3',
  '   ├─ Selected for execution: 2',
  '   ├─ Trades executed: 2',
  '   ├─ Rejected trades: 0',
  '   ├─ Errors: 0',
]

const result1 = parseLogsForCycleSummary(logs1)
console.log('Test 1: Full cycle with all steps')
console.assert(result1?.cycleNumber === 1, 'Cycle #1')
console.assert(result1?.cycleId === 'abc123def456', 'Cycle ID')
console.assert(result1?.mode === 'LIVE', 'Mode LIVE')
console.assert(result1?.duration === 12.5, 'Duration 12.5s')
console.assert(result1?.symbolsAnalyzed === 5, '5 symbols')
console.assert(result1?.tradesExecuted === 2, '2 trades')
console.assert(result1?.steps.length === 8, '8 steps')
console.assert(result1?.steps[0].step === '0', 'Step 0')
console.assert(result1?.steps[7].step === '7', 'Step 7')
console.log('✅ Test 1 passed\n')

// Test 2: DRYRUN cycle
const logs2 = [
  'STEP 0 COMPLETE: Chart Cleanup',
  'STEP 1 COMPLETE: Capturing Charts',
  'STEP 2 COMPLETE: Parallel Analysis',
  'STEP 3 COMPLETE: Collecting Recommendations',
  '   ├─ BUY: 4',
  '   ├─ SELL: 3',
  '   └─ HOLD: 1',
  'STEP 4 COMPLETE: Ranking Signals',
  'STEP 5 COMPLETE: Checking Available Slots',
  'STEP 6 COMPLETE: Selecting Best Signals',
  'STEP 7 COMPLETE: Executing Signals',
  '   ├─ Trades executed: 3',
  'CYCLE #2 COMPLETE - 1h - [xyz789abc123] - DRYRUN',
  '   ├─ Total duration: 8.0s',
  '   ├─ Symbols analyzed: 10',
  '   ├─ Recommendations generated: 8',
  '   ├─ Actionable signals: 7',
  '   ├─ Selected for execution: 3',
  '   ├─ Trades executed: 3',
  '   ├─ Rejected trades: 0',
  '   ├─ Errors: 0',
]

const result2 = parseLogsForCycleSummary(logs2)
console.log('Test 2: DRYRUN cycle')
console.assert(result2?.cycleNumber === 2, 'Cycle #2')
console.assert(result2?.mode === 'DRYRUN', 'Mode DRYRUN')
console.assert(result2?.buySignals === 4, '4 BUY signals')
console.assert(result2?.sellSignals === 3, '3 SELL signals')
console.assert(result2?.holdSignals === 1, '1 HOLD signal')
console.assert(result2?.steps.length === 8, '8 steps')
console.log('✅ Test 2 passed\n')

console.log('✅ All tests passed!')
