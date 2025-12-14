import { NextResponse } from 'next/server';
import { getPositions, getPendingOrders } from '@/lib/ws/socket-server';

export async function GET(): Promise<Response> {
  try {
    const positions = getPositions();
    const pendingOrders = getPendingOrders();

    return NextResponse.json({
      success: true,
      positions: {
        count: positions.length,
        data: positions
      },
      pendingOrders: {
        count: pendingOrders.length,
        data: pendingOrders
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('[Debug] Error getting positions:', error);
    return NextResponse.json(
      { success: false, error: String(error) },
      { status: 500 }
    );
  }
}

