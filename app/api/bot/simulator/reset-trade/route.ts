import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, execute } from '@/lib/db/trading-db'

export async function POST(request: NextRequest) {
  try {
    const { tradeId } = await request.json()

    if (!tradeId) {
      return NextResponse.json(
        { error: 'Trade ID is required' },
        { status: 400 }
      )
    }

    // Reset the trade to paper_trade status with all exit fields cleared
    // This preserves signal data (entry_price, stop_loss, take_profit, etc.)
    // but clears all execution/exit data
    await execute(
      `UPDATE trades 
       SET status = 'paper_trade',
           fill_price = NULL,
           fill_time = NULL,
           filled_at = NULL,
           exit_price = NULL,
           pair_exit_price = NULL,
           closed_at = NULL,
           exit_reason = NULL,
           pair_fill_price = NULL
       WHERE id = ?`,
      [tradeId]
    )

    return NextResponse.json({
      success: true,
      message: 'Trade reset successfully',
      tradeId
    })
  } catch (error) {
    console.error('Reset trade error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to reset trade' },
      { status: 500 }
    )
  }
}

