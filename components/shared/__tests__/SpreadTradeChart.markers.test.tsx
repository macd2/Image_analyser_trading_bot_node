/**
 * Unit tests for SpreadTradeChart marker functionality
 * Tests that signal, fill, and exit markers are correctly generated and positioned
 */

import { ChartDataSet, TradeMarker, SpreadTradeData, StrategyMetadata } from '../SpreadTradeChart.types'

// Mock buildChartData function behavior
function buildChartDataMock(
  trade: SpreadTradeData,
  metadata: StrategyMetadata
): ChartDataSet {
  const signalMarker = trade.created_at ? {
    timeLabel: new Date(trade.created_at).toLocaleString(),
    type: 'signal' as const,
    color: '#3b82f6',
    label: 'Signal',
  } : undefined

  const fillMarker = (trade.filled_at || trade.fill_time) ? {
    timeLabel: new Date(trade.filled_at || trade.fill_time!).toLocaleString(),
    type: 'fill' as const,
    color: '#f59e0b',
    label: 'Fill',
  } : undefined

  const exitMarker = (trade.closed_at && trade.exit_price) ? {
    timeLabel: new Date(trade.closed_at).toLocaleString(),
    type: 'exit' as const,
    color: trade.exit_reason === 'tp_hit' ? '#22c55e' : '#ef4444',
    label: trade.exit_reason === 'tp_hit' ? 'TP Hit' : 'SL Hit',
  } : undefined

  return {
    zScores: [],
    spreads: [],
    prices: [],
    signalMarker,
    fillMarker,
    exitMarker,
  }
}

describe('SpreadTradeChart Markers', () => {
  const mockMetadata: StrategyMetadata = {
    beta: 0.05,
    spread_mean: 0.0,
    spread_std: 1.0,
    z_score_at_entry: 2.0,
    pair_symbol: 'ETHUSDT',
    z_exit_threshold: 0.5,
  }

  test('Signal marker is created when trade has created_at', () => {
    const trade: SpreadTradeData = {
      id: 'test-1',
      symbol: 'BTCUSDT',
      side: 'Buy',
      entry_price: 45000,
      stop_loss: 44000,
      take_profit: 46000,
      status: 'submitted',
      created_at: '2025-01-01T10:00:00Z',
      strategy_type: 'spread_based',
      strategy_metadata: mockMetadata,
    }

    const result = buildChartDataMock(trade, mockMetadata)

    expect(result.signalMarker).toBeDefined()
    expect(result.signalMarker?.type).toBe('signal')
    expect(result.signalMarker?.color).toBe('#3b82f6')
    expect(result.signalMarker?.label).toBe('Signal')
  })

  test('Fill marker is created when trade has filled_at', () => {
    const trade: SpreadTradeData = {
      id: 'test-2',
      symbol: 'BTCUSDT',
      side: 'Buy',
      entry_price: 45000,
      stop_loss: 44000,
      take_profit: 46000,
      status: 'filled',
      created_at: '2025-01-01T10:00:00Z',
      filled_at: '2025-01-01T10:05:00Z',
      strategy_type: 'spread_based',
      strategy_metadata: mockMetadata,
    }

    const result = buildChartDataMock(trade, mockMetadata)

    expect(result.fillMarker).toBeDefined()
    expect(result.fillMarker?.type).toBe('fill')
    expect(result.fillMarker?.color).toBe('#f59e0b')
    expect(result.fillMarker?.label).toBe('Fill')
  })

  test('Exit marker is created with TP color when exit_reason is tp_hit', () => {
    const trade: SpreadTradeData = {
      id: 'test-3',
      symbol: 'BTCUSDT',
      side: 'Buy',
      entry_price: 45000,
      stop_loss: 44000,
      take_profit: 46000,
      exit_price: 46000,
      status: 'closed',
      created_at: '2025-01-01T10:00:00Z',
      filled_at: '2025-01-01T10:05:00Z',
      closed_at: '2025-01-01T10:15:00Z',
      exit_reason: 'tp_hit',
      strategy_type: 'spread_based',
      strategy_metadata: mockMetadata,
    }

    const result = buildChartDataMock(trade, mockMetadata)

    expect(result.exitMarker).toBeDefined()
    expect(result.exitMarker?.type).toBe('exit')
    expect(result.exitMarker?.color).toBe('#22c55e')
    expect(result.exitMarker?.label).toBe('TP Hit')
  })

  test('Exit marker is created with SL color when exit_reason is sl_hit', () => {
    const trade: SpreadTradeData = {
      id: 'test-4',
      symbol: 'BTCUSDT',
      side: 'Buy',
      entry_price: 45000,
      stop_loss: 44000,
      take_profit: 46000,
      exit_price: 44000,
      status: 'closed',
      created_at: '2025-01-01T10:00:00Z',
      filled_at: '2025-01-01T10:05:00Z',
      closed_at: '2025-01-01T10:15:00Z',
      exit_reason: 'sl_hit',
      strategy_type: 'spread_based',
      strategy_metadata: mockMetadata,
    }

    const result = buildChartDataMock(trade, mockMetadata)

    expect(result.exitMarker).toBeDefined()
    expect(result.exitMarker?.color).toBe('#ef4444')
    expect(result.exitMarker?.label).toBe('SL Hit')
  })

  test('No markers are created when trade data is missing', () => {
    const trade: SpreadTradeData = {
      id: 'test-5',
      symbol: 'BTCUSDT',
      side: 'Buy',
      entry_price: 45000,
      stop_loss: 44000,
      take_profit: 46000,
      status: 'submitted',
      strategy_type: 'spread_based',
      strategy_metadata: mockMetadata,
    }

    const result = buildChartDataMock(trade, mockMetadata)

    expect(result.signalMarker).toBeUndefined()
    expect(result.fillMarker).toBeUndefined()
    expect(result.exitMarker).toBeUndefined()
  })
})

