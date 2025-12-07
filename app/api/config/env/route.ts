/**
 * Environment Config API - Returns DB and Storage type for UI display
 */

import { NextResponse } from 'next/server';

// Force dynamic rendering - don't cache this endpoint
export const dynamic = 'force-dynamic';
export const revalidate = 0;

export async function GET() {
  const response = NextResponse.json({
    db_type: process.env.DB_TYPE || 'sqlite',
    storage_type: process.env.STORAGE_TYPE || 'local',
  });

  // Prevent caching
  response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate');

  return response;
}

